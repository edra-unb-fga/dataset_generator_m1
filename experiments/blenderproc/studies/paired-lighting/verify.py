"""Reject unmatched paired scenes, lighting controls, or masks."""
import copy, hashlib, json, sys
from pathlib import Path
import numpy as np
root=Path(sys.argv[1]); groups=[]
for kind in ('outdoor-night','indoor'):
    labels=[kind+'-baseline',kind+'-dim']
    studies=[json.loads((root/name/'study.json').read_text()) for name in labels]
    if any(len(s['jobs']) != 20 for s in studies): raise ValueError('Expected 20 jobs per variant')
    evidence=[]
    for index,(base,dim) in enumerate(zip(*(s['jobs'] for s in studies),strict=True)):
        for key in ('id','seed','scene_index','reference_scene_index','scene','samples','quality','ground_index','environment_geometry','environment_geometry_settings','selected_lighting','casters','material_state','ground_spans'):
            if base.get(key)!=dim.get(key): raise ValueError(f'{kind} {index}: {key} differs')
        bt=copy.deepcopy(base['treatment']);dt=copy.deepcopy(dim['treatment'])
        bl=bt.pop('lamps');dl=dt.pop('lamps')
        if bt!=dt or len(bl)!=len(dl): raise ValueError('Non-lamp treatment differs')
        for left,right in zip(bl,dl,strict=True):
            left=left.copy();right=right.copy();bp=left.pop('power_w');dp=right.pop('power_w')
            if left!=right or abs(dp-bp*.6)>1e-7: raise ValueError('Lamp pairing differs')
        def wear(job):
            return [{k:v['sha256'] for k,v in m['maps'].items()} for m in job.get('wear_maps',[])]
        if wear(base)!=wear(dim): raise ValueError('Wear derivatives differ')
        hashes=[]
        for name,job in zip(labels,(base,dim),strict=True):
            path=root/name/'scenes'/job['id'];result=json.loads((path/'result.json').read_text())
            if result['status']!='accepted':raise ValueError('Scene not accepted')
            with np.load(path/'masks.npz',allow_pickle=False) as masks:
                hashes.append({k:(str(masks[k].dtype),list(masks[k].shape),hashlib.sha256(masks[k].tobytes()).hexdigest()) for k in sorted(masks.files)})
        if hashes[0]!=hashes[1]:raise ValueError('Mask mismatch')
        evidence.append({'job':base['id'],'mask_hashes':hashes[0], 'baseline_lamps':bl,'dim_lamps':dl,'retained_intense_candidate':index<2})
    groups.append({'condition':kind,'pairs':evidence})
(root/'pair-evidence.json').write_text(json.dumps({'status':'complete','groups':groups},indent=2)+'\n')
