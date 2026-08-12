from __future__ import annotations

import json
import os
import platform
import subprocess
from importlib.metadata import PackageNotFoundError, version
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter_ns
from typing import Any

import cv2
import numpy as np
from PIL import Image

from .assets import AssetCatalog
from .annotation_evidence import decode_mask_evidence, polygonize_coverage
from .models import ResolvedProfile


def _package_version(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def _sanitized_profile(resolved: ResolvedProfile) -> dict[str, Any]:
    profile = resolved.profile.model_dump(mode="json")
    for source_name in ("backgrounds", "foregrounds"):
        source = profile["assets"][source_name]
        source["paths"] = [Path(value).name if Path(value).is_absolute() else value for value in source["paths"]]
        if source.get("catalog_file") and Path(source["catalog_file"]).is_absolute():
            source["catalog_file"] = Path(source["catalog_file"]).name
    recipe_file = profile["background_synthesis"]["recipe_file"]
    if Path(recipe_file).is_absolute():
        profile["background_synthesis"]["recipe_file"] = Path(recipe_file).name
    return profile


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(value, indent=2, sort_keys=False))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _atomic_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _state_records(path: Path) -> list[dict[str, Any]]:
    return [json.loads(item.read_text(encoding="utf-8")) for item in sorted(path.glob("*.json"))]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _git_provenance() -> dict[str, Any]:
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, check=True).stdout.strip())
        return {"commit": commit, "dirty": dirty}
    except Exception:
        return {"commit": None, "dirty": None}


