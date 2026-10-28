"""Save a machine-specific BlenderProc execution policy and its measurement basis."""
import argparse
import json
from pathlib import Path
import subprocess
import psutil
from dataset_generator_m1.blender_guard_policy import adaptive_guards

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--policy',required=True,help='Existing execution profile catalog')
parser.add_argument('--settings',required=True,help='Adaptive guard parameters')
parser.add_argument('--output',required=True,help='New output policy JSON (must not exist)')
gpu_options=parser.add_mutually_exclusive_group()
gpu_options.add_argument('--gpu',action='store_true',help='Require and guard exactly one NVIDIA GPU')
gpu_options.add_argument('--disable-gpu-guard',action='store_true',help='Explicitly disable an inherited VRAM guard')
args=parser.parse_args()
policy=json.loads(Path(args.policy).read_text())
settings=json.loads(Path(args.settings).read_text())
host=psutil.virtual_memory()
observed={'total_bytes':host.total,'available_bytes':host.available}
if args.gpu:
    result=subprocess.run(['nvidia-smi','--query-gpu=memory.total,memory.free','--format=csv,noheader,nounits'],check=True,text=True,capture_output=True,timeout=10)
    devices=[list(map(float,line.split(','))) for line in result.stdout.splitlines()]
    if len(devices)!=1 or len(devices[0])!=2:
        raise ValueError('Expected exactly one NVIDIA GPU with memory telemetry')
    observed.update(gpu_total_mib=devices[0][0],gpu_free_mib=devices[0][1])
policy['guards']=adaptive_guards(policy['guards'],settings,**observed)
if args.disable_gpu_guard:policy['guards']['min_gpu_free_mib']=None
from dataset_generator_m1.blender_execution import Catalog
Catalog.model_validate(policy)
output=Path(args.output);basis=output.with_suffix(output.suffix+'.basis.json')
if output.exists() or basis.exists():raise FileExistsError('Output policy or measurement basis already exists')
basis.write_text(json.dumps({'settings':settings,'observed':observed,'resolved_guards':policy['guards'],
                             'gpu_guard_disabled_explicitly':args.disable_gpu_guard},indent=2)+'\n')
try:output.write_text(json.dumps(policy,indent=2)+'\n')
except BaseException:
    basis.unlink(missing_ok=True)
    raise
print(json.dumps({'policy':str(output),'basis':str(basis),'guards':policy['guards']},indent=2))
