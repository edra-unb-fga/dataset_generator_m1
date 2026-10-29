#!/usr/bin/env python3
"""Run a bounded, saved matrix of paired camera/ground/environment pilot cells."""
from __future__ import annotations
import argparse
import os
import tarfile
import io
import copy
import json
from pathlib import Path
from time import monotonic
import hashlib
import math
import numpy as np
from PIL import Image
from dataset_generator_m1.blender_pilot import atomic_json, completed_outputs, load_config, prepare, run_study
from dataset_generator_m1.ownership import CoordinatorLease
from dataset_generator_m1.cell_handoff import package_with_deadline


def compare_outputs(prior, current):
    """Compare identical raster shapes only; retain explicit size mismatch evidence."""
    with Image.open(prior['image']) as image:
        a = np.asarray(image, dtype=np.int16)
    with Image.open(current['image']) as image:
        b = np.asarray(image, dtype=np.int16)
    comparable = a.shape == b.shape
    result = {'rgb_comparable': comparable, 'baseline_rgb_shape': list(a.shape),
              'candidate_rgb_shape': list(b.shape),
              'incomparable_reason': None if comparable else 'rgb-shape-mismatch',
              'rgb_mean_abs_difference': float(np.abs(a-b).mean()) if comparable else None,
              'all_masks_equal': None}
    if comparable:
        with np.load(prior['masks'], allow_pickle=False) as x, np.load(current['masks'], allow_pickle=False) as y:
            result['all_masks_equal'] = bool(sorted(x.files) == sorted(y.files) and
                                             all(np.array_equal(x[k], y[k]) for k in x.files))
    return result


