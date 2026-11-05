"""Focused checks for adaptive lighting controls and archive safety."""
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from transform import digest, transformed


def postprocessor():
    spec=importlib.util.spec_from_file_location('postprocess',HERE.parent/'postprocess.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


class StudyChecks(unittest.TestCase):
    def test_lighting_only_and_power_fill(self):
        base=[{'kind':'SPOT','location':[1,2,3],'target':[0,0,0],'color':[1,1,1],
               'power_w':1000.,'size_m':1.,'spot_size_rad':1.,'spot_blend':.2}]
        original=json.dumps(base,sort_keys=True);soft=transformed(base,'soft');filled=transformed(base,'soft-fill')
        self.assertEqual(json.dumps(base,sort_keys=True),original)
        self.assertEqual(soft[0]['power_w'],800.);self.assertEqual(soft[0]['size_m'],2.)
        self.assertEqual(soft[0]['spot_size_rad'],1.5);self.assertEqual(soft[0]['spot_blend'],.5)
        self.assertEqual(soft[0]['location'],base[0]['location']);self.assertEqual(filled[:-1],soft)
        self.assertEqual(filled[-1]['power_w'],60.);self.assertEqual(transformed(base,'baseline'),base)

    def test_matching_triplets_and_mask_mismatch(self):
        lamp={'kind':'AREA','location':[0,0,2],'target':[0,0,0],'color':[1,1,1],
              'power_w':500.,'size_m':1.,'spot_size_rad':1.,'spot_blend':.2}
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for kind in ('indoor','outdoor-night'):
                for variant in ('baseline','soft','soft-fill'):
                    job={'id':'scene','seed':1,'treatment':{'lamps':transformed([lamp],variant)}}
                    contract={'jobs_sha256':digest([job])};study={'contract':contract,'identity':digest(contract),'jobs':[job]}
                    batch=root/f'{kind}-{variant}';scene=batch/'scenes'/'scene';scene.mkdir(parents=True)
                    (batch/'study.json').write_text(json.dumps(study));(scene/'result.json').write_text('{"status":"accepted"}')
                    np.savez(scene/'masks.npz',visible=np.array([[1,0]],dtype=bool),full=np.array([[1,1]],dtype=bool))
            cmd=[sys.executable,str(HERE/'verify.py'),str(root),'1']
            self.assertEqual(subprocess.run(cmd,capture_output=True).returncode,0)
            np.savez(root/'indoor-soft'/'scenes'/'scene'/'masks.npz',visible=np.array([[0,0]],dtype=bool),full=np.array([[1,1]],dtype=bool))
            self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)

    def test_duplicate_archive_files_must_match(self):
        extract=postprocessor().extract
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            def make(name,entries):
                archive=root/name
                with tarfile.open(archive,'w:gz') as tar:
                    for content in entries:
                        member=tarfile.TarInfo('workspace/run-config.json');member.size=len(content);tar.addfile(member,io.BytesIO(content))
                return archive
            good=root/'good';good.mkdir();extract(make('good.tar.gz',[b'one',b'one']),good)
            self.assertEqual((good/'workspace/run-config.json').read_bytes(),b'one')
            bad=root/'bad';bad.mkdir()
            with self.assertRaises(ValueError): extract(make('bad.tar.gz',[b'one',b'two']),bad)

if __name__=='__main__': unittest.main()
