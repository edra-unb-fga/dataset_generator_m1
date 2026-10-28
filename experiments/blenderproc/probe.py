import blenderproc as bproc
import argparse
import json
from pathlib import Path
import bpy
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from runtime import hardware_info

parser=argparse.ArgumentParser();parser.add_argument('request');parser.add_argument('output');args=parser.parse_args()
if bproc.__version__!='2.8.0' or bpy.app.version!=(4,2,1):raise RuntimeError('Pinned BlenderProc2.8.0 / Blender4.2.1 required')
bproc.init()
request=json.loads(Path(args.request).read_text())
Path(args.output).write_text(json.dumps(hardware_info(request['backend_order']),indent=2))