def compact_handoff(root, cell_id, archive, lease, deadline):
    # Called only at the driver's settled between-cell barrier. Wear maps are intentionally
    # excluded; the bundle, matrix, seeds and study.json retain reproduction information.
    if monotonic() >= deadline: raise TimeoutError('No time for handoff')
    cell = root / 'cells' / cell_id
    paths = [root / 'matrix.json', root / 'design.json', root / 'provenance.json', root / 'budget.json',
             root / 'configs' / (cell_id + '.json')]
    for name in ('study.json', 'surface-origin.json', 'progress.json', 'runs.json', 'summary.json', 'execution.json'):
        paths.append(cell / name)
    paths.extend(sorted((cell / 'scenes').glob('*/result.json')))
    paths.extend(sorted((cell / 'scenes').glob('*/rgb.png')))
    paths.extend(sorted((cell / 'scenes').glob('*/masks.npz')))
    paths=[p for p in paths if p.is_file()]
    records=[{'path':str(p.relative_to(root)),'size':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths]
    archive.parent.mkdir(parents=True,exist_ok=True)
    temp=archive.with_suffix('.partial')
    with tarfile.open(temp,'w:gz',compresslevel=1) as tar:
        data=json.dumps({'schema_version':1,'cell':cell_id,'files':records,'scope':'compact visual evidence; wear maps omitted'},indent=2).encode()
        info=tarfile.TarInfo('compact-manifest.json');info.size=len(data);tar.addfile(info,io.BytesIO(data))
        for p in paths:
            if monotonic() >= deadline: raise TimeoutError('Handoff deadline exceeded')
            tar.add(p,arcname=str(p.relative_to(root)),recursive=False)
    os.replace(temp,archive)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('config','matrix','output-dir','blenderproc','blender-install-path'):
        parser.add_argument('--'+name, required=True)
    parser.add_argument('--total-seconds',type=float,required=True)
    parser.add_argument('--handoff-dir', help='Package each completed cell under the between-cell study lease')
    args=parser.parse_args()
    if not math.isfinite(args.total_seconds) or args.total_seconds <= 0: raise ValueError('A positive finite total time limit is required')
    started=monotonic()
    matrix=json.loads(Path(args.matrix).read_text())
    if matrix.get('schema_version')!=1 or not matrix.get('cells'):
        raise ValueError('Unsupported or empty camera study matrix')
    root=Path(args.output_dir).resolve()
    root.mkdir(parents=True,exist_ok=False)
    base=load_config(args.config).model_dump(mode='json')
    records=[]
    atomic_json(root/'matrix.json',matrix)
    matrix_sha=hashlib.sha256(Path(args.matrix).read_bytes()).hexdigest()
    atomic_json(root/'design.json',{'matrix':matrix,'matrix_sha256':matrix_sha})
    ledger={'schema_version':1,'policy':{'total_seconds':args.total_seconds,'basis':'elapsed_wall_time',
            'entry_charge_basis':'command_seconds'},'entries':[]}
    atomic_json(root/'budget.json',ledger)
    atomic_json(root/'provenance.json',{'matrix_sha256':hashlib.sha256(Path(args.matrix).read_bytes()).hexdigest(),
        'config_sha256':hashlib.sha256(Path(args.config).read_bytes()).hexdigest(),
        'driver_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'total_seconds':args.total_seconds})
    try:
        for cell in matrix['cells']:
            remaining=args.total_seconds-(monotonic()-started)
            if remaining<=0: raise TimeoutError('Total study time exhausted before next cell')
            name=cell['id']
            if not name or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in name):
                raise ValueError('Invalid cell id')
            cfg=copy.deepcopy(base)
            cfg.update(copy.deepcopy(cell.get('config',{})))
            if cell.get('camera_study'):
                cfg['camera_study']=cfg.get('camera_study') or {}
                for key,value in cell['camera_study'].items(): cfg['camera_study'][key]=value
            if cell.get('treatment'):
                for key,value in cell['treatment'].items():cfg['treatments'][0][key]=value
            with CoordinatorLease(root) as lease:
                if any(e['name']==name for e in ledger['entries']):
                    raise ValueError('Cell ID already reserved')
                remaining=args.total_seconds-(monotonic()-started)
                if remaining<=0: raise TimeoutError('Total study time exhausted before preparation')
                # Leave a wall-time margin for preparation and handoff; check again after prepare.
                cfg['study_seconds']=min(float(cfg['study_seconds']),remaining*.8)
                conf=root/'configs'/f'{name}.json'; atomic_json(conf,cfg)
                output=root/'cells'/name
                study=prepare(conf,output)
                remaining=args.total_seconds-(monotonic()-started)
                if remaining<=0 or cfg['study_seconds']>remaining:
                    raise TimeoutError('Insufficient wall time remains for the configured cell after preparation')
                entry={'name':name,'track':'camera-study','allowance_seconds':remaining,
                       'charged_seconds':remaining,'status':'reserved'}
                ledger['entries'].append(entry); atomic_json(root/'budget.json',ledger)
                atomic_json(output/'surface-origin.json',{'phase':'camera-study','cell_id':name,
                    'matrix_sha256':matrix_sha,'track':'camera-study',
                    'controller_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    'cell':cell})
                try:
                    outcome=run_study(output,args.blenderproc,args.blender_install_path,job_ids=cell['jobs'])
                finally:
                    runs_file=output/'runs.json'
                    if runs_file.exists():
                        runs=json.loads(runs_file.read_text())
                        durations=[r.get('command_seconds') for r in runs]
                        if runs and all(type(v) in (int,float) and math.isfinite(v) and v>=0 for v in durations):
                            entry.update(status='settled',charged_seconds=sum(durations),
                                study_wall_seconds_before_handoff=monotonic()-started,
                                evidence_identity=study['identity'],outcome=runs[-1]['status'])
                            atomic_json(root/'budget.json',ledger)
                rows=[]
                for job,path,result in completed_outputs(output,study):
                    if job['id'] not in cell['jobs']:continue
                    item={'job':job['id'],'status':result['status'],'attempts':result.get('attempts',[]),
                          'camera':result.get('camera_diagnostics'),'ground':result.get('ground_diagnostics'),
                          'environment':result.get('environment_geometry_diagnostics'),
                          'image':str(path/'rgb.png') if (path/'rgb.png').exists() else None,
                          'masks':str(path/'masks.npz') if (path/'masks.npz').exists() else None}
                    rows.append(item)
                record={'cell':name,'outcome':outcome,'study_identity':study['identity'],'rows':rows}
                records.append(record)
                atomic_json(output/'summary.json',record)
                atomic_json(root/'summary.json',{'status':'running','records':records})
                print(json.dumps({'cell':name,'status':outcome['status'],'outputs':len(rows)}),flush=True)
                if outcome['status']!='complete': raise RuntimeError('Cell did not complete: '+name)
                if args.handoff_dir:
                    compact_handoff(root,name,Path(args.handoff_dir)/(name+'.tar.gz'),
                                          lease=lease,deadline=started+args.total_seconds)
                if monotonic()-started > args.total_seconds:
                    raise TimeoutError('Total wall-time limit exceeded during cell or handoff')
        baseline={r['job']:r for r in records[0]['rows']}
        comparisons=[]
        for record in records[1:]:
            for row in record['rows']:
                prior=baseline.get(row['job'])
                if not prior or not row['image'] or not prior['image'] or not row['masks'] or not prior['masks']:continue
                comparisons.append({'cell':record['cell'], 'job':row['job'], **compare_outputs(prior, row)})
        atomic_json(root/'summary.json',{'status':'complete','records':records,'comparisons':comparisons,
            'elapsed_seconds':monotonic()-started})
    except BaseException as exc:
        atomic_json(root/'summary.json',{'status':'failed','error':str(exc),'records':records,
            'elapsed_seconds':monotonic()-started})
        raise

if __name__=='__main__':main()
