import numpy as np
import pytest
from dataset_generator_m1.background_adaptation import adapt_foreground_to_background


def test_deterministic_context_and_alpha_preserved():
    rgb = np.full((60, 80, 3), 120, np.uint8)
    alpha = np.zeros((60, 80), np.uint8)
    alpha[20:40, 30:50] = 255
    alpha[20, 30] = 64
    background = np.full_like(rgb, [230, 70, 30])
    old_rgb, old_alpha, old_bg = rgb.copy(), alpha.copy(), background.copy()
    out, evidence = adapt_foreground_to_background(np.dstack((rgb, alpha)), background, max_brightness_shift=1, max_color_shift=1, strength=.3, radius_fraction=.1)
    other, repeat = adapt_foreground_to_background(np.dstack((rgb, alpha)), background, max_brightness_shift=1, max_color_shift=1, strength=.3, radius_fraction=.1)
    assert np.array_equal(out, other) and evidence == repeat
    assert np.array_equal(rgb, old_rgb) and np.array_equal(alpha, old_alpha) and np.array_equal(background, old_bg)
    assert np.array_equal(out[..., :3][alpha == 0], rgb[alpha == 0])
    assert evidence['background_fallback'] is None
    assert out[25, 35, 0] > 120 and out[25, 35, 2] < 120
    assert np.array_equal(out[25, 35], out[35, 45])


def test_excludes_support_from_background_statistics():
    rgb = np.full((20, 20, 3), 100, np.uint8)
    alpha = np.zeros((20, 20), np.uint8); alpha[8:12, 8:12] = 255
    background = np.full_like(rgb, 200); background[8:12, 8:12] = 0
    out, evidence = adapt_foreground_to_background(np.dstack((rgb, alpha)), background, max_brightness_shift=1, max_color_shift=1, strength=.5, radius_fraction=.2)
    assert np.all(out[9, 9, :3] == 150)
    assert evidence['background_fallback'] is None


def test_empty_and_fully_covered_fallbacks():
    rgb = np.full((4, 4, 3), 100, np.uint8)
    bg = np.full_like(rgb, 200)
    alpha = np.zeros((4, 4), np.uint8)
    out, evidence = adapt_foreground_to_background(np.dstack((rgb, alpha)), bg, max_brightness_shift=1, max_color_shift=1, strength=.5, radius_fraction=.1)
    assert np.array_equal(out[..., :3], rgb) and evidence['background_fallback'] == 'empty_foreground'
    alpha[:] = 255
    out, evidence = adapt_foreground_to_background(np.dstack((rgb, alpha)), bg, max_brightness_shift=1, max_color_shift=1, strength=.5, radius_fraction=.1)
    assert np.array_equal(out[..., :3], rgb) and evidence['background_fallback'] == 'no_local_background'


@pytest.mark.parametrize('strength', [-.1, 2.1, float('nan')])
def test_invalid_strength_rejected(strength):
    with pytest.raises(ValueError):
        adapt_foreground_to_background(np.zeros((1, 1, 4), np.uint8), np.zeros((1, 1, 3), np.uint8), strength=strength, radius_fraction=.1, max_brightness_shift=.1, max_color_shift=.1)
