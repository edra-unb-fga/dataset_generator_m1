"""Paired optional Blender execution study; configuration and matrix are saved data."""
import argparse
import copy
import hashlib
import shutil
import json
from pathlib import Path
import statistics
from typing import Literal

import numpy as np
from PIL import Image
from pydantic import BaseModel,ConfigDict,Field

from dataset_generator_m1.blender_execution import load_catalog
from dataset_generator_m1.blender_pilot import atomic_json,completed_outputs,load_config,prepare,run_study


class Variant(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name:str=Field(pattern=r'^[a-z0-9][a-z0-9-]{0,63}$')
    execution_profile:str
    renderer_initialization:Literal['stock','guarded']


class Matrix(BaseModel):
    model_config=ConfigDict(extra='forbid')
    schema_version:Literal[1]
    metric:Literal['measured-output','whole-command']
    repetitions:int=Field(ge=1,le=5)
    warmups:int=Field(ge=0,le=5)
    measured:int=Field(ge=1,le=50)
    resolution:tuple[int,int]
    variants:tuple[Variant,Variant]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',required=True);p.add_argument('--matrix',required=True);p.add_argument('--output-dir',required=True);p.add_argument('--blenderproc',required=True);p.add_argument('--blender-install-path',required=True);a=p.parse_args()
    matrix=Matrix.model_validate(json.loads(Path(a.matrix).read_text()))
    if matrix.variants[0].name==matrix.variants[1].name:raise ValueError('Unique variant names required')
    root=Path(a.output_dir).resolve()
    if root.exists():raise ValueError('Use a fresh study output directory')
    root.mkdir(parents=True)
    shutil.copyfile(__file__,root/'driver-source.py')
    atomic_json(root/'provenance.json',{'driver_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'matrix_sha256':hashlib.sha256(Path(a.matrix).read_bytes()).hexdigest(),'input_config_sha256':hashlib.sha256(Path(a.config).read_bytes()).hexdigest()})
    base=load_config(a.config).model_dump(mode='json');catalog=load_catalog(base['execution_policy']).model_dump(mode='json')
    base.update(scenes=matrix.warmups+matrix.measured,resolution=list(matrix.resolution),treatments=base['treatments'][:1],quality_treatments=[base['treatments'][0]['id']])
    atomic_json(root/'matrix.json',matrix.model_dump(mode='json'));records=[];cells={};comparisons=[]
    for repeat in range(matrix.repetitions):
        ordered=list(matrix.variants);ordered=ordered[repeat%2:]+ordered[:repeat%2]
        for variant in ordered:
            cell=root/f'{repeat:02d}-{variant.name}';config=copy.deepcopy(base);policy=copy.deepcopy(catalog)
            profile=next(p for p in policy['profiles'] if p['id']==variant.execution_profile)
            profile['settings']['renderer_initialization']=variant.renderer_initialization
            if matrix.metric=='measured-output' and (config.get('workers') or profile['settings']['workers'])!=1:raise ValueError('Concurrent workers require whole-command metric')
            atomic_json(root/f'policy-{repeat}-{variant.name}.json',policy)
            config.update(execution_policy=str(root/f'policy-{repeat}-{variant.name}.json'),execution_profile=variant.execution_profile)
            config_file=root/f'config-{repeat}-{variant.name}.json';atomic_json(config_file,config)
            study=prepare(config_file,cell)
            jobs=[j['id'] for j in study['jobs'] if j['quality']=='fast' and j['case']=='ordinary']
            result=run_study(cell,a.blenderproc,a.blender_install_path,job_ids=jobs)
            if result['status']!='complete':raise RuntimeError('Execution study stopped: '+json.dumps(result))
            outputs=completed_outputs(cell,study)
            measured_all=[r for j,path,r in outputs if j['scene_index']>=matrix.warmups]
            measured=[r for r in measured_all if r['status']=='accepted']
            if not measured:raise RuntimeError('No accepted measured outputs')
            cost=sum(r.get('accepted_output_seconds',r['total_seconds']) for r in measured_all)
            row={'repeat':repeat,'variant':variant.name,'measured':len(measured),'images_per_second':len(measured)/cost if result['workers']==1 else None,
                 'command_images_per_second':sum(r['status']=='accepted' for j,p,r in outputs)/result['command_seconds'],
                 'mean_output_seconds':statistics.mean(r['accepted_output_seconds'] for r in measured),
                 'mean_label_seconds':statistics.mean(sum(x['annotation_seconds'] for x in r['attempts']) for r in measured),
                 'command_seconds':result['command_seconds'],'resources':result}
            records.append(row);cells[(repeat,variant.name)]=outputs;atomic_json(root/'summary.json',records);print(json.dumps(row),flush=True)
        left,right=[cells[(repeat,v.name)] for v in matrix.variants]
        if [j['id'] for j,p,r in left]!=[j['id'] for j,p,r in right]:raise ValueError('Paired job set changed')
        for (j,p,r),(j2,p2,r2) in zip(left,right,strict=True):
            if r['status']!=r2['status']:raise RuntimeError('Initialization changed acceptance')
            if r['status']!='accepted':continue
            masks_equal=True
            with np.load(p/'masks.npz') as x,np.load(p2/'masks.npz') as y:
                masks_equal=all(np.array_equal(x[k],y[k]) for k in ['visible','full'])
            x=np.asarray(Image.open(p/'rgb.png'),dtype=np.int16);y=np.asarray(Image.open(p2/'rgb.png'),dtype=np.int16);delta=np.abs(x-y)
            comparisons.append({'repeat':repeat,'job':j['id'],'masks_equal':masks_equal,'rgb_equal':bool(np.array_equal(x,y)),
                                'rgb_mae':float(delta.mean()),'rgb_max_delta':int(delta.max())})
        atomic_json(root/'comparison.json',comparisons)
        if not all(c['masks_equal'] for c in comparisons):raise RuntimeError('Initialization changed annotation geometry')
    first,second=[v.name for v in matrix.variants]
    key='command_images_per_second' if matrix.metric=='whole-command' else 'images_per_second'
    if matrix.metric=='measured-output' and any(x['resources']['workers']!=1 for x in records):raise ValueError('Concurrent workers require the whole-command metric')
    gains=[next(x[key] for x in records if x['repeat']==i and x['variant']==second)/next(x[key] for x in records if x['repeat']==i and x['variant']==first)-1 for i in range(matrix.repetitions)]
    verdict={'metric':matrix.metric,'paired_throughput_gains':gains,'median_gain':statistics.median(gains),'all_masks_equal':all(c['masks_equal'] for c in comparisons),
             'all_rgb_equal':all(c['rgb_equal'] for c in comparisons),'comparisons':len(comparisons)}
    atomic_json(root/'verdict.json',verdict);print(json.dumps(verdict),flush=True)


if __name__=='__main__':main()
