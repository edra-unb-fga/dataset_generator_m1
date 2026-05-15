import pytest
import numpy as np

from dataset_generator_m1.filters import SUPPORTED_FILTERS, apply_filter_groups


def test_foreground_filters_preserve_alpha_channel():
    image = np.zeros((16, 16, 4), dtype=np.uint8)
    image[:, :, :3] = 120
    image[4:12, 4:12, 3] = 255
    groups = {
        "ColorFilters": {
            "HueSaturationValue": {
                "hue_shift_range": [1, 1],
                "sat_shift_range": [1, 1],
                "val_shift_range": [1, 1],
                "probability": 1.0,
            }
        }
    }

    out = apply_filter_groups(image, groups, np.random.default_rng(1), preserve_alpha=True)

    assert np.array_equal(out[:, :, 3], image[:, :, 3])
    assert np.all(out[image[:, :, 3] == 0, :3] == 0)


@pytest.mark.parametrize(
    "name,params",
    [
        ("HueSaturationValue", {"hue_shift_range": [1, 1], "sat_shift_range": [1, 1], "val_shift_range": [1, 1]}),
        ("RandomBrightnessContrast", {"brightness_range": [0.01, 0.01], "contrast_range": [0.01, 0.01]}),
        ("GaussianBlur", {"blur_limit": [3, 3], "sigma_limit": [0.1, 0.1]}),
        ("GaussNoise", {"std_range": [0.01, 0.01], "mean_range": [0.0, 0.0], "per_channel": False}),
        ("AdditiveNoise", {"noise_type": "gaussian", "spatial_mode": "shared", "noise_params": None}),
        ("RandomGamma", {"gamma_range": [100, 100]}),
        ("PlanckianJitter", {"mode": "blackbody", "temperature_range": [5000, 8500], "sampling_method": "uniform"}),
        ("SaltAndPepper", {"amount_range": [0.01, 0.01], "salt_vs_pepper_range": [0.5, 0.5]}),
        ("MotionBlur", {"blur_range": [3, 3], "allow_shifted": True, "angle_range": [-12, 12], "direction_range": [-0.2, 0.2]}),
        ("PlasmaShadow", {"shadow_intensity_range": [0.1, 0.2], "plasma_size": 64, "roughness": 3.0}),
        ("PlasmaBrightnessContrast", {"brightness_range": [0.01, 0.01], "contrast_range": [0.01, 0.01], "plasma_size": 64, "roughness": 3.0}),
        ("RandomSunFlare", {"flare_roi": [0.0, 0.0, 1.0, 0.5], "src_radius": 20, "src_color": [255, 255, 255], "angle_range": [0.0, 1.0], "num_flare_circles_range": [1, 1], "method": "overlay"}),
        ("Illumination", {"mode": "linear", "intensity_range": [0.01, 0.02], "effect_type": "both", "angle_range": [0, 360], "center_range": [0.25, 0.75], "sigma_range": [0.2, 0.6]}),
        ("AtmosphericFog", {"density_range": [0.05, 0.05], "fog_color": [255, 255, 255], "depth_mode": "linear"}),
    ],
)
def test_all_documented_filters_are_allowed_and_apply(name, params):
    image = np.full((96, 96, 3), 128, dtype=np.uint8)
    groups = {"AnyGroup": {name: {**params, "probability": 1.0}}}

    out = apply_filter_groups(image, groups, np.random.default_rng(1))

    assert name in SUPPORTED_FILTERS
    assert out.shape == image.shape
    assert out.dtype == np.uint8
