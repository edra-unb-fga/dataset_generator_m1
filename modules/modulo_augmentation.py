import albumentations as A
import numpy as np
from PIL import Image

class AugmentationModule:
    def __init__(self, config):
        """
        Configura o pipeline de augmentação com as transformações selecionadas.
        config: Dicionário contendo as chaves de augmentação (ex: {'blur': True, ...})
        """
        self.transforms = []
        
        # 1. Blur (Desfoque)
        if config.get('blur', False):
            self.transforms.append(
                A.OneOf([
                    A.MotionBlur(p=0.2), # Tremido de movimento
                    A.MedianBlur(blur_limit=3, p=0.1), # Suaviza ruído
                    A.Blur(blur_limit=3, p=0.1), # Blur simples
                ], p=0.4)
            )
            

        # 2. Noise (Ruído)
        if config.get('noise', False):
            self.transforms.append(
                A.OneOf([
                    A.GaussNoise(p=0.3), # Removido var_limit que causou warning
                    A.MultiplicativeNoise(multiplier=[0.5, 1.5], elementwise=True, p=0.2),
                ], p=0.4)
            )
            
        # 3. Brightness/Contrast
        if config.get('brightness', False):
            self.transforms.append(
                A.RandomBrightnessContrast(
                    brightness_limit=0.2, 
                    contrast_limit=0.2, 
                    brightness_by_max=True, 
                    p=0.5
                )
            )
            self.transforms.append(
                A.HueSaturationValue(
                    hue_shift_limit=20, 
                    sat_shift_limit=30, 
                    val_shift_limit=20, 
                    p=0.3
                )
            )

        # 4. Perspective
        if config.get('perspective', False):
            self.transforms.append(
                A.Perspective(scale=(0.05, 0.1), keep_size=True, p=0.4)
            )

        # 5. Distortion
        if config.get('distortion', False):
            self.transforms.append(
                A.OneOf([
                    A.OpticalDistortion(distort_limit=0.05, p=0.5), # Removido shift_limit
                    A.GridDistortion(num_steps=5, distort_limit=0.05, p=0.5),
                ], p=0.4)
            )


        self.pipeline = A.Compose(
            self.transforms, 
            bbox_params=A.BboxParams(format='yolo', min_visibility=0.1, label_fields=['class_ids'])
        )


    def apply(self, image_pil, bboxes_yolo):
        """
        Aplica a augmentação na imagem e nas bboxes (suporta múltiplos objetos).
        
        Args:
            image_pil (PIL.Image): Imagem original RGB.
            bboxes_yolo (list of list): Lista de bboxes [[x, y, w, h, class_id], ...]
                                        As coordenadas já devem estar normalizadas (0.0 a 1.0).
            
        Returns:
            processed_image (PIL.Image): Imagem augmentada.
            processed_bboxes (list): Lista de bboxes ajustadas: [[x, y, w, h, class]]
        """
        # Se não houver transformações, retorna original imediatamente
        if not self.transforms:
            return image_pil, bboxes_yolo

        image_np = np.array(image_pil)
        
        # O Albumentations espera as bboxes como uma lista de listas
        # O formato da bbox é definido em bbox_params (aqui usamos 'yolo')
        
        input_bboxes = []
        input_class_ids = []
        
        for bbox in bboxes_yolo:
            input_bboxes.append(bbox[:4])
            input_class_ids.append(bbox[4])
        
        try:
            # Albumentations espera uma LISTA de bboxes.
            transformed = self.pipeline(
                image=image_np, 
                bboxes=input_bboxes, 
                class_ids=input_class_ids
            )
            
            aug_image_np = transformed['image']
            aug_bboxes = transformed['bboxes'] # Retorna lista de tuplas (x, y, w, h)
            aug_labels = transformed['class_ids']
            
            aug_image_pil = Image.fromarray(aug_image_np)

            # Reconstrói a lista final com o class_id
            final_bboxes = []
            if len(aug_bboxes) > 0:
                for bbox, label in zip(aug_bboxes, aug_labels):
                     final_bboxes.append(list(bbox) + [label])
            else:
                # Se todas as bboxes sumiram
                pass
            
            return aug_image_pil, final_bboxes
            
        except ValueError as e:
            # Em caso de erro (ex: bbox inválida, coord fora de 0-1), printa warning
            # e retorna a imagem original sem augmentação
            print(f"Augmentation Error (bbox dropped?): {e}")
            return image_pil, bboxes_yolo

