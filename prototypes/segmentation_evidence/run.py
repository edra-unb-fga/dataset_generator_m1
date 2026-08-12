from __future__ import annotations

import io
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "outputs" / "prototypes" / "segmentation-evidence"


def fixtures() -> dict[str, np.ndarray]:
    masks: dict[str, np.ndarray] = {}
    circle = np.zeros((256, 256), np.uint8)
    cv2.circle(circle, (128, 128), 91, 255, -1, lineType=cv2.LINE_AA)
    masks["circle"] = circle
    square = np.zeros_like(circle)
    cv2.fillConvexPoly(square, np.array([[35, 60], [218, 31], [229, 216], [48, 224]]), 255, lineType=cv2.LINE_AA)
    masks["perspective-square"] = square
    hole = circle.copy()
    cv2.circle(hole, (128, 128), 32, 0, -1, lineType=cv2.LINE_AA)
    masks["hole"] = hole
    disconnected = np.zeros_like(circle)
    cv2.circle(disconnected, (77, 128), 42, 255, -1)
    cv2.circle(disconnected, (181, 128), 31, 255, -1)
    masks["disconnected"] = disconnected
    outer = np.zeros_like(circle)
    cv2.circle(outer, (128, 128), 103, 255, -1, lineType=cv2.LINE_AA)
    inner = np.zeros_like(circle)
    cv2.circle(inner, (128, 128), 39, 255, -1, lineType=cv2.LINE_AA)
    visible = np.rint(outer.astype(np.float32) * (1.0 - inner.astype(np.float32) / 255.0)).astype(np.uint8)
    masks["overlap-full"] = outer
    masks["overlap-visible"] = visible
    actual = {
        "actual-landing": ROOT / "foregrounds" / "landing_foregrounds" / "gabaritos" / "estrela_gabarito_3.png",
        "actual-manometro": ROOT / "foregrounds" / "manometro_foregrounds" / "0-20" / "manometer_0_0.png",
    }
    for name, path in actual.items():
        image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if image is None:
            raise FileNotFoundError(path)
        masks[name] = image[:, :, 3] if image.shape[2] == 4 else np.full(image.shape[:2], 255, np.uint8)
    return masks


def cropped(mask: np.ndarray) -> tuple[np.ndarray, tuple[int, int]]:
    ys, xs = np.where(mask > 0)
    if not len(xs):
        return mask[:0, :0], (0, 0)
    x1, x2, y1, y2 = int(xs.min()), int(xs.max()) + 1, int(ys.min()), int(ys.max()) + 1
    return mask[y1:y2, x1:x2], (x1, y1)


def mask_iou(left: np.ndarray, right: np.ndarray) -> float:
    union = np.logical_or(left, right).sum()
    return 1.0 if union == 0 else float(np.logical_and(left, right).sum() / union)


def merged_contour(binary: np.ndarray) -> tuple[np.ndarray, int, int]:
    contours, hierarchy = cv2.findContours(binary, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return np.empty((0, 2), np.int32), 0, 0
    holes = 0 if hierarchy is None else sum(1 for item in hierarchy[0] if item[3] >= 0)
    outer = [contour[:, 0, :] for index, contour in enumerate(contours) if hierarchy is None or hierarchy[0][index][3] < 0]
    outer.sort(key=lambda points: abs(cv2.contourArea(points)), reverse=True)
    merged = outer[0]
    for segment in outer[1:]:
        distances = ((merged[:, None, :] - segment[None, :, :]) ** 2).sum(axis=2)
        left, right = np.unravel_index(int(np.argmin(distances)), distances.shape)
        loop = np.concatenate([segment[right:], segment[: right + 1], merged[left : left + 1]])
        merged = np.concatenate([merged[: left + 1], loop, merged[left + 1 :]])
    return merged, len(outer), holes


def polygonize(mask: np.ndarray) -> dict[str, object]:
    binary = (mask > 8).astype(np.uint8)
    contour, components, holes = merged_contour(binary)
    if len(contour) < 3:
        return {"polygon": contour, "reconstruction": np.zeros_like(binary), "iou": 0.0, "area_error": 1.0, "components": components, "holes": holes}
    source_area = max(1, int(binary.sum()))
    best = contour
    best_reconstruction = np.zeros_like(binary)
    cv2.fillPoly(best_reconstruction, [best.astype(np.int32)], 1)
    for epsilon in np.linspace(0.25, 8.0, 32):
        candidate = cv2.approxPolyDP(contour.reshape((-1, 1, 2)), float(epsilon), True)[:, 0, :]
        if len(candidate) < 3:
            continue
        reconstructed = np.zeros_like(binary)
        cv2.fillPoly(reconstructed, [candidate.astype(np.int32)], 1)
        iou = mask_iou(binary, reconstructed)
        area_error = abs(int(reconstructed.sum()) - source_area) / source_area
        if iou >= 0.995 and area_error <= 0.01:
            best, best_reconstruction = candidate, reconstructed
    achieved_iou = mask_iou(binary, best_reconstruction)
    area_error = abs(int(best_reconstruction.sum()) - source_area) / source_area
    return {"polygon": best, "reconstruction": best_reconstruction, "iou": achieved_iou, "area_error": area_error, "components": components, "holes": holes}


def panel(name: str, mask: np.ndarray, result: dict[str, object]) -> Image.Image:
    binary = ((mask > 8) * 255).astype(np.uint8)
    reconstruction = (np.asarray(result["reconstruction"]) * 255).astype(np.uint8)
    difference = cv2.absdiff(binary, reconstruction)
    triptych = np.concatenate([binary, reconstruction, difference], axis=1)
    image = Image.fromarray(triptych).convert("RGB")
    canvas = Image.new("RGB", (triptych.shape[1], triptych.shape[0] + 48), "#111827")
    canvas.paste(image, (0, 48))
    ImageDraw.Draw(canvas).text((8, 8), f"{name} | points={len(result['polygon'])} IoU={result['iou']:.5f} area={result['area_error']:.3%} holes={result['holes']} parts={result['components']}", fill="white")
    return canvas


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    masks = fixtures()
    archive_values: dict[str, np.ndarray] = {}
    origins: dict[str, tuple[int, int]] = {}
    for name, mask in masks.items():
        archive_values[name], origins[name] = cropped(mask)
    raw_bytes = sum(value.nbytes for value in archive_values.values())
    buffer = io.BytesIO()
    np.savez_compressed(buffer, **archive_values)
    results = {name: polygonize(mask) for name, mask in masks.items()}
    report = {
        "question": "Can cropped alpha archives and bounded polygons preserve the required evidence?",
        "archive": {"raw_bytes": raw_bytes, "compressed_bytes": len(buffer.getvalue()), "ratio": len(buffer.getvalue()) / raw_bytes, "origins": origins},
        "fixtures": {
            name: {key: value for key, value in result.items() if key not in {"polygon", "reconstruction"}} | {"points": len(result["polygon"])}
            for name, result in results.items()
        },
        "verdict": "Use cropped uint8 coverage archives as canonical evidence; use polygons as measured, warning-bearing export projections.",
    }
    (OUTPUT / "verdict.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    panels = [panel(name, masks[name], results[name]) for name in masks]
    sheet = Image.new("RGB", (panels[0].width, sum(item.height for item in panels)), "#111827")
    y = 0
    for item in panels:
        sheet.paste(item, (0, y))
        y += item.height
    sheet.save(OUTPUT / "contact-sheet.png")
    print(json.dumps(report, indent=2))
    print(f"Contact sheet: {OUTPUT / 'contact-sheet.png'}")


if __name__ == "__main__":
    main()
