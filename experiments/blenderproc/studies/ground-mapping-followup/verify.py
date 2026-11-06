"""Verify paired job geometry and exact rendered masks for a mapping-only study."""
import hashlib
import json
import sys
from pathlib import Path
import numpy as np

root=Path(sys.argv[1]); groups=[('legacy','span-05','span-10','span-15'),('close-0-legacy','close-0-span-10'),('close-3-legacy','close-3-span-10')]; all_evidence=[]
for labels in groups:
    studies={name:json.loads((root/name/'study.json').read_text()) for name in labels}
    base=studies[labels[0]]['jobs']; evidence=[]
    for name in labels:
        if studies[name]['config']['resolution'] != studies[labels[0]]['config']['resolution']:
            raise ValueError(f'{name}: resolution mismatch')
        jobs=studies[name]['jobs']
        if len(jobs)!=len(base): raise ValueError('job count mismatch')
        for reference,job in zip(base,jobs,strict=True):
            for key in ('seed','reference_scene_index','scene','treatment','casters','environment_geometry','environment_geometry_settings','ground_index','material_state'):
                if reference.get(key)!=job.get(key): raise ValueError(f'{name}: changed job {key}')
            path=root/name/'scenes'/job['id']; result=json.loads((path/'result.json').read_text())
            if result['status']!='accepted': raise ValueError(f'{name}: rejected {job["id"]}')
            with np.load(path/'masks.npz',allow_pickle=False) as masks:
                hashes={key:{'shape':list(masks[key].shape),'dtype':str(masks[key].dtype),'sha256':hashlib.sha256(masks[key].tobytes()).hexdigest()} for key in sorted(masks.files)}
            if name==labels[0]: evidence.append({'job':job['id'],'mask_hashes':hashes,'variants':{}})
            entry=evidence[base.index(reference)]
            if hashes!=entry['mask_hashes']: raise ValueError(f'{name}: mask mismatch {job["id"]}')
            entry['variants'][name]=result.get('ground_diagnostics')
    all_evidence.append({'variants':labels,'jobs':evidence})
(root/'pair-evidence.json').write_text(json.dumps({'status':'complete','groups':all_evidence},indent=2)+'\n')
