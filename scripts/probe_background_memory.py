"""Trace recipe array lifetimes; this is allocation evidence, not a throughput measurement."""
import argparse
import gc
import hashlib
import json
from pathlib import Path
import tracemalloc

import numpy as np

from dataset_generator_m1.assets import build_asset_catalog
from dataset_generator_m1.backgrounds import BackgroundSynthesizer
from dataset_generator_m1.config import load_profile
from dataset_generator_m1.execution import execution_scope, plan_execution
from dataset_generator_m1.identities import software_identity


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--samples',type=int,default=3)
    args=parser.parse_args();root=args.output_dir
    if root.exists() or args.samples<1:raise ValueError('Fresh output and positive sample count required')
    resolved=load_profile(args.config);catalog=build_asset_catalog(resolved)
    size=tuple(round(v*resolved.profile.scene.canvas_scale) for v in resolved.profile.output.image_size)
    synth=BackgroundSynthesizer(catalog,resolved.recipes,resolved.profile.assets.backgrounds.group_weights,resolved.profile.assets.backgrounds.asset_weights)
    original=synth._execute_node;nodes=[]
    def trace(node,*a,**kw):
        current,_=tracemalloc.get_traced_memory();tracemalloc.reset_peak()
        value=original(node,*a,**kw)
        _,peak=tracemalloc.get_traced_memory()
        nodes.append({'id':node.id,'op':node.op,'live_before_bytes':current,'peak_traced_bytes':peak,
            'array_bytes':value.nbytes if isinstance(value,np.ndarray) else 0,
            'dtype':str(value.dtype) if isinstance(value,np.ndarray) else None})
        return value
    synth._execute_node=trace;records=[]
    with execution_scope(plan_execution(resolved)):
        for fixture in range(args.samples):
            for name in resolved.recipes.recipes:
                nodes=[];gc.collect();tracemalloc.start()
                try:
                    sample=synth.synthesize(name,size,np.random.default_rng(20261025+fixture))
                    _,tail_peak=tracemalloc.get_traced_memory()
                    peak=max(tail_peak,*(n['peak_traced_bytes'] for n in nodes))
                finally:tracemalloc.stop()
                records.append({'fixture':fixture,'recipe':name,'peak_traced_bytes':peak,'tail_peak_bytes':tail_peak,'nodes':nodes})
                del sample
                print(f'{fixture} {name}: {peak/2**20:.1f} MiB traced',flush=True)
    root.mkdir(parents=True)
    result={'schema_version':1,'software':software_identity(),'canvas_size':size,'samples_per_recipe':args.samples,
        'background_source_sha256':hashlib.sha256(Path('src/dataset_generator_m1/backgrounds.py').read_bytes()).hexdigest(),
        'limit':'Traced allocation includes live arrays and selected native NumPy allocations; excludes interpreter/import baselines and untracked native storage.',
        'records':records}
    (root/'summary.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
