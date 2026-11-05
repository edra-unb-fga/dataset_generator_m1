import json
import subprocess
import sys
from pathlib import Path
import numpy as np


def test_pair_verifier_checks_shape_and_resolution(tmp_path):
    labels=('legacy','span-05','span-10','span-15','close-0-legacy','close-0-span-10','close-3-legacy','close-3-span-10')
    for label in labels:
        root=tmp_path/label;scene=root/'scenes'/'job';scene.mkdir(parents=True)
        resolution=[1024,1024] if label.startswith('close-') else [640,640]
        (root/'study.json').write_text(json.dumps({'config':{'resolution':resolution},'jobs':[{'id':'job','seed':1}]}))
        (scene/'result.json').write_text(json.dumps({'status':'accepted'}))
        np.savez(scene/'masks.npz',visible=np.ones((2,2),dtype=np.uint8))
    script=Path('experiments/blenderproc/studies/ground-mapping-followup/verify.py').resolve()
    def run(): return subprocess.run([sys.executable,str(script),str(tmp_path)],capture_output=True,text=True)
    assert run().returncode==0
    np.savez(tmp_path/'span-05/scenes/job/masks.npz',visible=np.ones((4,),dtype=np.uint8))
    assert 'mask mismatch' in run().stderr
    np.savez(tmp_path/'span-05/scenes/job/masks.npz',visible=np.ones((2,2),dtype=np.uint8))
    p=tmp_path/'span-10/study.json';data=json.loads(p.read_text());data['config']['resolution']=[1024,1024];p.write_text(json.dumps(data))
    assert 'resolution mismatch' in run().stderr
