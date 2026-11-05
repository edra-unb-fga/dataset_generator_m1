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
