from modules.modulo_foreground import ForegroundGenerator
from modules.modulo_composicao import CompositionModule
from modules.modulo_augmentation_imgaug import AugmentationModuleImgAug
from modules.config_loader import load_config
import yaml
import random
import os
import shutil
from pathlib import Path


def _resolve_stage_augmentation_configs(config):
    aug_cfg = config["augmentation"]
    has_stages = any(isinstance(aug_cfg.get(k), dict) for k in ("foreground", "background", "composition"))

    if has_stages:
        fg_cfg = aug_cfg.get("foreground", {"enabled": False})
        bg_cfg = aug_cfg.get("background", {"enabled": False})
        comp_cfg = aug_cfg.get("composition", {"enabled": False})
        return fg_cfg, bg_cfg, comp_cfg

    return aug_cfg, aug_cfg, aug_cfg


def _build_shape_digit_class_map(shapes, digits):
    shape_label_alias = {
        "pentagono": "estrela",
    }

    class_map = {}
    class_names = []

    for shape in shapes:
        for digit in digits:
            class_id = len(class_names)
            class_map[(shape, digit)] = class_id
            shape_label = shape_label_alias.get(shape, shape)
            class_names.append(f"{shape_label}_{digit}")

    return class_map, class_names


def _split_pairs(file_pairs, split_cfg):
    total = len(file_pairs)
    if total == 0:
        return [], [], []

    train_ratio = float(split_cfg.get("train", 0.8))
    valid_ratio = float(split_cfg.get("valid", 0.1))
    test_ratio = float(split_cfg.get("test", 0.1))

    ratio_sum = train_ratio + valid_ratio + test_ratio
    if ratio_sum <= 0:
        train_ratio, valid_ratio, test_ratio = 0.8, 0.1, 0.1
        ratio_sum = 1.0

    train_ratio /= ratio_sum
    valid_ratio /= ratio_sum
    test_ratio /= ratio_sum

    n_train = int(total * train_ratio)
    n_valid = int(total * valid_ratio)
    n_test = total - n_train - n_valid

    train_pairs = file_pairs[:n_train]
    valid_pairs = file_pairs[n_train:n_train + n_valid]
    test_pairs = file_pairs[n_train + n_valid:n_train + n_valid + n_test]
    return train_pairs, valid_pairs, test_pairs


