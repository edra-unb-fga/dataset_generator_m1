import hashlib
import json

import numpy as np
import pytest
from PIL import Image

from dataset_generator_m1.models import SurfaceWearConfig
from dataset_generator_m1.surface_effects import apply_surface_wear, generate_wear_fields
from dataset_generator_m1.wear_materials import prepare_wear_maps


def test_surface_wear_preserves_historical_pixels_trace_and_random_draws():
    """Golden values captured from the pre-extraction production implementation."""
    rgb = np.random.default_rng(123).integers(0, 256, (47, 93, 3), dtype=np.uint8)
    rng = np.random.default_rng(928)
    result, trace = apply_surface_wear(rgb, {'fade': .13, 'dirt': .43, 'scratches': .22,
                                          'marks': 19, 'scratch_width': .003}, rng)
    assert hashlib.sha256(result.tobytes()).hexdigest() == 'bd939cb75ce1d4230f9a785d2b98043cf4fa7932a12494834339eb790039e986'
    assert hashlib.sha256(json.dumps(trace, sort_keys=True).encode()).hexdigest() == '3a511d0f0222f5833f0cc51f5abd1cd285d6915a222ef59227e7678ef215ac2b'
    assert rng.random(4).tolist() == [0.26068696408053915, 0.3558719692234036,
                                     0.17368235185066616, 0.8349734338923682]


def read_maps(manifest):
    return {key: np.asarray(Image.open(value['path'])) for key, value in manifest['maps'].items()}


def test_registered_wear_maps_share_appearance_fields_and_alpha(tmp_path):
    source = np.random.default_rng(5).integers(0, 256, (75, 100, 4), dtype=np.uint8)
    params = {'fade': .1, 'dirt': .4, 'scratches': .3, 'marks': 15}
    first = prepare_wear_maps(source, params, 72, tmp_path/'first', roughness=.37)
    second = prepare_wear_maps(source, params, 72, tmp_path/'second', roughness=.37)
    maps = read_maps(first)
    expected, trace = apply_surface_wear(source[:, :, :3], params, np.random.default_rng(72))
    assert np.array_equal(maps['albedo'][:, :, :3], expected)
    assert np.array_equal(maps['albedo'][:, :, 3], source[:, :, 3])
    assert first['local_marks'] == trace['local_marks']
    assert first['mapping']['origin'] == 'top-left'
    assert first['mapping']['height_role'] == 'bump-only'
    assert all(item.shape[:2] == (75, 100) for item in maps.values())
    fields = generate_wear_fields((75, 100), SurfaceWearConfig.model_validate(params), np.random.default_rng(72))
    rough = np.rint(np.clip(.37+.35*fields.dirt[:, :, 0]-.1*fields.scratches[:, :, 0], 0, 1)*255).astype(np.uint8)
    height = np.rint(np.clip(.5+.08*fields.dirt[:, :, 0]-.12*fields.scratches[:, :, 0], 0, 1)*255).astype(np.uint8)
    assert np.array_equal(maps['roughness'], rough)
    assert np.array_equal(maps['height'], height)
    for name, item in first['maps'].items():
        assert item['sha256'] == second['maps'][name]['sha256']
        assert item['sha256'] == hashlib.sha256(open(item['path'], 'rb').read()).hexdigest()
        assert item['width'] == 100 and item['height'] == 75
        assert item['encoding'] == ('srgb' if name == 'albedo' else 'linear')


def test_pristine_maps_preserve_uv_corners_and_have_flat_channels(tmp_path):
    # An asymmetrical non-square artwork catches accidental transpose/flip/resizing.
    source = np.full((37, 61, 4), 255, np.uint8)
    source[0, 0] = (255, 0, 0, 17)
    source[0, -1] = (0, 255, 0, 61)
    source[-1, 0] = (0, 0, 255, 123)
    source[-1, -1] = (1, 2, 3, 227)
    path = tmp_path/'artwork.png'
    Image.fromarray(source).save(path)
    manifest = prepare_wear_maps(path, {'fade': 0, 'dirt': 0, 'scratches': 0}, 9, tmp_path/'maps')
    maps = read_maps(manifest)
    assert np.array_equal(maps['albedo'], source)
    assert np.all(maps['roughness'] == 128)
    assert np.all(maps['height'] == 128)
    assert manifest['shape'] == [37, 61]


def test_map_input_and_strength_bounds(tmp_path):
    source = np.zeros((3, 5, 3), np.uint8)
    for invalid in (-.1, 1.1, float('nan'), float('inf')):
        with pytest.raises(ValueError, match='roughness'):
            prepare_wear_maps(source, {}, 2, tmp_path/'bad', roughness=invalid)
    for invalid in (np.zeros((3, 5)), np.zeros((3, 5, 3), np.float32)):
        with pytest.raises(ValueError, match='uint8 RGB'):
            prepare_wear_maps(invalid, {}, 2, tmp_path/'bad')
    with pytest.raises(ValueError):
        prepare_wear_maps(source, {'marks': 65}, 2, tmp_path/'bad')
    assert not (tmp_path/'bad').exists()
