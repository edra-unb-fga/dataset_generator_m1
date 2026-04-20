import cairosvg
import io
import os
import re
from pathlib import Path

import cv2
from PIL import Image

class ForegroundGenerator:
    def __init__(self, template_dir="templates_svg"):
        # Inicializa o gerador apontando para a pasta de templates SVG.
        self.template_dir = template_dir


    def _find_template_path(self, shape_name, digit=None):
        # Procura primeiro o template específico e depois qualquer template da forma.
        template_dir = Path(self.template_dir)
        candidates = []

        if digit is not None:
            candidates.append(template_dir / f"{shape_name}_{digit}.svg")

        candidates.append(template_dir / f"{shape_name}.svg")

        if digit is None:
            candidates.extend(sorted(template_dir.glob(f"{shape_name}_*.svg")))

        for candidate in candidates:
            if candidate.exists():
                return candidate

        return None

    def _load_template(self, shape_name, digit=None):
        # Lê o arquivo SVG como texto.
        filepath = self._find_template_path(shape_name, digit)
        try:
            if filepath is None:
                raise FileNotFoundError

            with open(filepath, 'r', encoding='utf-8') as file:
                return file.read()
        except FileNotFoundError:
            raise FileNotFoundError(f"Erro: Template não encontrado: {filepath}")

    def _generate_aruco_marker(self, aruco_id, marker_size, dictionary_name="DICT_4X4_50"):
        # Gera um marcador ArUco quadrado em escala de cinza.
        if not hasattr(cv2, "aruco"):
            raise ImportError(
                "opencv-contrib-python é necessário para gerar o gabarito com ArUco."
            )

        dictionary_constant = getattr(cv2.aruco, dictionary_name, None)
        if dictionary_constant is None:
            raise ValueError(f"Dicionário ArUco inválido: {dictionary_name}")

        dictionary = cv2.aruco.getPredefinedDictionary(dictionary_constant)
        max_id = int(dictionary.bytesList.shape[0]) - 1
        if aruco_id < 0 or aruco_id > max_id:
            raise ValueError(f"aruco_id fora do intervalo permitido para {dictionary_name}: 0..{max_id}")

        marker_gray = cv2.aruco.generateImageMarker(dictionary, int(aruco_id), int(marker_size))
        return Image.fromarray(marker_gray).convert("RGBA")

    def generate(self, shape_name, digit, color_border="#000000", color_text="#000000", output_size=(512, 512)):
        # Injeta os parâmetros no SVG e renderiza para uma imagem PIL RGBA.
        
        # Args:
            # shape_name (str): 'triangulo', 'pentagono', 'hexagono'.
            # digit (int/str): O número a ser inserido (3, 4, 5).
            # color_border (str): Cor HEX da forma geométrica.
            # color_text (str): Cor HEX do número.
            # output_size (tuple): Resolução de saída (W, H).
            
        # Returns:
            # Image (PIL): Imagem RGBA (com transparência) pronta para composição.

        # 1. Carrega o template SVG como texto
        svg_content = self._load_template(shape_name, digit)
        
        # 2. Injeção de Parâmetros (Substituição de string)
        # Se for um template específico, isso não fará nada pois não tem placeholders
        svg_content = svg_content.replace("{{DIGITO}}", str(digit))
        svg_content = svg_content.replace("{{COR_BORDA}}", color_border)
        svg_content = svg_content.replace("{{COR_TEXTO}}", color_text)
        
        # 3. Renderiza o SVG diretamente na memória (sem salvar no disco)
        # O CairoSVG transforma o vetor perfeito em pixels transparentes
        png_bytes = cairosvg.svg2png(
            bytestring=svg_content.encode('utf-8'),
            output_width=output_size[0],
            output_height=output_size[1]
        )
        
        # 4. Converte os bytes para um objeto de Imagem do Pillow (RGBA = Transparência)
        image = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
        
        return image

    def generate_gabarito(
        self,
        shape_name,
        aruco_id,
        color_border="#000000",
        output_size=(512, 512),
        marker_scale=0.18,
        dictionary_name="DICT_4X4_50",
    ):
        # Gera uma base sem número e insere um marcador ArUco no centro.
        svg_content = self._load_template(shape_name, None)

        svg_content = re.sub(r"<text\b.*?</text>", "", svg_content, flags=re.DOTALL)
        svg_content = svg_content.replace("{{COR_BORDA}}", color_border)
        svg_content = svg_content.replace("{{COR_TEXTO}}", color_border)
        svg_content = svg_content.replace("{{DIGITO}}", "")

        png_bytes = cairosvg.svg2png(
            bytestring=svg_content.encode('utf-8'),
            output_width=output_size[0],
            output_height=output_size[1]
        )

        base_image = Image.open(io.BytesIO(png_bytes)).convert("RGBA")

        marker_size = max(1, int(min(output_size) * marker_scale))
        marker_image = self._generate_aruco_marker(
            aruco_id=aruco_id,
            marker_size=marker_size,
            dictionary_name=dictionary_name,
        )

        paste_x = (base_image.width - marker_image.width) // 2
        paste_y = (base_image.height - marker_image.height) // 2
        base_image.alpha_composite(marker_image, (paste_x, paste_y))

        return base_image

# TESTE DO MÓDULO
if __name__ == "__main__":
    if not os.path.exists("templates_svg"):
        os.makedirs("templates_svg")
        print("Pasta 'templates_svg' criada. Salve o triangulo.svg lá dentro!")
    else:
        # Instancia o gerador
        fg_gen = ForegroundGenerator()

        try:
            # Pede para gerar um Triângulo com o número 5
            img_fg = fg_gen.generate(
                shape_name="triangulo", 
                digit=5, 
                color_border="#000000", # Preto
                color_text="#000000"    # Preto
            )
            
            # Mostra a imagem gerada
            img_fg.show()
            
            # Opcional: Salvar para ver o fundo transparente
            img_fg.save("teste_triangulo_5.png")
            print("Sucesso! Imagem gerada com fundo transparente.")
            
        except FileNotFoundError:
            print("Erro: Crie o arquivo 'triangulo.svg' dentro da pasta 'templates_svg' usando o código XML fornecido.")