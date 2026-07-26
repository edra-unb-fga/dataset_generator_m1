import json

import numpy as np
import pytest

from dataset_generator_m1.filters import apply_pipeline, apply_pipeline_traced, backend_version, validate_transform_specs
from dataset_generator_m1.models import TransformSpec


def test_foreground_appearance_preserves_alpha() -> None:
    image = np.zeros((24, 24, 4), dtype=np.uint8)
    image[:, :, :3] = 120
    image[4:20, 4:20, 3] = 255
    specs = (
        TransformSpec(
            type="HueSaturationValue",
            probability=1.0,
            params={"hue_shift_limit": (1, 1), "sat_shift_limit": (2, 2), "val_shift_limit": (3, 3)},
        ),
    )

    output = apply_pipeline(image, specs, np.random.default_rng(3), preserve_alpha=True)

    assert np.array_equal(output[:, :, 3], image[:, :, 3])
    assert np.all(output[image[:, :, 3] == 0, :3] == 0)


def test_transform_capability_validation_is_version_specific() -> None:
    invalid = (TransformSpec(type="GaussianBlur", params={"obsolete_parameter": 1}),)

    with pytest.raises(ValueError, match=f"Albumentations {backend_version()} does not accept"):
        validate_transform_specs(invalid, "appearance.final")


def test_traced_effects_are_order_independent_and_preserve_alpha() -> None:
    image = np.zeros((24, 24, 4), dtype=np.uint8)
    image[:, :, :3] = 100
    image[3:21, 3:21, 3] = 255
    gamma = TransformSpec(id="gamma", type="RandomGamma", probability=1.0, params={"gamma_limit": (80, 120)})
    brightness = TransformSpec(
        id="brightness",
        type="RandomBrightnessContrast",
        probability=1.0,
        params={"brightness_limit": (-0.2, 0.2), "contrast_limit": (-0.2, 0.2)},
    )

    _, first = apply_pipeline_traced(image, (gamma, brightness), 91, "foreground:0", preserve_alpha=True)
    output, second = apply_pipeline_traced(image, (brightness, gamma), 91, "foreground:0", preserve_alpha=True)

    first_by_id = {trace.id: trace for trace in first}
    second_by_id = {trace.id: trace for trace in second}
    assert first_by_id["gamma"].seed == second_by_id["gamma"].seed
    assert first_by_id["gamma"].applied_params == second_by_id["gamma"].applied_params
    assert first_by_id["brightness"].applied_params == second_by_id["brightness"].applied_params
    assert np.array_equal(output[:, :, 3], image[:, :, 3])


def test_transform_ids_must_be_unique_within_stage() -> None:
    duplicate = (
        TransformSpec(id="same", type="RandomGamma"),
        TransformSpec(id="same", type="MotionBlur"),
    )
    with pytest.raises(ValueError, match="Duplicate transform id"):
        validate_transform_specs(duplicate, "appearance.final")


def test_traced_effect_duration_uses_exclusive_clock_span() -> None:
    times = iter((100, 145))
    image = np.zeros((4, 5, 3), dtype=np.uint8)
    _, traces = apply_pipeline_traced(
        image,
        (TransformSpec(id="skipped", type="RandomGamma", probability=0.0),),
        7,
        "final",
        clock=lambda: next(times),
    )

    assert traces[0].duration_ns == 45
    assert traces[0].input_pixels == 20
    assert traces[0].applied is False


def test_large_sampled_arrays_are_compact_fingerprints() -> None:
    image = np.full((64, 64, 3), 128, dtype=np.uint8)
    _, traces = apply_pipeline_traced(
        image,
        (
            TransformSpec(
                id="noise",
                type="GaussNoise",
                probability=1.0,
                params={"std_range": (0.02, 0.02), "mean_range": (0.0, 0.0), "per_channel": False},
            ),
        ),
        17,
        "background",
    )

    serialized = json.dumps(traces[0].applied_params)
    assert "ndarray-fingerprint" in serialized
    assert len(serialized) < 2_000


def test_random_fog_particle_lists_are_compact() -> None:
    image = np.full((128, 128, 3), 128, dtype=np.uint8)
    _, traces = apply_pipeline_traced(
        image,
        (
            TransformSpec(
                id="fog",
                type="RandomFog",
                probability=1.0,
                params={"alpha_coef": 0.08, "fog_coef_range": (0.8, 0.8)},
            ),
        ),
        18,
        "final",
    )

    serialized = json.dumps(traces[0].applied_params)
    assert "numeric-sequence-fingerprint" in serialized
    assert len(serialized) < 3_000


@pytest.mark.parametrize("depth_mode", ["linear", "diagonal", "radial"])
def test_atmospheric_fog_modes_are_deterministic_and_traced(depth_mode: str) -> None:
    image = np.full((40, 60, 3), 70, dtype=np.uint8)
    spec = TransformSpec(
        id=f"atmospheric-{depth_mode}",
        type="AtmosphericFog",
        probability=1.0,
        params={
            "density_range": (1.25, 1.75),
            "fog_color": (210, 215, 220),
            "depth_mode": depth_mode,
        },
    )

    first, first_traces = apply_pipeline_traced(image, (spec,), 101, "final")
    second, second_traces = apply_pipeline_traced(image, (spec,), 101, "final")

    assert np.array_equal(first, second)
    assert not np.array_equal(first, image)
    assert first_traces[0].applied_params == second_traces[0].applied_params
    sampled = first_traces[0].applied_params[0]
    assert sampled["depth_mode"] == depth_mode
    assert sampled["fog_color"] == [210, 215, 220]
    assert 1.25 <= sampled["density"] <= 1.75


def test_atmospheric_fog_preserves_foreground_alpha_bit_for_bit() -> None:
    image = np.full((32, 32, 4), 90, dtype=np.uint8)
    image[:, :, 3] = np.arange(32, dtype=np.uint8)[:, None] * 8
    original_alpha = image[:, :, 3].copy()
    spec = TransformSpec(
        id="native-fog",
        type="AtmosphericFog",
        params={"density_range": (2.0, 2.0), "fog_color": (230, 230, 230), "depth_mode": "radial"},
    )

    output, _ = apply_pipeline_traced(image, (spec,), 202, "foreground:0", preserve_alpha=True)

    assert np.array_equal(output[:, :, 3], original_alpha)


def test_atmospheric_fog_parameters_do_not_change_when_an_earlier_effect_is_inserted() -> None:
    image = np.full((32, 32, 3), 100, dtype=np.uint8)
    fog = TransformSpec(
        id="stable-fog",
        type="AtmosphericFog",
        params={"density_range": (1.0, 3.0), "fog_color": (200, 205, 210), "depth_mode": "diagonal"},
    )
    earlier = TransformSpec(id="earlier-gamma", type="RandomGamma", params={"gamma_limit": (90, 110)})

    _, fog_only = apply_pipeline_traced(image, (fog,), 303, "final")
    _, with_earlier = apply_pipeline_traced(image, (earlier, fog), 303, "final")

    assert fog_only[0].seed == with_earlier[1].seed
    assert fog_only[0].applied_params == with_earlier[1].applied_params


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"density_range": (2.0, 1.0)}, "density_range"),
        ({"depth_mode": "unknown"}, "depth_mode"),
        ({"fog_color": (255, 255)}, "fog_color"),
        ({"unknown": 1}, "does not accept"),
    ],
)
def test_atmospheric_fog_validation_rejects_invalid_parameters(params: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        validate_transform_specs((TransformSpec(type="AtmosphericFog", params=params),), "appearance.final")