def _export_roboflow_dataset(output_dir, class_names, export_cfg):
    output_path = Path(output_dir)
    export_path = Path(export_cfg.get("output_dir", "roboflow_dataset"))
    seed = int(export_cfg.get("seed", 42))
    split_cfg = export_cfg.get("split", {"train": 0.8, "valid": 0.1, "test": 0.1})

    image_files = sorted(output_path.glob("*.jpg"))
    file_pairs = []
    for img_path in image_files:
        label_path = img_path.with_suffix(".txt")
        if label_path.exists():
            file_pairs.append((img_path, label_path))

    if len(file_pairs) == 0:
        print("Nenhum par imagem+label encontrado para exportar ao Roboflow.")
        return

    rng = random.Random(seed)
    rng.shuffle(file_pairs)
    train_pairs, valid_pairs, test_pairs = _split_pairs(file_pairs, split_cfg)

    if export_path.exists():
        shutil.rmtree(export_path)

    for split_name in ("train", "valid", "test"):
        (export_path / "images" / split_name).mkdir(parents=True, exist_ok=True)
        (export_path / "labels" / split_name).mkdir(parents=True, exist_ok=True)

    def _copy_split(pairs, split_name):
        for img_src, lbl_src in pairs:
            shutil.copy2(img_src, export_path / "images" / split_name / img_src.name)
            shutil.copy2(lbl_src, export_path / "labels" / split_name / lbl_src.name)

    _copy_split(train_pairs, "train")
    _copy_split(valid_pairs, "valid")
    _copy_split(test_pairs, "test")

    data_yaml = {
        "train": "images/train",
        "val": "images/valid",
        "test": "images/test",
        "nc": len(class_names),
        "names": class_names,
    }

    with open(export_path / "data.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(data_yaml, f, sort_keys=False, allow_unicode=False)

    print("\nExportação Roboflow concluída:")
    print(f"- Pasta: {export_path}")
    print(f"- train: {len(train_pairs)} imagens")
    print(f"- valid: {len(valid_pairs)} imagens")
    print(f"- test: {len(test_pairs)} imagens")
    print(f"- classes: {class_names}")


def _build_shape_class_map(shapes):
    class_map = {}
    class_names = []

    for shape in shapes:
        class_map[shape] = len(class_names)
        class_names.append(shape)

    return class_map, class_names


def _run_gabarito_mode(config):
    gabarito_cfg = config.get("gabarito", {})

    num_images = int(gabarito_cfg.get("num_images", config["dataset"].get("num_images", 100)))
    output_dir = gabarito_cfg.get("output_dir", "output_gabarito")
    shapes = gabarito_cfg.get("shapes", config.get("foreground", {}).get("shapes", []))
    marker_scale = float(gabarito_cfg.get("marker_scale", 0.18))
    aruco_dictionary = gabarito_cfg.get("aruco_dictionary", "DICT_4X4_50")
    output_size = tuple(config["dataset"].get("image_size", [640, 640]))

    if not shapes:
        raise ValueError("Nenhuma forma configurada para gerar o gabarito.")

    fg_generator = ForegroundGenerator(template_dir="templates_svg")
    composer = CompositionModule(bg_dir=config["background"]["folder"])
    class_map, class_names = _build_shape_class_map(shapes)

    scale_range = tuple(config["composition"].get("scale_range", [0.15, 0.4]))
    rotation_limit = int(config["composition"].get("rotation_limit", 0))

    os.makedirs(output_dir, exist_ok=True)

    for image_idx in range(num_images):
        shape_name = random.choice(shapes)
        class_id = class_map[shape_name]
        aruco_id = image_idx % 50

        gabarito_fg = fg_generator.generate_gabarito(
            shape_name=shape_name,
            aruco_id=aruco_id,
            output_size=output_size,
            marker_scale=marker_scale,
            dictionary_name=aruco_dictionary,
        )

        composed_image, yolo_txt, _ = composer.compose_and_annotate(
            gabarito_fg,
            class_id=class_id,
            scale_range=scale_range,
            rotation_limit=rotation_limit,
            output_size=output_size,
        )

        image_path = os.path.join(output_dir, f"image_{image_idx}.jpg")
        label_path = os.path.join(output_dir, f"image_{image_idx}.txt")

        composed_image.save(image_path)

        with open(label_path, "w", encoding="utf-8") as file:
            file.write(yolo_txt)

        print(f"image_{image_idx}.jpg gerado como gabarito da forma '{shape_name}' (ArUco {aruco_id})")

    export_cfg = dict(config.get("roboflow", {}))
    if export_cfg.get("enabled", True):
        export_cfg["output_dir"] = gabarito_cfg.get("roboflow_output_dir", "roboflow_dataset_gabarito")
        _export_roboflow_dataset(output_dir=output_dir, class_names=class_names, export_cfg=export_cfg)


def _choose_dataset_mode(config):
    configured_mode = str(config.get("mode", "prompt")).strip().lower()

    if configured_mode in {"dataset", "gabarito"}:
        return configured_mode

    if not os.isatty(0):
        return "dataset"

    print("Qual dataset você quer gerar?")
    print("1 - dataset normal")
    print("2 - gabarito")

    while True:
        choice = input("Escolha 1 ou 2: ").strip()
        if choice == "1":
            return "dataset"
        if choice == "2":
            return "gabarito"
        print("Opção inválida. Digite 1 ou 2.")

def main():
    config = load_config()

    mode = _choose_dataset_mode(config)
    if mode == "gabarito":
        _run_gabarito_mode(config)
        return

    num_images = config["dataset"]["num_images"]
    digits = config["foreground"]["digits"]
    shapes = config["foreground"]["shapes"]
    augmentations_per_image = config["dataset"].get("augmentations_per_image", 1)
    output_dir = config["dataset"].get("output_dir", "output")
    export_cfg = config.get("roboflow", {})

    fg_generator = ForegroundGenerator(
        template_dir="templates_svg"
    )

    composer = CompositionModule(bg_dir=config["background"]["folder"])

    # Inicializa augmentadores separados por etapa
    fg_aug_cfg, bg_aug_cfg, comp_aug_cfg = _resolve_stage_augmentation_configs(config)
    foreground_augmentor = AugmentationModuleImgAug(fg_aug_cfg)
    background_augmentor = AugmentationModuleImgAug(bg_aug_cfg)
    composition_augmentor = AugmentationModuleImgAug(comp_aug_cfg)

    # Configuração de quantidade de objetos
    min_objs = config["dataset"].get("min_objects", 1)
    max_objs = config["dataset"].get("max_objects", 1)

    os.makedirs(output_dir, exist_ok=True)
    
    # Todas as combinações possíveis de (forma, digito)
    all_combinations = [(s, d) for s in shapes for d in digits]
    shuffled_cycle = all_combinations[:]
    random.shuffle(shuffled_cycle)
    cycle_idx = 0

    def _pick_balanced_combinations(k):
        # Seleciona k combinações tentando manter a frequência global equilibrada.
        nonlocal shuffled_cycle, cycle_idx

        selected = []
        selected_set = set()
        max_unique = min(k, len(all_combinations))

        while len(selected) < max_unique:
            if cycle_idx >= len(shuffled_cycle):
                shuffled_cycle = all_combinations[:]
                random.shuffle(shuffled_cycle)
                cycle_idx = 0

            combo = shuffled_cycle[cycle_idx]
            cycle_idx += 1

            if combo not in selected_set:
                selected.append(combo)
                selected_set.add(combo)

        return selected

    class_map, class_names = _build_shape_digit_class_map(shapes, digits)
    output_size = tuple(config["dataset"].get("image_size", [640, 640]))

    image_counter = 0
    
    for i in range(num_images):
        
        # Decide quantos objetos terá nesta imagem
        num_objects_in_image = random.randint(min_objs, max_objs)
        # Garante que não pedimos mais objetos únicos do que existem combinações
        num_objects_in_image = min(num_objects_in_image, len(all_combinations))
        
        base_objects = []
        
        # Seleciona combinações únicas para esta imagem com distribuição mais equilibrada.
        selected_combinations = _pick_balanced_combinations(num_objects_in_image)

        for shape, digit in selected_combinations:
            fg = fg_generator.generate(
                shape_name= shape,
                digit = digit
            )

            correct_class_id = class_map[(shape, digit)]
            
            base_objects.append((fg, correct_class_id))

        # Config de Rotação e Distancia minima
        rotation_limit = config["composition"].get("rotation_limit", 0)
        scale_range = config["composition"].get("scale_range", (0.15, 0.4))
        min_dist = config["composition"].get("min_dist", 0)

        # Gera múltiplas variações com filtros separados por etapa:
        # 1) foreground, 2) background, 3) composição final com bbox
        for aug_idx in range(augmentations_per_image):
            staged_objects = []
            for fg_image, class_id in base_objects:
                fg_aug = foreground_augmentor.apply_image_only(fg_image)
                staged_objects.append((fg_aug, class_id))

            bg_base = composer._get_random_background(size=output_size)
            bg_aug = background_augmentor.apply_image_only(bg_base)

            composed_image, _, composed_bboxes = composer.compose_multiple(
                objects=staged_objects,
                scale_range=scale_range,
                rotation_limit=rotation_limit,
                output_size=output_size,
                min_dist=min_dist,
                background_image=bg_aug
            )

            aug_image, aug_bboxes = composition_augmentor.apply(composed_image, composed_bboxes)
            
            # Se a bbox foi descartada, pulamos esta augmentação
            if len(aug_bboxes) == 0:
                print(f"Augmentação {aug_idx} de image_{i} descartada (sem bboxes válidas).")
                continue
            
            yolo_lines = []
            for final_bbox in aug_bboxes:
                # final_bbox: [center_x, center_y, width, height, class_id]
                # Formata para string YOLO
                line = f"{int(final_bbox[4])} {final_bbox[0]:.6f} {final_bbox[1]:.6f} {final_bbox[2]:.6f} {final_bbox[3]:.6f}"
                yolo_lines.append(line)
            
            yolo_txt_aug = "\n".join(yolo_lines)
            
            # Salva imagem e anotação
            aug_image.save(os.path.join(output_dir, f"image_{image_counter}.jpg"))
            
            with open(os.path.join(output_dir, f"image_{image_counter}.txt"), "w", encoding="utf-8") as f:
                f.write(yolo_txt_aug)
            
            print(f"image_{image_counter}.jpg gerado com {len(aug_bboxes)} objetos (augmentação {aug_idx} de image_{i})")
            image_counter += 1

    if export_cfg.get("enabled", True):
        _export_roboflow_dataset(output_dir=output_dir, class_names=class_names, export_cfg=export_cfg)

if __name__ == "__main__":
    main()



