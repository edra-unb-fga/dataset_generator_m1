"""Differential recipe study against captured baseline/candidate source, with exact evidence checks.

Compare algorithm-preserving implementations, not recipe distributions. Each module uses the real
BackgroundSynthesizer and QA. Raw captured sources/results stay ignored. Time variants sequentially.
"""
import argparse
from contextlib import ExitStack
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter_ns
from unittest.mock import patch

import numpy as np

from dataset_generator_m1.assets import build_asset_catalog
from dataset_generator_m1.config import load_profile
from dataset_generator_m1.execution import execution_scope, plan_execution
from dataset_generator_m1.identities import digest, software_identity
from dataset_generator_m1.scene import derive_seed

OPERATIONS=['_load_rgb_float','_resize_cover_crop','_palette_transfer','_normalize_mask','_multiband_blend','_displace','_qa','_perceptual_hash']


def load_module(name,path):
    full='dataset_generator_m1._performance_'+name
    spec=importlib.util.spec_from_file_location(full,path);module=importlib.util.module_from_spec(spec)
    sys.modules[full]=module;spec.loader.exec_module(module)
    return module


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--baseline-ref',required=True)
    parser.add_argument('--copies-source',type=Path,help='Optional isolated intermediate implementation')
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--samples',type=int,default=20)
    parser.add_argument('--warmups',type=int,default=2)
    parser.add_argument('--size',type=int,default=1280)
    parser.add_argument('--recipes',nargs='+',help='Optional subset for an isolated changed operation')
    args=parser.parse_args();root=args.output_dir
    if root.exists() or args.samples<1 or args.warmups<0 or args.size<1:raise ValueError('Fresh output and valid counts required')
    resolved=load_profile(args.config);catalog=build_asset_catalog(resolved)
    selected=args.recipes or list(resolved.recipes.recipes)
    if len(set(selected))!=len(selected) or set(selected)-set(resolved.recipes.recipes):raise ValueError('Invalid recipe subset')
    source=subprocess.run(['git','show',args.baseline_ref+':src/dataset_generator_m1/backgrounds.py'],check=True,capture_output=True).stdout
    root.mkdir(parents=True);(root/'baseline.py').write_bytes(source)
    names=['baseline','current']
    if args.copies_source:
        (root/'copies.py').write_bytes(args.copies_source.read_bytes());names.insert(1,'copies')
    (root/'current.py').write_bytes(Path('src/dataset_generator_m1/backgrounds.py').read_bytes())
    modules={name:load_module(name,root/(name+'.py')) for name in names}
    synthesis={name:module.BackgroundSynthesizer(catalog,resolved.recipes,resolved.profile.assets.backgrounds.group_weights,resolved.profile.assets.backgrounds.asset_weights) for name,module in modules.items()}
    size=(round(args.size*resolved.profile.scene.canvas_scale),)*2;records=[];observed={}
    def wrapper(function,name,operation):
        def timed(*a,**kw):
            started=perf_counter_ns()
            try:return function(*a,**kw)
            finally:observed[(name,operation)]=observed.get((name,operation),0)+perf_counter_ns()-started
        return timed
    with execution_scope(plan_execution(resolved)),ExitStack() as patches:
        for name,module in modules.items():
            for operation in OPERATIONS:
                patches.enter_context(patch.object(module,operation,wrapper(getattr(module,operation),name,operation)))
        for fixture in range(-args.warmups,args.samples):
            recipe_names=list(selected);offset=(fixture+args.warmups)%len(recipe_names)
            for recipe in recipe_names[offset:]+recipe_names[:offset]:
                names=list(modules);offset=(fixture+args.warmups)%len(names);reference=None
                for name in names[offset:]+names[:offset]:
                    observed.clear();seed=derive_seed(resolved.profile.run.seed,fixture,0,'background-optimization-pair');rng=np.random.default_rng(seed)
                    started=perf_counter_ns();sample=synthesis[name].synthesize(recipe,size,rng);duration=perf_counter_ns()-started
                    evidence={'pixel_sha256':hashlib.sha256(sample.image.tobytes()).hexdigest(),'qa':sample.qa,'warnings':sample.warnings,
                        'source_assets':sample.source_assets,'sampled_parameters':sample.sampled_parameters,'graph_hash':sample.graph_hash,'rng_state':rng.bit_generator.state}
                    identity=digest(evidence)
                    if reference is None:reference=identity
                    if identity!=reference:raise RuntimeError(f'Pixels/QA/provenance/RNG changed: fixture{fixture} recipe{recipe} variant{name}')
                    if fixture>=0:
                        records.append({'fixture':fixture,'recipe':recipe,'variant':name,'duration_ns':duration,'evidence_sha256':identity,
                            'operations_ns':{op:observed.get((name,op),0) for op in OPERATIONS}})
                        with (root/'records.jsonl').open('a') as handle:handle.write(json.dumps(records[-1])+'\n')
                    del sample
                (root/'progress.json').write_text(json.dumps({'fixture':fixture,'recipe':recipe,'measured_calls':len(records)}))
            print(f'fixture{fixture} complete; exact pixels/QA/lineage/parameters/RNG matched',flush=True)
    summary={'schema_version':1,'kind':'background-implementation-study','status':'complete','samples_per_recipe':args.samples,
        'warmups_per_recipe':args.warmups,'canvas_size':size,'low_sample':args.samples<20,'software':software_identity(),
        'baseline_ref':args.baseline_ref,'sources':{name:hashlib.sha256((root/(name+'.py')).read_bytes()).hexdigest() for name in modules},
        'catalog_fingerprint':catalog.fingerprint,'all_pixels_qa_lineage_parameters_rng_equal':True,'recipes':{}}
    for recipe in selected:
        summary['recipes'][recipe]={}
        for name in modules:
            rows=[r for r in records if r['recipe']==recipe and r['variant']==name]
            summary['recipes'][recipe][name]={'median_seconds':float(np.median([r['duration_ns']/1e9 for r in rows])),
                'mean_seconds':float(np.mean([r['duration_ns']/1e9 for r in rows])),
                'median_operations_seconds':{op:float(np.median([r['operations_ns'][op]/1e9 for r in rows])) for op in OPERATIONS}}
    (root/'summary.json').write_text(json.dumps(summary,indent=2))

if __name__=='__main__':main()
