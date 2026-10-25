"""Render the supplied pad artwork at its native SVG dimensions.

Optional asset-maintenance dependency (not needed to generate datasets):
    uv run --no-project --with cairosvg==2.9.1 python scripts/generate_pad_fixtures.py
"""
from pathlib import Path

import cairosvg


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1] / "foregrounds" / "landing_pad_foregrounds"
    root.mkdir(parents=True, exist_ok=True)
    for name in ("landing-base", "takeoff-base"):
        cairosvg.svg2png(url=str(root / "sources" / f"{name}.svg"), write_to=str(root / f"{name}.png"))
