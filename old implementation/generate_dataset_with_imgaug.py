"""
Script de demonstração do novo pipeline de augmentação com imgaug
Mostra como gerar imagens com anotações robustas em formato YOLO

Uso: python generate_dataset_with_imgaug.py
"""

import os
import sys
from pathlib import Path

# Adiciona o diretório atual ao path
sys.path.insert(0, str(Path(__file__).parent))

from modules.modulo_foreground import ForegroundGenerator
from modules.modulo_composicao import CompositionModule
from modules.modulo_augmentation_imgaug import AugmentationModuleImgAug
from modules.config_loader import load_config
import random


def main():
    print("=" * 70)
    print("GERADOR DE DATASET COM ANOTAÇÕES - Pipeline ImgAug")
    print("=" * 70)
    
    # Carrega configuração
    config = load_config()
    print(f"\nConfiguração carregada: {len(config)} seções")

    num_images = config["dataset"]["num_images"]
    augmentations_per_image = config["dataset"].get("augmentations_per_image", 1)
    
    print(f"Parâmetros:")
    print(f"   • Imagens a gerar: {num_images}")
    print(f"   • Augmentações por imagem: {augmentations_per_image}")
    print(f"   • Total esperado: {num_images * augmentations_per_image} imagens")

    digits = config["foreground"]["digits"]
    shapes = config["foreground"]["shapes"]
    print(f"\nForeground:")
    print(f"   • Dígitos: {digits}")
    print(f"   • Formas: {shapes}")

    # Cria diretório de output se não existir
    os.makedirs("output", exist_ok=True)

    fg_generator = ForegroundGenerator(template_dir="templates_svg")
    composer = CompositionModule(bg_dir=config["background"]["folder"])
    
    # Inicializa o augmentador com imgaug
    print(f"\nInicializando augmentador ImgAug...")
    augmentor = AugmentationModuleImgAug(config["augmentation"])
    print(f"Augmentador inicializado")

    min_objs = config["dataset"].get("min_objects", 1)
    max_objs = config["dataset"].get("max_objects", 1)
    
    all_combinations = [(s, d) for s in shapes for d in digits]
    image_counter = 0
    success_count = 0
    failed_count = 0
    
    print(f"\nIniciando geração de dataset...\n")

    for i in range(num_images):
        print(f"─" * 70)
        print(f"Processando imagem base {i+1}/{num_images}")
        
        # Decide quantos objetos terá nesta imagem
        num_objects_in_image = random.randint(min_objs, max_objs)
        num_objects_in_image = min(num_objects_in_image, len(all_combinations))
        
        objects_to_compose = []
        selected_combinations = random.sample(all_combinations, num_objects_in_image)

        for shape, digit in selected_combinations:
            fg = fg_generator.generate(shape_name=shape, digit=digit)
            class_map = {3: 0, 4: 1, 5: 2}
            correct_class_id = class_map.get(digit, 0)
            objects_to_compose.append((fg, correct_class_id))

        # Config de composição
        rotation_limit = config["composition"].get("rotation_limit", 0)
        scale_range = config["composition"].get("scale_range", (0.15, 0.4))
        min_dist = config["composition"].get("min_dist", 0)

        # Compõe a imagem
        image, original_annotations, bboxes_raw = composer.compose_multiple(
            objects=objects_to_compose,
            scale_range=scale_range,
            rotation_limit=rotation_limit,
            min_dist=min_dist
        )
        
        print(f"   → Imagem base com {len(bboxes_raw)} objetos composta")
        
        # Aplica múltiplas augmentações
        aug_results = augmentor.apply_multiple(image, bboxes_raw, augmentations_per_image)
        
        # Salva cada augmentação
        aug_success = 0
        for aug_idx, (aug_image, aug_bboxes) in enumerate(aug_results):
            if len(aug_bboxes) == 0:
                print(f"   Augmentação {aug_idx} descartada (sem bboxes válidas)")
                failed_count += 1
                continue
            
            yolo_lines = []
            for final_bbox in aug_bboxes:
                line = f"{int(final_bbox[4])} {final_bbox[0]:.6f} {final_bbox[1]:.6f} {final_bbox[2]:.6f} {final_bbox[3]:.6f}"
                yolo_lines.append(line)
            
            yolo_txt = "\n".join(yolo_lines)
            
            # Salva imagem e anotação
            aug_image.save(f"output/image_{image_counter}.jpg")
            with open(f"output/image_{image_counter}.txt", "w") as f:
                f.write(yolo_txt)
            
            success_count += 1
            aug_success += 1
            image_counter += 1
        
        print(f"   {aug_success}/{augmentations_per_image} augmentações salvas")

    print(f"\n{'=' * 70}")
    print(f"GERAÇÃO CONCLUÍDA")
    print(f"{'=' * 70}")
    print(f"Estatísticas:")
    print(f"   • Imagens salvas com sucesso: {success_count}")
    print(f"   • Augmentações descartadas: {failed_count}")
    print(f"   • Imagens finais geradas: {success_count}")
    print(f"   • Localização: ./output/")
    print(f"\nFormato das anotações: YOLO")
    print(f"   • Cada imagem tem um arquivo .txt correspondente")
    print(f"   • Formato: class_id center_x center_y width height")
    print(f"   • Coordenadas normalizadas [0, 1]")
    print(f"\n{'=' * 70}\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nErro durante a execução:")
        print(f"   {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
