"""Portable scene/content identity is distinct from execution and exact-file provenance."""
import hashlib
import json
from importlib.metadata import version
import platform
from .renderer_version import RENDERER_SEMANTICS


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def software_identity() -> dict:
    return {"python": platform.python_version(), **{name: version(name) for name in
            ("numpy", "opencv-python-headless", "albumentations", "Pillow")}}


def generation_contract(resolved, catalog) -> dict:
    payload = resolved.profile.model_dump(mode="json")
    for key in ("execution", "telemetry", "report"):
        payload.pop(key, None)
    for key in ("label", "tags", "max_wall_seconds", "max_rejection_rate"):
        payload["run"].pop(key, None)
    payload["background_synthesis"].pop("recipe_file", None)
    payload["assets"].pop("partition", None)
    for role in ("backgrounds", "foregrounds"):
        payload["assets"][role].pop("paths", None)
        payload["assets"][role].pop("catalog_file", None)
        payload["assets"][role]["sources"] = [
            {"logical_path": item.logical_path, "sha256": item.content_hash, "group": item.group,
             "class_name": item.class_name, "material_id": item.material_id, "tags": list(item.tags),
             "approved_roles": list(item.approved_roles), "seamless": item.seamless,
             "texture_kind": item.texture_kind}
            for item in getattr(catalog, role)
        ]
    return {"schema_version": 1, "renderer_semantics": RENDERER_SEMANTICS, "profile": payload,
            "family": resolved.family.model_dump(mode="json"), "recipes": resolved.recipes.model_dump(mode="json")}


def generation_identity(resolved, catalog) -> dict:
    value = generation_contract(resolved, catalog)
    return {"schema_version": 1, "sha256": digest(value), "renderer_semantics": value["renderer_semantics"]}


def execution_identity(plan) -> dict:
    import cv2
    policy = {key: value for key, value in plan.as_dict().items() if key not in {"warnings", "requested"}}
    from .performance_version import IMPLEMENTATION
    value = {"policy": policy, "software": software_identity(), "performance_implementation": IMPLEMENTATION,
             "effective_opencv_threads": plan.native_threads or cv2.getNumThreads()}
    return {"schema_version": 1, "sha256": digest(value), **value}
