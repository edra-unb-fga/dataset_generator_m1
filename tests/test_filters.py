import numpy as np

from dataset_generator_m1.filters import apply_filter_groups


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

