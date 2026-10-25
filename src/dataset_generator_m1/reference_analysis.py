"""Audit supplied references and verify explicit pinhole projections; never fit calibration."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

from .analysis_contracts import ProjectionManifest, ReferenceManifest
from .analysis_reports import file_hash, fresh_output, local_artifact, read_json, write_report
from .evaluation_io import valid_box


def audit_references(manifest_file, output_dir):
    source = Path(manifest_file).resolve()
    manifest = ReferenceManifest.model_validate(read_json(source))
    if len({r.id for r in manifest.images}) != len(manifest.images):
        raise ValueError("Reference image IDs must be unique")
    rows, copies, duplicates = [], [], defaultdict(list)
    for row in manifest.images:
        path = local_artifact(source.parent, row.path)
        with Image.open(path) as image:
            rgb = np.asarray(image.convert("RGB"))
        height, width = rgb.shape[:2]
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        sha = file_hash(path)
        duplicates[sha].append(row.id)
        boxes = []
        for annotation in row.annotations:
            x, y, w, h = valid_box(annotation.get("bbox"), width, height)
            boxes.append({"class_name": annotation.get("class_name", "unknown"), "bbox": [x, y, w, h],
                          "width_px": w, "height_px": h, "relative_width": w/width, "relative_height": h/height,
                          "relative_box_area": w*h/(width*height)})
        rows.append({"id": row.id, "sha256": sha, "image_size": [width, height],
                     "capture_session": row.capture_session or "unknown", "location": row.location or "unknown",
                     "conditions": row.conditions, "targets": boxes,
                     "observables": {"mean_luma_8bit": float(gray.mean()), "std_luma_8bit": float(gray.std()),
                                     "mean_rgb_8bit": rgb.mean(axis=(0, 1)).tolist(),
                                     "low_clip_fraction": float(np.mean(gray <= 1)), "high_clip_fraction": float(np.mean(gray >= 254)),
                                     "laplacian_variance_proxy": float(cv2.Laplacian(gray, cv2.CV_64F).var())}})
        if len(copies) < 16:
            canvas = Image.fromarray(rgb)
            draw = ImageDraw.Draw(canvas)
            for box in boxes:
                x, y, w, h = box["bbox"]
                draw.rectangle((x, y, x+w, y+h), outline="#00ba83", width=2)
            canvas.thumbnail((960, 960))
            copies.append((canvas, row.id))
    output = fresh_output(output_dir)
    output.joinpath("previews").mkdir()
    cards = []
    for i, (image, label) in enumerate(copies):
        name = f"previews/{i:03d}.jpg"
        image.save(output / name, quality=90)
        cards.append((name, label))
    warnings = ["Image statistics are observables, not estimated sensor noise, optical blur, camera pose or calibrated effect probabilities.",
                "Duplicate detection cannot establish capture-session/location independence; unknown groups remain unknown.",
                "No calibration fit or real-image detector benefit is established by this audit."]
    return write_report(output, {"schema_version": 1, "kind": "reference-audit", "status": "complete_with_warnings",
                                 "domain": manifest.domain, "role": manifest.role, "images": rows,
                                 "input_manifest_sha256": file_hash(source),
                                 "duplicate_groups": [v for v in duplicates.values() if len(v) > 1],
                                 "physical_measurements": manifest.physical_measurements,
                                 "warnings": warnings, "missing_evidence": ["verified target metric dimensions", "camera intrinsics and capture geometry", "deployment capture-effect distributions", "real labels and external predictions"]},
                        "Reference evidence audit", images=cards)


def check_projection(manifest_file, output_dir):
    source = Path(manifest_file)
    manifest = ProjectionManifest.model_validate(read_json(source))
    k = np.asarray(manifest.camera_matrix, dtype=float)
    pose = np.asarray(manifest.world_to_camera, dtype=float)
    width, height = manifest.image_size
    w, h = manifest.target_size_m
    if k.shape != (3, 3) or pose.shape != (4, 4) or not np.isfinite(k).all() or not np.isfinite(pose).all():
        raise ValueError("Projection requires finite 3x3 intrinsics and 4x4 world_to_camera")
    if min(width, height, w, h) <= 0 or k[0, 0] <= 0 or k[1, 1] <= 0 or not np.allclose(k[2], [0, 0, 1]):
        raise ValueError("Image/target dimensions and focal lengths must be positive; intrinsics last row is [0,0,1]")
    rotation = pose[:3, :3]
    if not np.allclose(pose[3], [0, 0, 0, 1]) or not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-6) or not np.isclose(np.linalg.det(rotation), 1, atol=1e-6):
        raise ValueError("world_to_camera must be a rigid right-handed transform")
    corners = np.array([[-w/2, -h/2, 0, 1], [w/2, -h/2, 0, 1], [w/2, h/2, 0, 1], [-w/2, h/2, 0, 1]])
    camera = (pose @ corners.T)[:3].T
    if np.any(camera[:, 2] <= 1e-9):
        raise ValueError("Target corners must lie in front of the camera")
    pixels = (k @ camera.T).T
    pixels = pixels[:, :2] / pixels[:, 2:]
    residuals = None
    if manifest.observed_corners_px is not None:
        observed = np.asarray(manifest.observed_corners_px, dtype=float)
        if observed.shape != (4, 2) or not np.isfinite(observed).all():
            raise ValueError("Observed corners need four finite xy pairs in the declared order")
        distances = np.linalg.norm(observed - pixels, axis=1)
        residuals = {"per_corner_px": distances.tolist(), "rms_px": float(np.sqrt(np.mean(distances**2))), "max_px": float(distances.max())}
    output = fresh_output(output_dir)
    canvas = Image.new("RGB", (width, height), "#f5f5f2")
    draw = ImageDraw.Draw(canvas)
    draw.polygon([tuple(p) for p in pixels], outline="#047e65", width=3)
    for i, point in enumerate(pixels):
        draw.text(tuple(point), str(i), fill="#182532")
    canvas.thumbnail((1200, 1200))
    canvas.save(output / "projection.png")
    warnings = ["Forward projection check only: supplied parameters are not fitted calibration or evidence of deployment camera accuracy.",
                "OpenCV camera axes: x right, y down, z forward; centered target on world Z=0, corners (-x,-y),(+x,-y),(+x,+y),(-x,+y). Undistorted pinhole image coordinates only."]
    outside = bool(np.any((pixels[:, 0] < 0) | (pixels[:, 0] > width) | (pixels[:, 1] < 0) | (pixels[:, 1] > height)))
    if outside:
        warnings.append("Some projected corners lie outside the declared image.")
    return write_report(output, {"schema_version": 1, "kind": "projection-check", "status": "complete_with_warnings",
                                 "input_manifest_sha256": file_hash(source), "parameter_provenance": manifest.provenance,
                                 "image_size": [width, height], "target_size_m": [w, h], "projected_corners_px": pixels.tolist(),
                                 "residuals": residuals, "warnings": warnings}, "Supplied-camera planar projection", images=[("projection.png", "Projected target corners")])
