import json
import runpy
from pathlib import Path
import pytest

MODULE=runpy.run_path('scripts/select_blender_screen_profile.py')
APPLY=MODULE['apply_profile']
BASE='experiments/blenderproc/pilot-drone.example.json'
CATALOG='experiments/blenderproc/execution/quick-screen-profiles.json'

@pytest.mark.parametrize(('profile','size','expected'),[
 ('colab-l4-screen',(640,640),('gpu-guarded',4,1)),
 ('colab-l4-screen',(1280,1280),('gpu-guarded',2,1)),
 ('colab-t4-screen',(640,640),('gpu-guarded',1,2)),
 ('local-cpu',(640,640),('cpu',1,6)),
])
def test_profiles_generate_complete_valid_configs(tmp_path,profile,size,expected):
 output=tmp_path/'pilot.json'
 APPLY(BASE,CATALOG,profile,output,size)
 value=json.loads(output.read_text())
 assert (value['execution_profile'],value['workers'],value['threads'])==expected
 assert value['resolution']==list(size)
 assert Path(value['reference_pool']).is_absolute()
 with pytest.raises(FileExistsError):APPLY(BASE,CATALOG,profile,output,size)

def test_rejects_unknown_profile(tmp_path):
 with pytest.raises(ValueError):APPLY(BASE,CATALOG,'unknown',tmp_path/'x.json')


def test_selector_and_prepare_share_profile_rule(tmp_path, monkeypatch):
 from dataset_generator_m1.blender_screen_profiles import select_screen_profile
 import importlib.util
 spec=importlib.util.spec_from_file_location('prepare_run_parity', 'scripts/prepare_blenderproc_run.py')
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 observed={}
 def fake_prepare(config,output):
  observed.update(json.loads(Path(config).read_text()));return {'identity':'test'}
 monkeypatch.setattr(module,'prepare',fake_prepare)
 profile='colab-l4-camera-study'
 selected=APPLY(BASE,CATALOG,profile,tmp_path/'selected.json',(640,640))
 rule,status=select_screen_profile(CATALOG,profile,(640,640))
 assert selected['rule']==rule and selected['status']==status
 result=module.prepare_run(tmp_path/'selected.json',tmp_path/'prepared',screen_profile=profile,gpu_guard='off')
 assert (observed['execution_profile'],observed['workers'],observed['threads'])==(rule['execution_profile'],rule['workers'],rule['threads'])
 assert result['screen_status']==status
