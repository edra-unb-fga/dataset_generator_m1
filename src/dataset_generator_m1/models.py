from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RunConfig(StrictModel):
    label: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    tags: tuple[str, ...] = ()
    num_images: int = Field(default=10, ge=1)
    seed: int = 42
    negative_fraction: float = Field(default=0.0, ge=0.0, le=1.0)
    max_candidate_attempts: int = Field(default=10, ge=1)
    max_wall_seconds: float | None = Field(default=None, gt=0)
    max_rejection_rate: float | None = Field(default=None, ge=0.0, le=1.0)


class AssetSourceConfig(StrictModel):
    paths: tuple[str, ...]
    recursive: bool = True
    catalog_file: str | None = None
    group_weights: dict[str, float] = Field(default_factory=dict)
    asset_weights: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_weights(self) -> "AssetSourceConfig":
        for name, weights in (("group_weights", self.group_weights), ("asset_weights", self.asset_weights)):
            if any(value < 0 for value in weights.values()):
                raise ValueError(f"{name} values must be non-negative")
            if weights and not any(value > 0 for value in weights.values()):
                raise ValueError(f"{name} must contain a positive value")
        return self


class AssetsConfig(StrictModel):
    backgrounds: AssetSourceConfig
    foregrounds: AssetSourceConfig


class OutputConfig(StrictModel):
    image_size: tuple[int, int] = (1280, 1280)
    image_format: Literal["jpg", "jpeg", "png"] = "jpg"
    jpeg_quality: int = Field(default=95, ge=1, le=100)

    @model_validator(mode="after")
    def validate_image_size(self) -> "OutputConfig":
        if len(self.image_size) != 2 or min(self.image_size) < 1:
            raise ValueError("image_size must be [width, height] with positive values")
        return self


def _ordered_range(value: tuple[float, float], name: str, minimum: float | None = None) -> None:
    if len(value) != 2 or value[0] > value[1]:
        raise ValueError(f"{name} must be an ordered two-item range")
    if minimum is not None and value[0] < minimum:
        raise ValueError(f"{name} values must be >= {minimum}")


