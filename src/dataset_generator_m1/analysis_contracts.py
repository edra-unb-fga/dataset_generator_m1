"""Versioned public inputs for offline analysis; no model-runtime dependency."""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AnalysisInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    schema_version: Literal[1]


class EvaluationManifest(AnalysisInput):
    format: Literal["coco", "pool", "yolo-export"]
    domain: Literal["real", "synthetic"]
    role: Literal["development", "held-out", "regression"]
    source: str = "."
    annotation_semantics: Literal["visible", "full", "unknown"] = "unknown"
    ground_truth: str | None = None
    images_root: str = "."
    split: str | None = None
    pool_bindings: dict[str, str] = Field(default_factory=dict)
    metadata_file: str | None = None
    training_provenance: dict[str, Any] | Literal["unknown"] = "unknown"


class PredictionManifest(AnalysisInput):
    dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    predictions: str = Field(min_length=1)
    image_ids: list[int]
    allow_partial: bool = False
    model: dict[str, Any] | None = None


class ReferenceImage(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    id: str = Field(min_length=1)
    path: str = Field(min_length=1)
    capture_session: str | None = None
    location: str | None = None
    annotations: list[dict[str, Any]] = Field(default_factory=list)
    conditions: dict[str, Any] = Field(default_factory=dict)


class ReferenceManifest(AnalysisInput):
    domain: Literal["real", "synthetic"]
    role: Literal["development", "held-out", "regression"]
    images: list[ReferenceImage] = Field(min_length=1)
    physical_measurements: dict[str, Any] = Field(default_factory=dict)


class ProjectionManifest(AnalysisInput):
    camera_matrix: list[list[float]]
    world_to_camera: list[list[float]]
    target_size_m: tuple[float, float]
    image_size: tuple[int, int]
    observed_corners_px: list[list[float]] | None = None
    image_space: Literal["undistorted"] = "undistorted"
    provenance: Literal["measured", "configured", "inferred", "unknown"] = "configured"
