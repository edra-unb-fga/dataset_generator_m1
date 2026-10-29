"""Paired visual/quantitative 2D ablation of surface and scene appearance effects."""
from __future__ import annotations
import argparse
import hashlib
import html
import json
from pathlib import Path
import re
import shutil

import numpy as np
from PIL import Image
from dataset_generator_m1.config import load_profile
from dataset_generator_m1.execution import plan_execution
from dataset_generator_m1.identities import digest, software_identity
from dataset_generator_m1.models import ExecutionConfig, GenerationProfile
from study_surface_2d import atomic_json, run_pool

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MATRIX = ROOT/'experiments/foreground-context/effect-combinations.json'
# This bounded, guarded study explicitly compares these known uncalibrated settings.
# Any additional required acknowledgement is rejected by run_pool without a receipt.
ACKNOWLEDGED_CODES = frozenset({'UNDOCUMENTED_LOCAL_PROFILE',
    'EXPERIMENTAL_SCENE_LIGHTING_UNCALIBRATED', 'EXPERIMENTAL_FOREGROUND_CONTEXT_UNCALIBRATED'})


def load_matrix(path):
    raw = Path(path).read_bytes()
    matrix = json.loads(raw)
    if set(matrix) != {'schema_version', 'seeds', 'variants'} or matrix['schema_version'] != 1:
        raise ValueError('Invalid study matrix')
    if set(matrix['seeds']) != {'development', 'reserved'} or any(type(s) is not int or s < 0 for s in matrix['seeds'].values()) or len(set(matrix['seeds'].values())) != 2:
        raise ValueError('Expected distinct nonnegative development and reserved seeds')
    variants = matrix['variants']
    if not isinstance(variants, dict) or list(variants)[0] != 'baseline':
        raise ValueError('Expected baseline as first variant')
    for name, value in variants.items():
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', name) or set(value) != {'wear', 'lighting', 'context', 'capture'} or type(value['capture']) is not bool:
            raise ValueError('Invalid variant entry')
    return matrix, raw, hashlib.sha256(raw).hexdigest()


def profile_for(base, variant, phase, count, matrix, execution=None):
    item = matrix['variants'][variant]
    payload = base.profile.model_dump(mode='json')
    payload['run'].update(seed=matrix['seeds'][phase], num_images=count)
    payload['scene'].update(foreground_resampling='premultiplied', lighting=item['lighting'], foreground_context=item['context'])
    payload['appearance']['background'] = []
    payload['appearance']['foreground'] = [] if item['wear'] is None else [
        {'id':'study-wear', 'type':'SurfaceWear', 'probability':1.0, 'params':item['wear']}]
    if not item['capture']:
        payload['appearance']['final'] = []
    if execution is not None:
        payload['execution'] = execution.model_dump(mode='json')
    profile = GenerationProfile.model_validate(payload)
    return base.model_copy(update={'profile':profile, 'contract_hash':digest({'base':base.contract_hash, 'effect_combinations':payload}),
        'applied_overrides':{**base.applied_overrides, 'effect_combinations':{'phase':phase,'variant':variant}}})


def mask_for(pool, row, width, height):
    evidence = row['mask_evidence']
    mask = np.zeros((height, width), dtype=bool)
    with np.load(pool/evidence['path'], allow_pickle=False) as arrays:
        for instance in evidence['instances']:
            part = instance['visible']
            if part.get('same_as') == 'full':
                part = instance['full']
            if part.get('key') is None:
                continue
            x, y = part['origin']
            values = arrays[part['key']]
            h, w = values.shape
            mask[y:y+h, x:x+w] |= values > evidence['alpha_threshold']
    return mask


def image_effects(row):
    context = (row.get('scene_effects') or {}).get('foreground_context') or {}
    objects = context.get('objects', [])
    return {'context_applied':sum(bool(x.get('applied')) for x in objects), 'context_attempted':len(objects),
        'lighting':(row.get('scene_effects') or {}).get('lighting'),
        'appearance':[{'id':x['id'], 'stage':x['stage'], 'applied':x['applied']} for x in row.get('appearance_effects', [])]}


