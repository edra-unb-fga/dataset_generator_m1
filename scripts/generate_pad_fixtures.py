"""Independently authored geometric workflow fixtures; no uploaded image is copied."""
from pathlib import Path
from PIL import Image, ImageDraw


def draw_pad(size: tuple[int, int]) -> Image.Image:
    width, height = size
    image = Image.new("RGB", size, (255, 255, 64))
    draw = ImageDraw.Draw(image)
    border = max(2, min(size) // 40)
    draw.rectangle((border, border, width-border-1, height-border-1), fill=(67, 109, 184))
    radius = min(size) * 0.40
    cx, cy = width / 2, height / 2
    stroke = max(2, round(min(size) * 0.025))
    draw.ellipse((cx-radius, cy-radius, cx+radius, cy+radius), outline=(255, 255, 64), width=stroke)
    arm = radius * 0.62
    draw.line((cx-arm, cy, cx+arm, cy), fill=(255, 255, 64), width=stroke*2)
    draw.line((cx, cy-arm, cx, cy+arm), fill=(255, 255, 64), width=stroke*2)
    return image


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1] / "foregrounds" / "landing_pad_foregrounds"
    root.mkdir(parents=True, exist_ok=True)
    for name, size in (("synthetic-square", (512, 512)), ("synthetic-rectangle", (640, 400))):
        draw_pad(size).save(root / f"{name}.png")
