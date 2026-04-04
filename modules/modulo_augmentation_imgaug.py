"""
Módulo de Augmentação usando imgaug - baseado em imageaug-example-main
Fornece augmentações robustas que preservam/transformam anotações em formato YOLO
"""

import numpy as np
from PIL import Image
import warnings

# Fix para compatibilidade com NumPy moderna e imgaug
# imgaug usa np.bool que foi removido, então monkeypatchamos antes de importar
with warnings.catch_warnings():
    warnings.simplefilter("ignore", FutureWarning)
    if not hasattr(np, 'bool'):
        np.bool = np.bool_
    if not hasattr(np, 'int'):
        np.int = np.int_
    if not hasattr(np, 'float'):
        np.float = np.float_
    if not hasattr(np, 'complex'):
        np.complex = np.complex_
    if not hasattr(np, 'object'):
        np.object = np.object_
    if not hasattr(np, 'str'):
        np.str = np.str_

import imgaug.augmenters as iaa
import imgaug.parameters as iap
from imgaug.augmentables.bbs import BoundingBox, BoundingBoxesOnImage
from typing import List, Tuple, Dict, Any


class AugmentationModuleImgAug:
    def __init__(self, config: Dict[str, Any]):
        """
        Configura o pipeline de augmentação usando imgaug.
        
        Args:
            config: Dicionário com configurações de augmentação
                   Exemplo: {
                       'flip_lr': 0.5,
                       'flip_ud': 0.0,
                       'crop_percent': [0.0, 0.05],
                       'contrast': [0.8, 1.2],
                       'affine_scale': [0.95, 1.05],
                       'affine_translate': [-0.1, 0.1],
                       'affine_rotate': [-15, 15],
                       'blur': True,
                       'noise': True,
                       'brightness': True,
                       'distortion': True,
                   }
        """
        self.config = config
        self.sequence = self._build_sequence()

    def _build_sequence(self) -> iaa.Sequential:
        """Constrói a sequência de augmentações a partir da configuração"""
        if not self.config or not bool(self.config.get('enabled', True)):
            return iaa.Sequential([])
        
        augmenters_list = []
        
        # Flips (não afetam bboxes, apenas espelham)
        flip_lr = float(self.config.get('flip_lr', 0.5))
        flip_ud = float(self.config.get('flip_ud', 0.0))
        augmenters_list.append(iaa.Fliplr(flip_lr))
        augmenters_list.append(iaa.Flipud(flip_ud))
        
        # Crop (afeta bboxes)
        crop_percent = self.config.get('crop_percent', [0.0, 0.05])
        if isinstance(crop_percent, (list, tuple)):
            crop_tuple = tuple(crop_percent)
        else:
            crop_tuple = (0.0, float(crop_percent))
        augmenters_list.append(iaa.Crop(percent=crop_tuple))
        
        # Contrast
        contrast = self.config.get('contrast', [0.8, 1.2])
        if isinstance(contrast, (list, tuple)):
            contrast_tuple = tuple(contrast)
        else:
            contrast_tuple = (0.8, 1.2)
        augmenters_list.append(iaa.LinearContrast(contrast_tuple))
        
        # Affine transformations (scale, translate, rotate)
        affine_prob = float(self.config.get('affine_prob', 0.5))
        affine_scale = self.config.get('affine_scale', [0.95, 1.05])
        affine_translate = self.config.get('affine_translate', [-0.05, 0.05])
        affine_rotate = self.config.get('affine_rotate', [-10, 10])
        
        if isinstance(affine_scale, (list, tuple)):
            scale_tuple = (affine_scale[0], affine_scale[1])
        else:
            scale_tuple = (0.95, 1.05)
            
        if isinstance(affine_translate, (list, tuple)):
            translate_tuple = (affine_translate[0], affine_translate[1])
        else:
            translate_tuple = (-0.05, 0.05)
            
        if isinstance(affine_rotate, (list, tuple)):
            rotate_tuple = (affine_rotate[0], affine_rotate[1])
        else:
            rotate_tuple = (-10, 10)
        
        augmenters_list.append(
            iaa.Sometimes(
                affine_prob,
                iaa.Affine(
                    scale={"x": scale_tuple, "y": scale_tuple},
                    translate_percent={"x": translate_tuple, "y": translate_tuple},
                    rotate=rotate_tuple,
                    mode='edge'
                )
            )
        )
        
        # Blur
        if self.config.get('blur', True):
            augmenters_list.append(
                iaa.OneOf([
                iaa.GaussianBlur(sigma=(0.0, 0.3)),
                iaa.MotionBlur(k=(3, 5)),
            ])
            )
        
        # Noise
        if self.config.get('noise', True):
            # Parâmetros configuráveis de ruído
            noise_prob = float(self.config.get('noise_probability', 0.5))
            
            gaussian_scale = self.config.get('noise_gaussian_scale', [.0, 0.01*255])
            if isinstance(gaussian_scale, (list, tuple)):
                gaussian_scale_tuple = tuple(gaussian_scale)
            else:
                gaussian_scale_tuple = (0.0, float(gaussian_scale)*255)
            
            dropout_prob = self.config.get('noise_dropout_prob', [0.01, 0.05])
            if isinstance(dropout_prob, (list, tuple)):
                dropout_prob_tuple = tuple(dropout_prob)
            else:
                dropout_prob_tuple = (0.01, float(dropout_prob))
            
            augmenters_list.append(
                iaa.Sometimes(
                    noise_prob,
                    iaa.OneOf([
                    iaa.AdditiveGaussianNoise(loc=0, scale=(0.0, 0.01*255)),
                    iaa.Dropout(p=(0.0, 0.01)),
                    
])  
                )
            )
        
        # Brightness
        if self.config.get('brightness', True):
            augmenters_list.append(
                iaa.Multiply((0.8, 1.2), per_channel=0.1)
            )
        
        # Perspectiva/Distorção
        if self.config.get('distortion', True):
            augmenters_list.append(
                iaa.Sometimes(
                    0.3,
                    iaa.PerspectiveTransform(scale=(0.01, 0.03))
                )
            )
            augmenters_list.append(
                iaa.Sometimes(
                    0.2,
                    iaa.ElasticTransformation(alpha=(0.0, 30.0), sigma=5.0)
                )
            )
        
        return iaa.Sequential(augmenters_list)

    def apply_image_only(self, image_pil: Image.Image) -> Image.Image:
        """Aplica augmentação apenas na imagem (sem bboxes)."""
        image_np = np.array(image_pil)

        # Para imagens RGBA (foreground), preserva o alpha original para evitar
        # que ruído/blur torne regiões transparentes em pixels visíveis.
        if image_pil.mode == "RGBA" and image_np.ndim == 3 and image_np.shape[2] == 4:
            rgb = image_np[:, :, :3]
            alpha = image_np[:, :, 3]

            aug_rgb = self.sequence(image=rgb)
            aug_rgba = np.dstack((aug_rgb, alpha)).astype('uint8')

            # Garante que pixels totalmente transparentes não carreguem cor residual.
            aug_rgba[alpha == 0, :3] = 0
            return Image.fromarray(aug_rgba, mode="RGBA")

        aug_image_np = self.sequence(image=image_np)
        return Image.fromarray(aug_image_np.astype('uint8'))
    
    def apply(self, 
              image_pil: Image.Image, 
              bboxes_yolo: List[List[float]]
              ) -> Tuple[Image.Image, List[List[float]]]:
        """
        Aplica augmentação na imagem e transforma as bboxes em paralelo.
        
        Args:
            image_pil: Imagem PIL em RGB
            bboxes_yolo: Lista de bboxes em formato YOLO:
                        [[cx, cy, w, h, class_id], ...]
                        Coordenadas normalizadas [0, 1]
        
        Returns:
            aug_image: Imagem augmentada (PIL)
            aug_bboxes: Bboxes transformadas no mesmo formato
                       Boxes que saíram da imagem ou têm área zero são removidas
        """
        
        if not bboxes_yolo:
            # Sem bboxes, apenas augmenta a imagem
            return self.apply_image_only(image_pil), []
        
        # Converte imagem para numpy
        image_np = np.array(image_pil)
        h, w = image_np.shape[:2]
        
        # Converte de YOLO normalizado para coordenadas de pixel (x1, y1, x2, y2)
        bboxes_imgaug = []
        
        for bbox in bboxes_yolo:
            cx, cy, bw, bh, class_id = bbox
            
            # Converte de normalizado para pixels
            x_center = cx * w
            y_center = cy * h
            box_w = bw * w
            box_h = bh * h
            
            # Calcula x1, y1, x2, y2
            x1 = x_center - box_w / 2
            y1 = y_center - box_h / 2
            x2 = x_center + box_w / 2
            y2 = y_center + box_h / 2
            
            # Clipa as coordenadas (imgaug é sensível)
            x1 = max(0, min(w, x1))
            y1 = max(0, min(h, y1))
            x2 = max(0, min(w, x2))
            y2 = max(0, min(h, y2))
            
            if x2 > x1 and y2 > y1:  # Bbox válida
                # Mantém o class_id preso à bbox para evitar desalinhamento
                # quando alguma bbox é descartada pelo pipeline.
                bb = BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2, label=int(class_id))
                bboxes_imgaug.append(bb)
        
        # Cria BoundingBoxesOnImage
        bbs = BoundingBoxesOnImage(bboxes_imgaug, shape=image_np.shape)
        
        # Aplica augmentação determinística (com seed para reproducibilidade por padrão)
        aug_image_np, aug_bbs = self.sequence(image=image_np, bounding_boxes=bbs)
        
        # Converte de volta para YOLO normalizado
        aug_h, aug_w = aug_image_np.shape[:2]
        aug_bboxes = []
        
        for bb in aug_bbs.bounding_boxes:
            # Garante que está dentro dos limites
            x1 = max(0, min(aug_w, bb.x1))
            y1 = max(0, min(aug_h, bb.y1))
            x2 = max(0, min(aug_w, bb.x2))
            y2 = max(0, min(aug_h, bb.y2))
            
            # Converte de volta para normalizado
            if x2 > x1 and y2 > y1:
                width = (x2 - x1) / aug_w
                height = (y2 - y1) / aug_h
                center_x = (x1 + width * aug_w / 2) / aug_w
                center_y = (y1 + height * aug_h / 2) / aug_h
                
                # Garante que estão dentro do range [0, 1]
                center_x = max(0, min(1, center_x))
                center_y = max(0, min(1, center_y))
                width = min(1, width)
                height = min(1, height)
                
                if width > 0.01 and height > 0.01:  # Mínimo de área
                    class_id = bb.label
                    if class_id is None:
                        continue
                    aug_bboxes.append([
                        center_x,
                        center_y,
                        width,
                        height,
                        int(class_id)
                    ])
        
        # Converte de volta para PIL
        aug_image = Image.fromarray(aug_image_np.astype('uint8'))
        
        return aug_image, aug_bboxes
    
    def apply_multiple(self,
                       image_pil: Image.Image,
                       bboxes_yolo: List[List[float]],
                       num_augmentations: int = 1
                       ) -> List[Tuple[Image.Image, List[List[float]]]]:
        """
        Aplica múltiplas augmentações na mesma imagem (para dataset expansion).
        
        Args:
            image_pil: Imagem PIL
            bboxes_yolo: Bboxes em formato YOLO
            num_augmentations: Número de variações a gerar
        
        Returns:
            Lista de tuplas (imagem_augmentada, bboxes_augmentadas)
        """
        results = []
        for _ in range(num_augmentations):
            aug_image, aug_bboxes = self.apply(image_pil, bboxes_yolo)
            results.append((aug_image, aug_bboxes))
        
        return results
