import json
from collections import defaultdict
from pathlib import Path

from dataset_generator_m1.blender_pilot import PilotConfig


def test_lighting_candidate_preserves_context_mix_and_explicit_tail():
    root = Path(__file__).resolve().parents[1]
    baseline = json.loads((root / 'experiments/blenderproc/pilot-balanced-candidate.example.json').read_text())
    candidate = json.loads((root / 'experiments/blenderproc/pilot-lighting-refined-candidate.example.json').read_text())
    PilotConfig.model_validate(candidate)
    assert candidate['thickness_metres'] == baseline['thickness_metres'] == 0.005
    contexts = defaultdict(list)
    for member in candidate['procedural']['members']:
        contexts[member['preset']['environment']].append(member)
    assert set(contexts) == {'open', 'outdoor', 'indoor'}
    assert all(sum(item['weight'] for item in members) == 10 for members in contexts.values())
    for members in contexts.values():
        broad, soft, original = members
        assert (broad['weight'], soft['weight'], original['weight']) == (5, 4, 1)
        for ordinary in (broad, soft):
            assert ordinary['preset']['lamp_size_m'][0] > original['preset']['lamp_size_m'][0]
            assert ordinary['preset']['ground_weights'] == original['preset']['ground_weights']
            assert ordinary['preset']['lighting'] == original['preset']['lighting']
        assert broad['preset']['lamp_z_m'] != soft['preset']['lamp_z_m']
        assert broad['preset']['lamp_power_w'] != soft['preset']['lamp_power_w']


def test_optional_indoor_balance_preserves_legacy_and_sampling_streams():
    from dataset_generator_m1.scene_presets import Preset, sample

    root = Path(__file__).resolve().parents[1]
    original = json.loads((root / 'experiments/blenderproc/scene-presets/indoor.json').read_text())
    original['lamp_count'] = [1, 1]
    original['lamp_types'] = [{'value': 'SPOT', 'weight': 1}]
    legacy = Preset.model_validate(original)
    assert 'indoor_light_balance' not in legacy.model_dump(mode='json')
    balance = {'max_total_power_w': 500, 'single_spot_fill': {'power_w': 150, 'size_m': 2, 'location': [0, 0, 3]}}
    configured = Preset.model_validate({**original, 'indoor_light_balance': balance})
    first = sample(legacy, 9182, 2, {}, {}, 3, 2)
    repeat = sample(legacy, 9182, 2, {}, {}, 3, 2)
    changed = sample(configured, 9182, 2, {}, {}, 3, 2)
    assert first == repeat
    assert all(first[k] == changed[k] for k in ('casters','ground_index','environment_geometry','environment_geometry_settings','selected_lighting'))
    before, after = first['treatment']['lamps'], changed['treatment']['lamps']
    assert len(before) == 1 and len(after) == 2
    assert after[0]['power_w'] == min(before[0]['power_w'], 500)
    assert after[0]['location'] == before[0]['location']
    assert after[1]['kind'] == 'AREA' and after[1]['power_w'] == 150
    assert sample(configured, 9182, 2, {}, {}, 3, 2) == changed


def test_balance_caps_multiple_lamps_without_additional_fill():
    from dataset_generator_m1.scene_presets import Preset, sample

    root = Path(__file__).resolve().parents[1]
    raw = json.loads((root / 'experiments/blenderproc/scene-presets/indoor.json').read_text())
    raw.update(lamp_count=[3, 3], lamp_types=[{'value':'AREA','weight':1}], lamp_power_w=[500, 500],
               indoor_light_balance={'max_total_power_w':1200,'single_spot_fill':{'power_w':150,'size_m':2,'location':[0,0,3]}})
    lamps = sample(Preset.model_validate(raw), 10, 0, {}, {}, 3, 2)['treatment']['lamps']
    assert len(lamps) == 3
    assert abs(sum(lamp['power_w'] for lamp in lamps) - 1200) < 1e-7
