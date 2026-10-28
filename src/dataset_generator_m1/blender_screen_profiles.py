"""Resolve the opt-in, saved BlenderProc hardware screen profiles."""
import json
from pathlib import Path


def select_screen_profile(catalog_path, profile_name, resolution):
    """Return the selected rule and study status for an explicit profile."""
    catalog = json.loads(Path(catalog_path).read_text())
    if catalog.get("schema_version") != 1 or profile_name not in catalog.get("profiles", {}):
        raise ValueError("Unknown or invalid execution profile")
    profile = catalog["profiles"][profile_name]
    pixels = resolution[0] * resolution[1]
    rule = next((item for item in profile["rules"]
                 if item["max_pixels"] is None or pixels <= item["max_pixels"]), None)
    if rule is None:
        raise ValueError("Profile has no rule for this resolution")
    return rule, profile["status"]
