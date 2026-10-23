"""PROTOTYPE: do material maps justify a new production lighting model?"""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
from time import perf_counter_ns

import cv2
import numpy as np
from PIL import Image, ImageDraw
from rich.console import Console

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from dataset_generator_m1.assets import build_asset_catalog
from dataset_generator_m1.backgrounds import BackgroundSynthesizer
from dataset_generator_m1.config import load_profile
from dataset_generator_m1.models import AppearanceConfig
from dataset_generator_m1.scene import ScenePlanner, SceneRenderer, derive_seed
from model import shade


def render(material, output, azimuth):
    color = np.asarray(Image.open(material / "color.jpg").convert("RGB"), dtype=np.float32) / 255
    normal = np.asarray(Image.open(material / "normal.jpg").convert("RGB"), dtype=np.float32) / 255
    roughness = np.asarray(Image.open(material / "roughness.jpg").convert("L"), dtype=np.float32) / 255
    choices = [("colour only", color, 0)]
    for label, angle, rough in (("normal lighting", azimuth, False), ("normal + roughness", azimuth, True), ("different light", azimuth+90, True)):
        started = perf_counter_ns()
        image = shade(color, normal, roughness, azimuth=angle, use_roughness=rough)
        choices.append((label, image, perf_counter_ns()-started))
    sheet = Image.new("RGB", (4*400, 3*310), "white")
    draw = ImageDraw.Draw(sheet)
    evidence = []
    for row, family in enumerate(("landing", "landing-pad", "manometro")):
        config = Path("examples/configs") / f"{family}_minimal.yaml"
        resolved = load_profile(config)
        profile = resolved.profile.model_copy(update={"appearance": AppearanceConfig()})
        resolved = resolved.model_copy(update={"profile": profile})
        catalog = build_asset_catalog(resolved)
        plan = ScenePlanner(resolved, catalog).plan(1, 0)
        background = BackgroundSynthesizer(catalog, resolved.recipes).synthesize(plan.recipe_id, plan.canvas_size, np.random.default_rng(derive_seed(profile.run.seed, 1, 0, "prototype")))
        signature = None
        for col, (label, texture, cost) in enumerate(choices):
            pixels = np.clip(cv2.resize(texture, plan.canvas_size) * 255, 0, 255).astype(np.uint8)
            result = SceneRenderer(resolved).render(plan, replace(background, image=pixels))
            current = ([(a.bbox, a.source_asset) for a in result.annotations], [m.tobytes() for m in result.full_coverages])
            if signature is None:
                signature = current
            invariant = current == signature
            preview = Image.fromarray(result.image)
            preview.thumbnail((398, 280))
            sheet.paste(preview, (col*400, row*310+28))
            draw.text((col*400+5, row*310+5), f"{family}: {label}", fill="black")
            evidence.append({"family": family, "choice": label, "map_shading_ns": cost, "geometry_and_masks_equal": invariant})
    output.mkdir(parents=True, exist_ok=True)
    sheet.save(output / "contact-sheet.jpg", quality=85)
    (output / "prototype.json").write_text(json.dumps({"azimuth": azimuth, "material": json.loads((material / "material.json").read_text()), "evidence": evidence}, indent=2), encoding="utf-8")
    return evidence


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--material-dir", type=Path, default=Path("outputs/materials/Ground068"))
    p.add_argument("--output-dir", type=Path, default=Path("outputs/prototypes/material-lighting"))
    p.add_argument("--demo", action="store_true")
    args = p.parse_args()
    console = Console()
    angle = 45
    while True:
        evidence = render(args.material_dir, args.output_dir, angle)
        console.clear()
        console.print({"prototype": True, "azimuth": angle, "evidence": evidence, "sheet": str(args.output_dir / "contact-sheet.jpg")})
        if args.demo:
            break
        action = input("[a] rotate light  [q] quit > ").strip().lower()
        if action == "q":
            break
        if action == "a":
            angle = (angle+45) % 360