def _draw_overlay(image: np.ndarray, annotations: list[dict[str, Any]]) -> np.ndarray:
    output = image.copy()
    for annotation in annotations:
        x1, y1, x2, y2 = annotation["bbox"]
        cv2.rectangle(output, (x1, y1), (x2, y2), (45, 212, 191), 2)
        cv2.putText(output, annotation["class_name"], (x1, max(15, y1 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (45, 212, 191), 1)
    return output


def _mask_panel(masks: list[np.ndarray]) -> np.ndarray:
    if not masks:
        raise ValueError("QA mask panel requires at least one instance")
    output = np.zeros((*masks[0].shape, 3), dtype=np.uint8)
    colors = ((45, 212, 191), (244, 114, 182), (250, 204, 21), (96, 165, 250))
    for index, mask in enumerate(masks):
        strength = mask.astype(np.float32)[:, :, None] / 255.0
        color = np.asarray(colors[index % len(colors)], dtype=np.float32)
        output = np.maximum(output, np.rint(strength * color).astype(np.uint8))
    return output


def _draw_segmentation_qa(
    image: np.ndarray,
    annotations: list[dict[str, Any]],
    decoded: dict[str, dict[str, np.ndarray]],
    *,
    alpha_threshold: int,
    semantics: str,
) -> np.ndarray:
    overlay = image.copy()
    if not annotations:
        blank = np.zeros_like(image)
        return np.concatenate((overlay, blank, blank, blank), axis=1)
    full = [decoded[item["instance_id"]]["full"] for item in annotations]
    visible = [decoded[item["instance_id"]]["visible"] for item in annotations]
    differences: list[np.ndarray] = []
    for item in annotations:
        coverage = decoded[item["instance_id"]][semantics]
        projection = polygonize_coverage(coverage, alpha_threshold=alpha_threshold)
        points = np.asarray(projection.polygon, dtype=np.int32).reshape((-1, 1, 2))
        cv2.polylines(overlay, [points], True, (244, 114, 182), 2)
        exact = (coverage > alpha_threshold).astype(np.uint8)
        differences.append((np.abs(exact.astype(np.int16) - projection.reconstruction.astype(np.int16)) * 255).astype(np.uint8))
    difference = np.maximum.reduce(differences) if differences else np.zeros(image.shape[:2], dtype=np.uint8)
    heatmap = cv2.applyColorMap(difference, cv2.COLORMAP_INFERNO)
    heatmap = cv2.cvtColor(heatmap, cv2.COLOR_BGR2RGB)
    panel = np.concatenate((overlay, _mask_panel(full), _mask_panel(visible), heatmap), axis=1)
    width = image.shape[1]
    panel = cv2.copyMakeBorder(panel, 36, 0, 0, 0, cv2.BORDER_CONSTANT, value=(17, 24, 39))
    for index, label in enumerate(("image + polygon", "full coverage", "visible coverage", "polygon disagreement")):
        cv2.putText(
            panel,
            label,
            (index * width + 12, 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (240, 244, 248),
            1,
            cv2.LINE_AA,
        )
    return panel


@dataclass
class RunStore:
    root: Path
    resolved: ResolvedProfile
    catalog: AssetCatalog
    run_id: str

    @classmethod
    def open(
        cls,
        root: Path,
        resolved: ResolvedProfile,
        catalog: AssetCatalog,
        *,
        resume: bool,
        invocation: tuple[str, ...] = (),
        preflight: dict[str, Any] | None = None,
    ) -> "RunStore":
        root = root.resolve()
        run_id = f"{resolved.profile.run.label}-{resolved.contract_hash[:4]}-{catalog.fingerprint[:4]}"
        run_path = root / "run.json"
        if root.exists() and any(root.iterdir()) and not resume:
            raise ValueError(f"Output directory is not empty; use --resume: {root}")
        root.mkdir(parents=True, exist_ok=True)
        (root / "images").mkdir(exist_ok=True)
        (root / "masks").mkdir(exist_ok=True)
        (root / "qa").mkdir(exist_ok=True)
        (root / "state" / "samples").mkdir(parents=True, exist_ok=True)
        (root / "state" / "rejections").mkdir(parents=True, exist_ok=True)
        for name in ("samples.jsonl", "rejections.jsonl", "metrics.jsonl"):
            (root / name).touch(exist_ok=True)
        if run_path.exists():
            existing = json.loads(run_path.read_text(encoding="utf-8"))
            if existing.get("schema_version", 1) != 2:
                raise ValueError("Pool schema v1 remains auditable/exportable but cannot resume as pool schema v2; generate a new pool")
            if existing.get("contract_hash") != resolved.contract_hash or existing.get("catalog_fingerprint") != catalog.fingerprint:
                raise ValueError("Resume contract or asset catalog fingerprint does not match the existing run")
        else:
            provenance = {
                "generator_version": _package_version("dataset-generator-m1") or "0.1.0",
                "schema_version": 1,
                "python": platform.python_version(),
                "hardware": {
                    "system": platform.system(),
                    "release": platform.release(),
                    "machine": platform.machine(),
                    "processor": platform.processor(),
                    "logical_cpu_count": os.cpu_count(),
                },
                "dependencies": {
                    name: _package_version(name)
                    for name in ("albumentations", "numpy", "opencv-python-headless", "pydantic", "rich", "psutil", "PyYAML", "Pillow")
                },
                "git": _git_provenance(),
            }
            _atomic_json(
                run_path,
                {
                    "schema_version": 2,
                    "run_id": run_id,
                    "label": resolved.profile.run.label,
                    "tags": list(resolved.profile.run.tags),
                    "invocation": list(invocation),
                    "contract_hash": resolved.contract_hash,
                    "catalog_fingerprint": catalog.fingerprint,
                    "profile": _sanitized_profile(resolved),
                    "reference_graph": resolved.reference_graph,
                    "source_hashes": resolved.source_hashes,
                    "profile_metadata": list(resolved.profile_metadata),
                    "applied_overrides": resolved.applied_overrides,
                    "preflight": preflight,
                    "capabilities": {
                        "detection_boxes": True,
                        "full_instance_coverage": True,
                        "visible_instance_coverage": True,
                    },
                    "annotation_policy": resolved.family.annotation.model_dump(mode="json"),
                    "family": resolved.family.model_dump(mode="json"),
                    "recipes": resolved.recipes.model_dump(mode="json"),
                    "provenance": provenance,
                },
            )
        sample_state = _state_records(root / "state" / "samples")
        rejection_state = _state_records(root / "state" / "rejections")
        if sample_state:
            _atomic_jsonl(root / "samples.jsonl", sample_state)
        if rejection_state:
            _atomic_jsonl(root / "rejections.jsonl", rejection_state)
        return cls(root, resolved, catalog, run_id)

    @property
    def samples(self) -> list[dict[str, Any]]:
        return _read_jsonl(self.root / "samples.jsonl")

    @property
    def rejections(self) -> list[dict[str, Any]]:
        return _read_jsonl(self.root / "rejections.jsonl")

    def completed_slots(self) -> set[int]:
        return {int(record["slot"]) for record in self.samples}

    def next_attempt(self, slot: int) -> int:
        attempts = [int(record["candidate_attempt"]) for record in self.rejections if int(record["slot"]) == slot]
        return max(attempts, default=-1) + 1

    def sample_identity(self, slot: int) -> tuple[str, str]:
        suffix = __import__("hashlib").sha256(f"{self.run_id}:{slot}".encode("utf-8")).hexdigest()[:8]
        sample_id = f"{self.resolved.profile.run.label}_{slot:06d}_{suffix}"
        extension = "jpg" if self.resolved.profile.output.image_format == "jpeg" else self.resolved.profile.output.image_format
        return sample_id, f"{sample_id}.{extension}"

    def commit_sample(
        self, record: dict[str, Any], image: np.ndarray, mask_archive: bytes, *, qa: bool
    ) -> dict[str, Any]:
        sample_id, filename = self.sample_identity(int(record["slot"]))
        image_path = self.root / "images" / filename
        temporary = image_path.with_name(image_path.stem + ".tmp" + image_path.suffix)
        started = perf_counter_ns()
        if self.resolved.profile.output.image_format in {"jpg", "jpeg"}:
            Image.fromarray(image).save(temporary, quality=self.resolved.profile.output.jpeg_quality, subsampling=1)
        else:
            Image.fromarray(image).save(temporary)
        os.replace(temporary, image_path)
        image_encode_write_ns = perf_counter_ns() - started
        record = dict(record)
        record["sample_id"] = sample_id
        record["image_path"] = f"images/{filename}"
        mask_path = self.root / "masks" / f"{sample_id}.npz"
        mask_temporary = mask_path.with_suffix(".npz.tmp")
        mask_started = perf_counter_ns()
        with mask_temporary.open("wb") as handle:
            handle.write(mask_archive)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(mask_temporary, mask_path)
        mask_write_ns = perf_counter_ns() - mask_started
        record["mask_evidence"] = {
            **dict(record["mask_evidence"]),
            "path": f"masks/{sample_id}.npz",
        }
        if qa:
            qa_started = perf_counter_ns()
            overlay = _draw_overlay(image, record.get("annotations", []))
            qa_path = self.root / "qa" / f"{sample_id}_overlay.jpg"
            Image.fromarray(overlay).save(qa_path, quality=90)
            policy = self.resolved.family.annotation
            decoded = (
                decode_mask_evidence(mask_archive, record["mask_evidence"])
                if record.get("annotations")
                else {}
            )
            segmentation = _draw_segmentation_qa(
                image,
                record.get("annotations", []),
                decoded,
                alpha_threshold=policy.alpha_threshold,
                semantics=policy.default_mask_semantics,
            )
            Image.fromarray(segmentation).save(self.root / "qa" / f"{sample_id}_segmentation.jpg", quality=90)
            qa_render_ns = perf_counter_ns() - qa_started
        timings = dict(record.get("stage_timings_ns", {}))
        timings["mask_write"] = mask_write_ns
        if qa:
            timings["qa_render"] = qa_render_ns
        timings["image_encode_write"] = image_encode_write_ns
        record["stage_timings_ns"] = timings
        _atomic_json(self.root / "state" / "samples" / f"{int(record['slot']):08d}.json", record)
        _append_jsonl(self.root / "samples.jsonl", record)
        return record

    def append_rejection(self, record: dict[str, Any]) -> None:
        slot = int(record["slot"])
        attempt = int(record["candidate_attempt"])
        _atomic_json(self.root / "state" / "rejections" / f"{slot:08d}_{attempt:08d}.json", record)
        _append_jsonl(self.root / "rejections.jsonl", record)

    def append_metric(self, record: dict[str, Any]) -> None:
        _append_jsonl(self.root / "metrics.jsonl", record)

    def write_summary(self, summary: dict[str, Any]) -> None:
        _atomic_json(self.root / "summary.json", summary)

    def write_qa_index(self) -> None:
        images = sorted((self.root / "qa").glob("*.jpg"))
        cards = "\n".join(
            f'<figure><img src="{image.name}" loading="lazy"><figcaption>{image.stem}</figcaption></figure>' for image in images
        )
        html = f"""<!doctype html><html><head><meta charset=\"utf-8\"><title>Dataset Generator QA</title>
<style>body{{font-family:system-ui;background:#111;color:#eee}}main{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}}img{{max-width:100%;height:auto}}figure{{margin:0;background:#222;padding:10px}}</style></head><body><h1>QA samples</h1><main>{cards}</main></body></html>"""
        (self.root / "qa" / "index.html").write_text(html, encoding="utf-8")
