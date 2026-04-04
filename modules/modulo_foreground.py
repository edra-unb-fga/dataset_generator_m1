import cairosvg
import io
from PIL import Image
import os

class ForegroundGenerator:
    def __init__(self, template_dir="templates_svg"):
        # Inicializa o gerador apontando para a pasta de templates SVG.
        self.template_dir = template_dir


    def _load_template(self, shape_name, digit=None):
        # Lê o arquivo SVG como texto.
        filepath = ""
        try:
            if digit is not None:
                # Tenta carregar o template específico (ex: triangulo_3.svg)
                filepath = os.path.join(self.template_dir, f"{shape_name}_{digit}.svg")
                if os.path.exists(filepath):
                    with open(filepath, 'r', encoding='utf-8') as file:
                        return file.read()
            
            # Fallback para o template genérico antigo (ex: triangulo.svg)
            filepath = os.path.join(self.template_dir, f"{shape_name}.svg")
            with open(filepath, 'r', encoding='utf-8') as file:
                return file.read()
                
        except FileNotFoundError:
             raise FileNotFoundError(f"Erro: Template não encontrado: {filepath}")

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