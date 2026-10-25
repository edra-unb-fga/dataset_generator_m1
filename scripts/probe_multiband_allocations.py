"""Isolate traced multiband temporaries; this is not a process RSS benchmark.

Inputs are allocated before tracing. Exact equality is required. Run sequentially after timing work.
"""
import argparse
import gc
import hashlib
import json
from pathlib import Path
import subprocess
import tracemalloc

import cv2
import numpy as np

from dataset_generator_m1.identities import software_identity
from study_background_optimizations import load_module


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-ref',required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args();root=args.output_dir
    if root.exists():raise ValueError('Choose a fresh output directory')
    baseline=subprocess.run(['git','show',args.baseline_ref+':src/dataset_generator_m1/backgrounds.py'],check=True,capture_output=True).stdout
    root.mkdir(parents=True);(root/'baseline.py').write_bytes(baseline)
    (root/'current.py').write_bytes(Path('src/dataset_generator_m1/backgrounds.py').read_bytes())
    modules={name:load_module('alloc_'+name,root/(name+'.py')) for name in ['baseline','current']}
    cv2.setNumThreads(1);rng=np.random.default_rng(20261025)
    first=rng.random((1024,1024,3),dtype=np.float32);second=rng.random(first.shape,dtype=np.float32)
    mask=rng.random(first.shape[:2],dtype=np.float32);records={};reference=None
    for name,module in modules.items():
        gc.collect();tracemalloc.start()
        try:
            output=module._multiband_blend(first,second,mask,4)
            _,peak=tracemalloc.get_traced_memory()
        finally:tracemalloc.stop()
        signature=hashlib.sha256(output.tobytes()).hexdigest()
        if reference is not None and signature!=reference:raise ValueError('Kernel pixels changed')
        reference=signature;records[name]={'peak_traced_bytes':peak,'output_sha256':signature}
        del output
    result={'schema_version':1,'kind':'isolated-traced-multiband-allocation','baseline_ref':args.baseline_ref,
        'software':software_identity(),'input_shape':[1024,1024,3],'dtype':'float32','levels':4,'seed':20261025,
        'native_threads':1,'inputs_excluded':True,'exact_output_equal':True,
        'source_hashes':{name:hashlib.sha256((root/(name+'.py')).read_bytes()).hexdigest() for name in modules},'records':records,
        'limit':'Traced temporaries, not process RSS or total generation memory; includes all changes since baseline.'}
    (root/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