def generate_report(root, phase, rows, matrix):
    variants = list(matrix['variants'])
    slots = sorted(set.intersection(*(set(rows[v]) for v in variants)))
    crops = root/'crops'
    crops.mkdir()
    metrics = []
    sections = []
    for slot in slots:
        refrow = rows['baseline'][slot]
        ref = np.asarray(Image.open(root/'baseline'/refrow['image_path']).convert('RGB'), dtype=np.int16)
        h, w = ref.shape[:2]
        mask = mask_for(root/'baseline', refrow, w, h)
        boxes = sorted((a['bbox'] for a in refrow['annotations']), key=lambda b:(b[2]-b[0])*(b[3]-b[1]), reverse=True)
        box = boxes[0] if boxes else [0,0,w,h]
        x1,y1,x2,y2 = box
        pad = max(8, int(max(x2-x1,y2-y1)*0.15))
        cropbox = (max(0,x1-pad),max(0,y1-pad),min(w,x2+pad),min(h,y2+pad))
        cells=[]
        for name in variants:
            row = rows[name][slot]
            source = root/name/row['image_path']
            im = Image.open(source).convert('RGB')
            candidate = np.asarray(im, dtype=np.int16)
            diff = np.abs(candidate-ref).mean(axis=2)
            def metric(region):
                return None if not np.any(region) else round(float(diff[region].mean()), 4)
            observed = {'slot':slot,'variant':name,'inside_mae_rgb_0_255':metric(mask),'outside_mae_rgb_0_255':metric(~mask),
                'inside_pixels':int(mask.sum()),'effects':image_effects(row)}
            metrics.append(observed)
            crop = f'{name}-{slot:04}.png'
            im.crop(cropbox).save(crops/crop)
            label=html.escape(name)
            detail=html.escape(json.dumps(observed['effects'],ensure_ascii=False,indent=2))
            cells.append(f'<div class="cell"><b>{label}</b><br><img loading="lazy" src="{html.escape((Path(name)/row["image_path"]).as_posix(),quote=True)}"><br><img loading="lazy" src="crops/{crop}"><br>MAE target {observed["inside_mae_rgb_0_255"]}; outside {observed["outside_mae_rgb_0_255"]}<details><summary>Applied effects</summary><pre>{detail}</pre></details></div>')
        sections.append(f'<h2>Scene {slot}</h2><p>Crop: largest annotated target, same coordinates in every column.</p><div class="row">' + ''.join(cells) + '</div>')
    doc='''<!doctype html><meta charset="utf-8"><title>Paired effects comparison</title><style>body{font:15px sans-serif;margin:2rem}.row{display:flex;overflow:auto;gap:12px}.cell{display:block;min-width:260px;max-width:300px}img{width:100%;max-width:300px}pre{white-space:pre-wrap;font-size:11px}details{max-height:300px;overflow:auto}</style>'''
    doc+=f'<h1>2D effects comparison: {html.escape(phase)}</h1><p>Same geometry and masks. All use premultiplied resampling. Except for the all-capture cell, camera effects are disabled and enabled effects are forced to activate; their magnitudes remain sampled. The all-capture cell uses sampled lighting, shade and context probabilities and the selected camera effects. Lighting and shade are qualitative approximations; no physical accuracy is implied.</p><p>MAE is mean absolute RGB channel difference from baseline on decoded images (0–255): an effect-size indicator, not a realism score. JPEG encoding, edges and capture effects can affect outside-mask pixels. A larger difference need not be better.</p>'+''.join(sections)
    (root/'report.html').write_text(doc,encoding='utf-8')
    atomic_json(root/'metrics.json',{'schema_version':1,'rows':metrics,'limits':['No realism, detector utility, or causal comparison across engines is established.', 'Visible target alpha threshold and JPEG decoding define measured regions; edge leakage can affect outside values.']})
    return slots


def run(config, output, phase, count, matrix_path=DEFAULT_MATRIX, execution_policy=None):
    matrix, raw, matrix_hash = load_matrix(matrix_path)
    if phase not in matrix['seeds'] or not 1 <= count <= 100: raise ValueError('Invalid phase or count')
    root=Path(output).resolve()
    if root.exists(): raise ValueError('Use a fresh output directory')
    base=load_profile(Path(config).resolve())
    execution=ExecutionConfig.model_validate(json.loads(Path(execution_policy).read_text())) if execution_policy else None
    profiles={name:profile_for(base,name,phase,count,matrix,execution) for name in matrix['variants']}
    for profile in profiles.values(): plan_execution(profile)
    root.mkdir(parents=True)
    shutil.copyfile(__file__,root/'driver-source.py')
    (root/'matrix.json').write_bytes(raw)
    atomic_json(root/'study.json',{'schema_version':1,'phase':phase,'samples':count,'matrix_sha256':matrix_hash,
        'source_hashes':base.source_hashes,'software':software_identity(),
        'study_acknowledged_warning_codes':sorted(ACKNOWLEDGED_CODES),
        'effective_profiles':{name:p.profile.model_dump(mode='json') for name,p in profiles.items()}})
    rows={}; signatures={}; timings={}
    for name, current in profiles.items():
        summary, inspection, plan, prep, wall, signature, samples = run_pool(current,root/name,root/'local-observations.jsonl', acknowledged_codes=ACKNOWLEDGED_CODES)
        signatures[name]=signature
        rows[name]={r['slot']:r for r in samples}
        timings[name]={'accepted':summary['accepted_samples'],'inspection':inspection['status'],'generation_seconds':wall,'preparation_seconds':prep,'execution':plan.as_dict()}
        atomic_json(root/'progress.json',{'completed':list(rows),'current':name,'timings':timings,'signatures':signatures})
        if signature != signatures['baseline']: raise RuntimeError(f'{name} changed geometry, annotations, or masks')
    slots=generate_report(root,phase,rows,matrix)
    atomic_json(root/'summary.json',{'status':'complete','paired_slots':slots,'signatures':signatures,'timings':timings,'report':'report.html'})
    return root


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',required=True); p.add_argument('--output-dir',required=True)
    p.add_argument('--phase',choices=['development','reserved'],required=True); p.add_argument('--samples',type=int,default=8)
    p.add_argument('--matrix',default=DEFAULT_MATRIX); p.add_argument('--execution-policy')
    a=p.parse_args(); print(run(a.config,a.output_dir,a.phase,a.samples,a.matrix,a.execution_policy))
if __name__=='__main__': main()
