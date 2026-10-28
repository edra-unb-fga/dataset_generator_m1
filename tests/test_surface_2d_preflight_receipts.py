"""The timing study acknowledges only the experimental warnings it declares."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from dataset_generator_m1.preflight import require_warning_receipt

spec=importlib.util.spec_from_file_location('surface_2d_receipts',Path('scripts/study_surface_2d.py'))
surface=importlib.util.module_from_spec(spec);spec.loader.exec_module(surface)


@pytest.mark.parametrize('code,allowed', [('EXPERIMENTAL_LINEAR_COMPOSITING_UNVALIDATED',True),('OTHER_UNREVIEWED_WARNING',False)])
def test_only_declared_warning_codes_receive_recorded_receipts(tmp_path,monkeypatch,code,allowed):
    preflight={'status':'valid','required_acknowledgements':[code],
               'receipt_binding':{'hash':'binding','value':{}}}
    monkeypatch.setattr(surface,'plan_execution',lambda current:SimpleNamespace(workers=1))
    monkeypatch.setattr(surface,'prepare_generation',lambda request:SimpleNamespace(preflight=preflight))
    def generate(current,pool,options):
        require_warning_receipt(preflight,options.receipt_path)
        return {'status':'complete','accepted_samples':1}
    monkeypatch.setattr(surface,'generate_pool',generate)
    monkeypatch.setattr(surface,'inspect_pool',lambda pool:{'status':'valid'})
    monkeypatch.setattr(surface,'pool_evidence',lambda pool:('same',[]))
    current=SimpleNamespace(profile=SimpleNamespace(run=SimpleNamespace(num_images=1)))
    kwargs={'acknowledged_codes':{'EXPERIMENTAL_LINEAR_COMPOSITING_UNVALIDATED'}}
    if allowed:
        surface.run_pool(current,tmp_path/'sample',tmp_path/'observations.jsonl',**kwargs)
        assert (tmp_path/'sample-preflight-receipt.json').is_file()
    else:
        with pytest.raises(ValueError,match='receipt'):
            surface.run_pool(current,tmp_path/'sample',tmp_path/'observations.jsonl',**kwargs)
        assert not (tmp_path/'sample-preflight-receipt.json').exists()
