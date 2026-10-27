#!/usr/bin/env python3
"""Run a bounded, saved matrix of paired camera/ground/environment pilot cells."""
from __future__ import annotations
import argparse
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
                    package_with_deadline(root,name,Path(args.handoff_dir)/(name+'.tar.gz'),
                                          lease=lease,deadline=started+args.total_seconds)
                if monotonic()-started > args.total_seconds:
                    raise TimeoutError('Total wall-time limit exceeded during cell or handoff')
        baseline={r['job']:r for r in records[0]['rows']}
        comparisons=[]
        for record in records[1:]:
            for row in record['rows']:
                prior=baseline.get(row['job'])
                if not prior or not row['image'] or not prior['image'] or not row['masks'] or not prior['masks']:continue
                with np.load(prior['masks'],allow_pickle=False) as x,np.load(row['masks'],allow_pickle=False) as y:
                    mask_equal=sorted(x.files)==sorted(y.files) and all(np.array_equal(x[k],y[k]) for k in x.files)
                a=np.asarray(Image.open(prior['image']),dtype=np.int16);b=np.asarray(Image.open(row['image']),dtype=np.int16)
                comparisons.append({'cell':record['cell'],'job':row['job'],'all_masks_equal':bool(mask_equal),
                    'rgb_mean_abs_difference':float(np.abs(a-b).mean())})
        atomic_json(root/'summary.json',{'status':'complete','records':records,'comparisons':comparisons,
            'elapsed_seconds':monotonic()-started})
    except BaseException as exc:
        atomic_json(root/'summary.json',{'status':'failed','error':str(exc),'records':records,
            'elapsed_seconds':monotonic()-started})
        raise

if __name__=='__main__':main()