class SamplingConfig(StrictModel):
    instances_per_image: tuple[int, int] = (1, 2)
    foreground_size: tuple[float, float] = (0.20, 0.45)
    bbox_spacing: float = Field(default=0.015, ge=0.0)
    placement_attempts: int = Field(default=50, ge=1)
    min_visible_bbox_fraction: float = Field(default=0.70, gt=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_ranges(self) -> "SamplingConfig":
        if len(self.instances_per_image) != 2 or self.instances_per_image[0] < 0 or self.instances_per_image[0] > self.instances_per_image[1]:
            raise ValueError("instances_per_image must be an ordered non-negative range")
        _ordered_range(self.foreground_size, "foreground_size", 0.001)
        return self


class CameraConfig(StrictModel):
    crop_scale: tuple[float, float] = (1.0, 1.0)
    center_jitter_x: tuple[float, float] = (0.0, 0.0)
    center_jitter_y: tuple[float, float] = (0.0, 0.0)

    @model_validator(mode="after")
    def validate_ranges(self) -> "CameraConfig":
        _ordered_range(self.crop_scale, "crop_scale", 0.1)
        _ordered_range(self.center_jitter_x, "center_jitter_x")
        _ordered_range(self.center_jitter_y, "center_jitter_y")
        return self


class PerspectiveConfig(StrictModel):
    probability: float = Field(default=0.25, ge=0.0, le=1.0)
    corner_offset_x: tuple[float, float] = (-0.02, 0.02)
    corner_offset_y: tuple[float, float] = (-0.02, 0.02)
    min_area_fraction: float = Field(default=0.75, gt=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_ranges(self) -> "PerspectiveConfig":
        _ordered_range(self.corner_offset_x, "corner_offset_x")
        _ordered_range(self.corner_offset_y, "corner_offset_y")
        return self


class BackgroundAffineConfig(StrictModel):
    rotation_degrees: tuple[float, float] = (0.0, 0.0)
    scale: tuple[float, float] = (1.0, 1.0)
    translation_x: tuple[float, float] = (0.0, 0.0)
    translation_y: tuple[float, float] = (0.0, 0.0)

    @model_validator(mode="after")
    def validate_ranges(self) -> "BackgroundAffineConfig":
        _ordered_range(self.rotation_degrees, "rotation_degrees")
        _ordered_range(self.scale, "scale", 0.01)
        _ordered_range(self.translation_x, "translation_x")
        _ordered_range(self.translation_y, "translation_y")
        return self


class SceneConfig(StrictModel):
    canvas_scale: float = Field(default=2.0, ge=1.25)
    camera: CameraConfig = Field(default_factory=CameraConfig)
    perspective: PerspectiveConfig = Field(default_factory=PerspectiveConfig)
    background_affine: BackgroundAffineConfig = Field(default_factory=BackgroundAffineConfig)


class TransformSpec(StrictModel):
    id: str | None = Field(default=None, min_length=1, pattern=r"^[A-Za-z][A-Za-z0-9._-]*$")
    type: str = Field(min_length=1)
    probability: float = Field(default=1.0, ge=0.0, le=1.0)
    params: dict[str, Any] = Field(default_factory=dict)


class AppearanceConfig(StrictModel):
    background: tuple[TransformSpec, ...] = ()
    foreground: tuple[TransformSpec, ...] = ()
    final: tuple[TransformSpec, ...] = ()


class BackgroundSynthesisConfig(StrictModel):
    recipe_file: str
    recipe_weights: dict[str, float]

    @model_validator(mode="after")
    def validate_weights(self) -> "BackgroundSynthesisConfig":
        if not self.recipe_weights or any(weight < 0 for weight in self.recipe_weights.values()) or not any(weight > 0 for weight in self.recipe_weights.values()):
            raise ValueError("recipe_weights must contain at least one positive, non-negative weight")
        return self


class TelemetryConfig(StrictModel):
    refresh_hz: float = Field(default=3.0, ge=0.5, le=10.0)
    resource_interval_seconds: float = Field(default=1.0, ge=0.25)
    plain_interval_seconds: float = Field(default=5.0, ge=0.5)


class ReportConfig(StrictModel):
    qa_samples: int = Field(default=16, ge=0)


class GenerationProfile(StrictModel):
    schema_version: Literal[1]
    family: Literal["landing", "manometro"]
    run: RunConfig
    assets: AssetsConfig
    output: OutputConfig = Field(default_factory=OutputConfig)
    sampling: SamplingConfig = Field(default_factory=SamplingConfig)
    scene: SceneConfig = Field(default_factory=SceneConfig)
    background_synthesis: BackgroundSynthesisConfig
    appearance: AppearanceConfig = Field(default_factory=AppearanceConfig)
    telemetry: TelemetryConfig = Field(default_factory=TelemetryConfig)
    report: ReportConfig = Field(default_factory=ReportConfig)


class ClassMappingRule(StrictModel):
    pattern: str
    class_template: str


class RotationPolicy(StrictModel):
    mode: Literal["square", "circle"]
    angle_degrees: tuple[float, float]
    probability: float = Field(default=1.0, ge=0.0, le=1.0)


class FamilyDefinition(StrictModel):
    schema_version: Literal[1]
    name: Literal["landing", "manometro"]
    classes: tuple[str, ...]
    class_mapping: tuple[ClassMappingRule, ...]
    rotation: RotationPolicy

    @model_validator(mode="after")
    def validate_classes(self) -> "FamilyDefinition":
        if not self.classes or len(set(self.classes)) != len(self.classes):
            raise ValueError("family classes must be non-empty and unique")
        return self


RecipeOp = Literal[
    "sample_asset",
    "resize_crop",
    "colorspace_convert",
    "channel_extract",
    "channel_compose",
    "palette_transfer",
    "mask_normalize",
    "linear_blend",
    "multiband_blend",
    "displace",
]


class RecipeNode(StrictModel):
    id: str = Field(min_length=1, pattern=r"^[A-Za-z_][A-Za-z0-9_-]*$")
    op: RecipeOp
    inputs: dict[str, str] = Field(default_factory=dict)
    params: dict[str, Any] = Field(default_factory=dict)


class BackgroundRecipe(StrictModel):
    version: int = Field(default=1, ge=1)
    experimental: bool = False
    tileable: bool = False
    allowed_cross_group_pairs: tuple[tuple[str, str], ...] = ()
    nodes: tuple[RecipeNode, ...]
    output: str

    @model_validator(mode="after")
    def validate_graph(self) -> "BackgroundRecipe":
        required_inputs = {
            "sample_asset": set(),
            "resize_crop": {"image"},
            "colorspace_convert": {"image"},
            "channel_extract": {"image"},
            "channel_compose": {"channel_0", "channel_1", "channel_2"},
            "palette_transfer": {"image", "palette"},
            "mask_normalize": {"mask"},
            "linear_blend": {"first", "second", "mask"},
            "multiband_blend": {"first", "second", "mask"},
            "displace": {"image", "map_x", "map_y"},
        }
        allowed_params = {
            "sample_asset": {"group", "same_group_as", "distinct_from", "role"},
            "resize_crop": set(),
            "colorspace_convert": {"from", "to"},
            "channel_extract": {"color_space", "channel"},
            "channel_compose": {"color_space"},
            "palette_transfer": {"strength"},
            "mask_normalize": {"percentiles", "invert", "gamma", "curve", "threshold", "blur_fraction"},
            "linear_blend": set(),
            "multiband_blend": {"levels"},
            "displace": {"amplitude_fraction", "blur_fraction"},
        }
        input_types = {
            "resize_crop": {"image": {"asset", "image"}},
            "colorspace_convert": {"image": {"image"}},
            "channel_extract": {"image": {"image"}},
            "channel_compose": {"channel_0": {"scalar"}, "channel_1": {"scalar"}, "channel_2": {"scalar"}},
            "palette_transfer": {"image": {"image"}, "palette": {"image"}},
            "mask_normalize": {"mask": {"scalar"}},
            "linear_blend": {"first": {"image"}, "second": {"image"}, "mask": {"scalar"}},
            "multiband_blend": {"first": {"image"}, "second": {"image"}, "mask": {"scalar"}},
            "displace": {"image": {"image"}, "map_x": {"scalar"}, "map_y": {"scalar"}},
        }
        output_types = {
            "sample_asset": "asset",
            "resize_crop": "image",
            "colorspace_convert": "image",
            "channel_extract": "scalar",
            "channel_compose": "image",
            "palette_transfer": "image",
            "mask_normalize": "scalar",
            "linear_blend": "image",
            "multiband_blend": "image",
            "displace": "image",
        }
        seen: set[str] = set()
        node_types: dict[str, str] = {}
        for node in self.nodes:
            if node.id in seen:
                raise ValueError(f"duplicate recipe node id: {node.id}")
            missing = set(node.inputs.values()) - seen
            if missing:
                raise ValueError(f"recipe node {node.id} references later or unknown nodes: {sorted(missing)}")
            expected = required_inputs[node.op]
            if set(node.inputs) != expected:
                raise ValueError(f"recipe node {node.id} inputs must be exactly {sorted(expected)}")
            for input_name, reference in node.inputs.items():
                actual_type = node_types[reference]
                if actual_type not in input_types[node.op][input_name]:
                    raise ValueError(
                        f"recipe node {node.id} input {input_name} expects {sorted(input_types[node.op][input_name])}, "
                        f"got {actual_type} from {reference}"
                    )
            unknown_params = set(node.params) - allowed_params[node.op]
            if unknown_params:
                raise ValueError(f"recipe node {node.id} has unsupported parameters: {sorted(unknown_params)}")
            for reference in [node.params.get("same_group_as"), *node.params.get("distinct_from", [])]:
                if reference is not None and str(reference) not in seen:
                    raise ValueError(f"recipe node {node.id} parameter references later or unknown node: {reference}")
            color_space = node.params.get("color_space")
            if color_space is not None and str(color_space).lower() not in {"rgb", "lab", "hsv"}:
                raise ValueError(f"recipe node {node.id} has unsupported color_space {color_space}")
            if node.op == "colorspace_convert":
                for key in ("from", "to"):
                    if str(node.params.get(key, "RGB")).lower() not in {"rgb", "lab", "hsv"}:
                        raise ValueError(f"recipe node {node.id} has unsupported {key} color space")
            if node.op == "channel_extract" and int(node.params.get("channel", 0)) not in {0, 1, 2}:
                raise ValueError(f"recipe node {node.id} channel must be 0, 1, or 2")
            seen.add(node.id)
            node_types[node.id] = output_types[node.op]
        if self.output not in seen:
            raise ValueError(f"recipe output references unknown node: {self.output}")
        return self


class RecipeCatalog(StrictModel):
    schema_version: Literal[1]
    recipes: dict[str, BackgroundRecipe]


class BackgroundCatalogEntry(StrictModel):
    path: str
    aliases: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    excluded: bool = False
    seamless: bool | None = None
    texture_kind: Literal["micro", "structured"] | None = None
    approved_roles: tuple[str, ...] = ()


class BackgroundCatalogMetadata(StrictModel):
    schema_version: Literal[1]
    assets: tuple[BackgroundCatalogEntry, ...] = ()


class VariantCatalog(StrictModel):
    schema_version: Literal[1]
    variants: dict[str, dict[str, Any]]

    @model_validator(mode="after")
    def validate_variants(self) -> "VariantCatalog":
        if not self.variants:
            raise ValueError("variant catalog must contain at least one named variant")
        return self


class ResolvedProfile(StrictModel):
    profile: GenerationProfile
    family: FamilyDefinition
    recipes: RecipeCatalog
    config_path: Path
    recipe_path: Path
    contract_hash: str
