from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from rich.console import Console
from rich.panel import Panel


OUTPUT = Path("outputs/prototypes/nested-placement/contact-sheet.png")
MODELS = ("attached-local", "projected-contained", "typed-mixed")


@dataclass(frozen=True)
class State:
    model: str = "typed-mixed"
    containment_threshold: float = 0.98
    child_occluded: bool = True
    control_family: str = "landing"


def _rotate(point: tuple[float, float], angle: float) -> tuple[float, float]:
    radians = math.radians(angle)
    return (
        point[0] * math.cos(radians) - point[1] * math.sin(radians),
        point[0] * math.sin(radians) + point[1] * math.cos(radians),
    )


def resolve_relationship(model: str, child_kind: str) -> str:
    if model != "typed-mixed":
        return model
    return "attached-local" if child_kind == "printed-mark" else "projected-contained"


def scenario(state: State) -> dict:
    parent_center = (180.0, 150.0)
    parent_angle = 32.0
    local_offset = (35.0, -20.0)
    relationship = resolve_relationship(state.model, "printed-mark")
    if relationship == "attached-local":
        offset = _rotate(local_offset, parent_angle)
        child_center = (parent_center[0] + offset[0], parent_center[1] + offset[1])
        child_angle = parent_angle
    else:
        child_center = (195.0, 142.0)
        child_angle = -12.0
    containment = 1.0 if state.model != "projected-contained" else 0.985
    accepted = containment >= state.containment_threshold
    return {
        "model": state.model,
        "relationship": relationship,
        "compatibility": {
            "container->printed-mark": "allowed:attached-local",
            "container->insert": "allowed:projected-contained",
            "landing->child": "not-declared",
            "manometro->child": "not-declared",
        },
        "instances": [
            {"instance_id": "parent-000", "parent_id": None, "compositing_order": 0},
            {"instance_id": "parent-000.child-000", "parent_id": "parent-000", "compositing_order": 1},
            {"instance_id": "occluder-000", "parent_id": None, "compositing_order": 2},
        ],
        "parent": {"center": parent_center, "angle": parent_angle},
        "child": {"center": child_center, "angle": child_angle},
        "containment": containment,
        "threshold": state.containment_threshold,
        "accepted": accepted,
        "failure": None if accepted else {"stage": "relationship.containment", "shortfall": state.containment_threshold - containment},
        "mask_semantics": {"full": "before later-object occlusion", "visible": "after occluder-000"},
        "control_signatures": {
            "landing": "flat-control-landing-v1",
            "manometro": "flat-control-manometro-v1",
        },
    }


def _ellipse_mask(size: tuple[int, int], box: tuple[int, int, int, int]) -> np.ndarray:
    image = Image.new("L", size, 0)
    ImageDraw.Draw(image).ellipse(box, fill=255)
    return np.asarray(image)


def render_panel(model: str, state: State) -> Image.Image:
    local = replace(state, model=model)
    result = scenario(local)
    image = Image.new("RGB", (360, 300), (16, 24, 39))
    draw = ImageDraw.Draw(image)
    parent = Image.new("RGBA", (170, 110), (70, 150, 210, 220)).rotate(32, expand=True)
    image.paste(parent, (96, 80), parent)
    cx, cy = result["child"]["center"]
    child_box = (int(cx - 28), int(cy - 20), int(cx + 28), int(cy + 20))
    draw.ellipse(child_box, fill=(251, 191, 36), outline=(255, 255, 255), width=3)
    full = _ellipse_mask(image.size, child_box)
    visible = full.copy()
    if state.child_occluded:
        draw.rectangle((190, 135, 280, 205), fill=(190, 60, 110), outline=(255, 255, 255), width=2)
        visible[135:206, 190:281] = 0
    draw.text((12, 10), model, fill=(245, 248, 252))
    draw.text((12, 31), f"relationship: {result['relationship']}", fill=(180, 205, 225))
    draw.text((12, 52), f"containment {result['containment']:.3f} / {state.containment_threshold:.3f}", fill=(180, 205, 225))
    status = "accepted" if result["accepted"] else "rejected"
    draw.text((12, 270), f"{status} | full {np.count_nonzero(full)} | visible {np.count_nonzero(visible)}", fill=(120, 230, 180) if result["accepted"] else (255, 100, 100))
    return image


def render_contact_sheet(state: State) -> None:
    panels = [render_panel(model, state) for model in MODELS]
    sheet = Image.new("RGB", (sum(panel.width for panel in panels), max(panel.height for panel in panels)), (0, 0, 0))
    x = 0
    for panel in panels:
        sheet.paste(panel, (x, 0))
        x += panel.width
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(OUTPUT)


def show(console: Console, state: State) -> None:
    result = scenario(state)
    render_contact_sheet(state)
    console.clear()
    console.print(Panel.fit("PROTOTYPE — nested placement", style="bold cyan"))
    console.print_json(json.dumps({"state": asdict(state), "resolved": result, "contact_sheet": str(OUTPUT)}))
    console.print("[m] model  [t] threshold  [o] occlusion  [c] control family  [q] quit")


def main() -> None:
    console = Console()
    state = State()
    while True:
        show(console, state)
        choice = console.input("> ").strip().lower()
        if choice == "q":
            break
        if choice == "m":
            state = replace(state, model=MODELS[(MODELS.index(state.model) + 1) % len(MODELS)])
        elif choice == "t":
            state = replace(state, containment_threshold=0.99 if state.containment_threshold == 0.98 else 0.98)
        elif choice == "o":
            state = replace(state, child_occluded=not state.child_occluded)
        elif choice == "c":
            state = replace(state, control_family="manometro" if state.control_family == "landing" else "landing")


if __name__ == "__main__":
    main()
