import importlib.util
import json
from pathlib import Path
import sys

import pytest

from dataset_generator_m1.config import load_profile
from dataset_generator_m1.renderer_version import contract_profile

sys.path.insert(0, str(Path('scripts').resolve()))
spec = importlib.util.spec_from_file_location('linear_timing', 'scripts/study_linear_compositing_timing.py')
timing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(timing)


def test_matrix_profiles_change_only_compositing_and_keep_configured_policy():
    matrix = timing.load_matrix('experiments/planar/linear-compositing-timing.json')
    base = load_profile(matrix['config'])
    a = timing.profile_for(base, matrix, 'legacy', matrix['measured_samples'])
    b = timing.profile_for(base, matrix, 'linear-srgb', matrix['measured_samples'])
    old, new = contract_profile(a.profile), contract_profile(b.profile)
    assert new['scene'].pop('compositing') == 'linear-srgb'
    assert old == new
    assert a.profile.scene.occlusion.probability == 1
    assert a.profile.execution.workers == 4 and a.profile.execution.native_threads == 1
    assert a.profile.run.num_images == b.profile.run.num_images == 4
    assert a.contract_hash != b.contract_hash


@pytest.mark.parametrize('guards', [
    {'min_available_gib': 1, 'rss_limit_gib': 10, 'max_swap_out_mib': 16},
    {'min_available_gib': 2, 'rss_limit_gib': 11, 'max_swap_out_mib': 16},
    {'min_available_gib': float('nan'), 'rss_limit_gib': 10, 'max_swap_out_mib': 16},
])
def test_guards_cannot_be_weakened(tmp_path, guards):
    matrix = json.loads(Path('experiments/planar/linear-compositing-timing.json').read_text())
    matrix['guards'] = guards
    path = tmp_path / 'matrix.json'
    path.write_text(json.dumps(matrix))
    with pytest.raises(ValueError):
        timing.load_matrix(path)
