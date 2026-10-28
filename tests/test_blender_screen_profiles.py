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
