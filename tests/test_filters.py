import numpy as np
import pytest

from dataset_generator_m1.filters import apply_pipeline, backend_version, validate_transform_specs
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
