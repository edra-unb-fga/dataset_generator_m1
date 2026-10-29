import json
from pathlib import Path
import sys
import numpy as np
from PIL import Image
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from dataset_generator_m1.config import load_profile
from study_effect_combinations import DEFAULT_MATRIX, generate_report, load_matrix, profile_for

ROOT = Path(__file__).resolve().parents[1]

def test_saved_matrix_has_controlled_ablation_and_sampled_combination():
    matrix, _, _ = load_matrix(DEFAULT_MATRIX)
    base = load_profile(ROOT/'examples/configs/landing-pad_surface-pristine.yaml')
    profiles = {v: profile_for(base,v,'development',2,matrix).profile for v in matrix['variants']}
    assert set(profiles) >= {'baseline','wear','lighting','shade','context','wear-light','wear-context','all','all-capture'}
    assert all(p.scene.foreground_resampling == 'premultiplied' for p in profiles.values())
    assert all(not p.appearance.final for v,p in profiles.items() if v != 'all-capture')
    assert profiles['all-capture'].appearance.final
    assert profiles['context'].scene.foreground_context.probability == 1
    assert profiles['all-capture'].scene.foreground_context.probability == .5
    assert profiles['all-capture'].scene.lighting.shade.probability == .7
    assert not profiles['baseline'].appearance.foreground


def test_report_measures_visible_mask_and_crops_matching_box(tmp_path):
    matrix = {'variants': {'baseline':{},'wear':{}}}
    base = np.zeros((12,12,3), dtype=np.uint8)
    changed = base.copy(); changed[2:6,3:7,:] = 30; changed[10,10,:] = 12
    rows = {}
    for name,img in [('baseline',base),('wear',changed)]:
        path=tmp_path/name; path.mkdir(); (path/'masks').mkdir()
        Image.fromarray(img).save(path/'image.png')
        np.savez_compressed(path/'masks'/'a.npz', alpha=np.full((4,4),255,dtype=np.uint8))
        rows[name]={0:{'slot':0,'image_path':'image.png','annotations':[{'bbox':[3,2,7,6]}],
            'mask_evidence':{'path':'masks/a.npz','alpha_threshold':8,'instances':[{'full':{'key':'alpha','origin':[3,2]},'visible':{'same_as':'full'}}]},
            'scene_effects':{},'appearance_effects':[]}}
    assert generate_report(tmp_path,'development',rows,matrix)==[0]
    values=json.loads((tmp_path/'metrics.json').read_text())['rows']
    assert values[1]['inside_mae_rgb_0_255']==30
    assert values[1]['outside_mae_rgb_0_255']==round(12/128,4)
    assert (tmp_path/'crops'/'wear-0000.png').is_file()
    assert 'not a realism score' in (tmp_path/'report.html').read_text()


def test_rejects_invalid_seed_matrix(tmp_path):
    matrix,_,_=load_matrix(DEFAULT_MATRIX)
    matrix['seeds']['reserved']=matrix['seeds']['development']
    p=tmp_path/'matrix.json'; p.write_text(json.dumps(matrix))
    with pytest.raises(ValueError): load_matrix(p)


def test_only_expected_study_warnings_are_acknowledged():
    from study_effect_combinations import ACKNOWLEDGED_CODES
    assert ACKNOWLEDGED_CODES == {
        'UNDOCUMENTED_LOCAL_PROFILE', 'EXPERIMENTAL_SCENE_LIGHTING_UNCALIBRATED',
        'EXPERIMENTAL_FOREGROUND_CONTEXT_UNCALIBRATED'}


def test_unexpected_preflight_warning_fails_closed(tmp_path, monkeypatch):
    import study_surface_2d
    from study_effect_combinations import ACKNOWLEDGED_CODES
    from types import SimpleNamespace
    from dataset_generator_m1.preflight import require_warning_receipt
    warning = {'required_acknowledgements':['UNDOCUMENTED_LOCAL_PROFILE','UNEXPECTED_DANGER']}
    prepared = SimpleNamespace(preflight=warning)
    monkeypatch.setattr(study_surface_2d, 'plan_execution', lambda current: SimpleNamespace(workers=1))
    monkeypatch.setattr(study_surface_2d, 'prepare_generation', lambda request: prepared)
    def attempt_generate(current, pool, options):
        require_warning_receipt(warning, options.receipt_path)
    monkeypatch.setattr(study_surface_2d, 'generate_pool', attempt_generate)
    with pytest.raises(ValueError, match='requires a matching preflight warning receipt'):
        study_surface_2d.run_pool(object(), tmp_path/'pool', tmp_path/'obs', acknowledged_codes=ACKNOWLEDGED_CODES)
    assert not list(tmp_path.glob('*preflight-receipt.json'))
