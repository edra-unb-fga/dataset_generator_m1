from PIL import Image
import random
import os
import numpy as np

class CompositionModule:
    def __init__(self, bg_dir=None):
        # Módulo responsável por compor o foreground no background e calcular a BBox.
        # Se bg_dir não for passado, ele gera fundos sintéticos para teste.
        self.bg_dir = bg_dir

    def _get_random_background(self, size=(640, 640)):
        # Carrega um fundo aleatório ou gera um fundo sólido/ruído para testes.
        if self.bg_dir and os.path.exists(self.bg_dir) and len(os.listdir(self.bg_dir)) > 0:
            # Pega uma imagem real se a pasta existir
            valid_images = [f for f in os.listdir(self.bg_dir) if f.endswith(('.jpg', '.png'))]
            bg_path = os.path.join(self.bg_dir, random.choice(valid_images))
            bg = Image.open(bg_path).convert("RGBA")
            bg = bg.resize(size) # Força o tamanho do YOLO
            return bg
        else:
            # Fundo de fallback (ruído/cinza) se não tiver imagens
            color = (random.randint(100, 200), random.randint(100, 200), random.randint(100, 200), 255)
            return Image.new("RGBA", size, color)

    def _check_overlap(self, rect1, rect2, min_dist=0):
        # Verifica se dois retângulos se sobrepoem considerando uma distância mínima.
        # rect: (x, y, w, h)
        l1, t1, w1, h1 = rect1
        r1, b1 = l1 + w1, t1 + h1
        
        l2, t2, w2, h2 = rect2
        r2, b2 = l2 + w2, t2 + h2
        
        # Se um estiver totalmente à direita/esquerda/cima/baixo do outro com a margem, não há overlap
        if l1 >= r2 + min_dist or r1 <= l2 - min_dist:
            return False
        if t1 >= b2 + min_dist or b1 <= t2 - min_dist:
            return False
            
        return True

    def _get_visible_bbox(self, fg_image, alpha_threshold=8):
        # Calcula o bbox do conteúdo visível (canal alpha) no próprio FG.
        # Retorna (x1, y1, x2, y2) no sistema local da imagem.
        if fg_image.mode != "RGBA":
            w, h = fg_image.size
            return (0, 0, w, h)

        alpha = np.array(fg_image.getchannel("A"))
        ys, xs = np.where(alpha > alpha_threshold)

        if len(xs) == 0 or len(ys) == 0:
            return None

        x1 = int(xs.min())
        y1 = int(ys.min())
        x2 = int(xs.max()) + 1
        y2 = int(ys.max()) + 1
        return (x1, y1, x2, y2)

    def compose_multiple(self, objects, scale_range=(0.15, 0.4), rotation_limit=0, output_size=(640, 640), min_dist=10, background_image=None):
        # Cola múltiplos FGs no BG de forma aleatória e calcula as BBoxes no formato YOLO.
        
        # Args:
            # objects (list): Lista de tuplas [(fg_image, class_id), (fg_image, class_id), ...].
            # scale_range (tuple): Porcentagem da tela que o objeto vai ocupar.
            # rotation_limit (int): Ângulo máximo de rotação (+/-).
            # output_size (tuple): Tamanho final da imagem (L, A).
            # min_dist (int): Distância mínima em pixels entre os objetos.
            
        # Returns:
            # composite (PIL.Image): A imagem final colada.
            # annotations (list of str): Lista de linhas texto para o .txt do YOLO.
            # bboxes_data (list of list): Lista de bboxes raw [x, y, w, h, class_id]

        # 1. Pega o Background
        if background_image is not None:
            bg = background_image.convert("RGBA").resize(output_size, Image.Resampling.LANCZOS)
        else:
            bg = self._get_random_background(size=output_size)
        bg_w, bg_h = output_size
        
        all_annotations = []
        all_bboxes_data = []
        
        # Lista de retângulos já posicionados (x, y, w, h)
        placed_rects = []

        # Itera sobre cada objeto para colar na imagem
        for (fg_image, class_id) in objects:
            
            # 2. Rotaciona e define o tamanho do Foreground (Escala aleatória)
            if rotation_limit > 0:
                angle = random.uniform(-rotation_limit, rotation_limit)
                fg_image = fg_image.rotate(angle, expand=True, resample=Image.BICUBIC)
                
            scale = random.uniform(scale_range[0], scale_range[1])
            new_fg_size = int(bg_w * scale)
            
            # Ajusta aspect ratio
            w_orig, h_orig = fg_image.size
            ratio = h_orig / w_orig
            
            new_w = new_fg_size
            new_h = int(new_w * ratio)
            
            fg_resized = fg_image.resize((new_w, new_h), Image.Resampling.LANCZOS)
            fg_w, fg_h = fg_resized.size

            visible_bbox = self._get_visible_bbox(fg_resized)
            if visible_bbox is None:
                print(f"Bbox warning: Foreground class {class_id} ficou totalmente transparente. Skipping.")
                continue

            vis_x1, vis_y1, vis_x2, vis_y2 = visible_bbox
            vis_w = vis_x2 - vis_x1
            vis_h = vis_y2 - vis_y1
            
            # 3. Sorteia a Posição (Garantindo que não saia da tela e sem overlap)
            max_x = bg_w - fg_w
            max_y = bg_h - fg_h
            
            # Garante que as dimensões sejam válidas
            if max_x < 0: max_x = 0
            if max_y < 0: max_y = 0
            
            # Tenta encontrar uma posição livre
            max_attempts = 50
            placed = False
            paste_x, paste_y = 0, 0
            
            for _ in range(max_attempts):
                candidate_x = random.randint(0, max_x)
                candidate_y = random.randint(0, max_y)
                
                candidate_rect = (candidate_x + vis_x1, candidate_y + vis_y1, vis_w, vis_h)
                
                overlap = False
                for r in placed_rects:
                    if self._check_overlap(candidate_rect, r, min_dist):
                        overlap = True
                        break
                
                if not overlap:
                    paste_x, paste_y = candidate_x, candidate_y
                    placed_rects.append(candidate_rect)
                    placed = True
                    break
            
            if not placed:
                print(f"Bbox overlap warning: Could not place object {class_id} after {max_attempts} attempts. Skipping.")
                continue # Pula este objeto se não couber
            
            # 4. A COLAGEM
            # Cria uma camada transparente do tamanho do BG para este objeto
            fg_layer = Image.new("RGBA", bg.size, (0, 0, 0, 0))
            fg_layer.paste(fg_resized, (paste_x, paste_y), fg_resized)
            
            # Aplica sobre o background atual acumulando
            bg = Image.alpha_composite(bg, fg_layer)
            
            # 5. MATEMÁTICA DA BBOX (YOLO Format)
            bbox_x1 = paste_x + vis_x1
            bbox_y1 = paste_y + vis_y1
            bbox_w = vis_w
            bbox_h = vis_h

            center_x_px = bbox_x1 + (bbox_w / 2.0)
            center_y_px = bbox_y1 + (bbox_h / 2.0)
            
            x_center_norm = center_x_px / bg_w
            y_center_norm = center_y_px / bg_h
            w_norm = bbox_w / bg_w
            h_norm = bbox_h / bg_h
            
            yolo_annotation = f"{class_id} {x_center_norm:.6f} {y_center_norm:.6f} {w_norm:.6f} {h_norm:.6f}"
            bbox_data = [x_center_norm, y_center_norm, w_norm, h_norm, class_id]
            
            all_annotations.append(yolo_annotation)
            all_bboxes_data.append(bbox_data)
        
        return bg.convert("RGB"), all_annotations, all_bboxes_data

    def compose_and_annotate(self, fg_image, class_id, scale_range=(0.15, 0.4), rotation_limit=0, output_size=(640, 640)):
        # Wrapper para manter compatibilidade, mas agora usando a lógica de múltiplos objetos (lista com 1 item)
        bg, anns, bboxes = self.compose_multiple([(fg_image, class_id)], scale_range, rotation_limit, output_size)
        return bg, anns[0], bboxes[0]

# TESTE DO MÓDULO (Integrando com o Gerador anterior)
if __name__ == "__main__":
    from modulo_foreground import ForegroundGenerator
    
    # 1. Gera Triângulo com 5 (Foreground)
    fg_gen = ForegroundGenerator()
    img_fg = fg_gen.generate("triangulo", 5)
    
    # 2. Inicializa o Compositor
    # Dica: Criar uma pasta 'backgrounds' com fotos de asfalto/chão
    composer = CompositionModule(bg_dir="backgrounds")
    
    # A classe do "5" no YOLO será o ID 2.
    final_img, yolo_txt = composer.compose_and_annotate(img_fg, class_id=2)
    
    # 3. Visualizar os resultados
    print(f"✅ Anotação YOLO Calculada: {yolo_txt}")
    final_img.show()
    final_img.save("teste_dataset_001.jpg")
    
    # Salva o arquivo texto de anotação
    with open("teste_dataset_001.txt", "w") as f:
        f.write(yolo_txt)
    print("✅ Arquivo .txt salvo com sucesso!")