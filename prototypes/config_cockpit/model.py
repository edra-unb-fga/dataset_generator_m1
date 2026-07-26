from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json


APPEARANCES = {
    "realistic-heavy": {"risk": "informational", "eta": "8-13 min", "effects": ["GaussianBlur", "PlasmaShadow", "RandomRain"]},
    "current-fast": {"risk": "none", "eta": "3-5 min", "effects": ["HueSaturationValue", "RandomBrightnessContrast"]},
    "legacy-heavy-compatible": {"risk": "confirmation", "eta": "11-19 min", "effects": ["PlasmaShadow", "AtmosphericFog"]},
    "random-fog-heavy": {"risk": "confirmation", "eta": "24-46 min", "effects": ["RandomFog"]},
}


def initial_state() -> dict:
    return {
        "section": "summary",
        "family": "landing",
        "appearance": "realistic-heavy",
        "custom_effects": [],
        "composer_revision": 1,
        "receipt_revision": None,
        "run": "not-started",
        "events": [],
    }


def contract_hash(state: dict) -> str:
    contract = {
        "family": state["family"],
        "appearance": state["appearance"],
        "custom_effects": state["custom_effects"],
        "revision": state["composer_revision"],
    }
    return sha256(json.dumps(contract, sort_keys=True).encode()).hexdigest()[:12]


def summary(state: dict) -> dict:
    profile = APPEARANCES[state["appearance"]]
    receipt = "valid" if state["receipt_revision"] == state["composer_revision"] else "missing/stale"
    return {
        "section": state["section"],
        "family": state["family"],
        "appearance": state["appearance"],
        "effects": [*profile["effects"], *[effect["type"] for effect in state["custom_effects"]]],
        "warning": profile["risk"],
        "eta": profile["eta"],
        "receipt": receipt,
        "contract": contract_hash(state),
        "run": state["run"],
        "suggested_next": "confirm preflight" if profile["risk"] == "confirmation" and receipt != "valid" else "start or inspect run",
    }


def reduce(state: dict, action: str) -> dict:
    next_state = deepcopy(state)
    profiles = list(APPEARANCES)
    if action == "appearance":
        index = (profiles.index(next_state["appearance"]) + 1) % len(profiles)
        next_state["appearance"] = profiles[index]
        next_state["composer_revision"] += 1
    elif action == "effect":
        next_state["custom_effects"].append({"id": f"custom-{len(next_state['custom_effects']) + 1}", "stage": "final", "type": "AtmosphericFog", "depth_mode": "diagonal"})
        next_state["composer_revision"] += 1
    elif action == "receipt":
        next_state["receipt_revision"] = next_state["composer_revision"]
    elif action == "start" and next_state["run"] in {"not-started", "stopped"}:
        next_state["run"] = "running"
    elif action == "pause" and next_state["run"] == "running":
        next_state["run"] = "draining"
    elif action == "drained" and next_state["run"] == "draining":
        next_state["run"] = "paused"
    elif action == "continue" and next_state["run"] == "paused":
        next_state["run"] = "running"
    elif action == "stop" and next_state["run"] in {"running", "paused", "draining"}:
        next_state["run"] = "stopped"
    elif action.startswith("section:"):
        next_state["section"] = action.split(":", 1)[1]
    next_state["events"].append(action)
    return next_state
