"""Standalone optional BlenderProc workflow; core CLI/runtime remains unchanged."""
import argparse
from pathlib import Path
import json
from dataset_generator_m1.blender_pilot import prepare,run_study,export_study,report,fetch_assets,bridge_composers

parser=argparse.ArgumentParser(description=__doc__)
sub=parser.add_subparsers(dest='command',required=True)
p=sub.add_parser('bridge');p.add_argument('--assets-dir',required=True);p.add_argument('--foreground-dir',required=True);p.add_argument('--output-dir',required=True);p.add_argument('--workers',type=int,default=1)
p=sub.add_parser('assets');p.add_argument('--manifest-dir',default='experiments/blenderproc/assets');p.add_argument('--output-dir',required=True)
p=sub.add_parser('prepare');p.add_argument('--config',required=True);p.add_argument('--output-dir',required=True)
p=sub.add_parser('render');p.add_argument('--output-dir',required=True);p.add_argument('--blenderproc',required=True);p.add_argument('--blender-install-path',required=True);p.add_argument('--jobs',nargs='*')
p=sub.add_parser('export');p.add_argument('--output-dir',required=True);p.add_argument('--yolo',action='store_true')
p=sub.add_parser('report');p.add_argument('--output-dir',required=True)
args=parser.parse_args()
if args.command=='bridge':result=bridge_composers(args.assets_dir,args.foreground_dir,args.output_dir,workers=args.workers)
elif args.command=='assets':result=fetch_assets(args.manifest_dir,args.output_dir)
elif args.command=='prepare':
    value=prepare(args.config,args.output_dir);result={'identity':value['identity'],'jobs':len(value['jobs'])}
elif args.command=='render':result=run_study(args.output_dir,args.blenderproc,args.blender_install_path,job_ids=args.jobs)
elif args.command=='export':
    result=export_study(args.output_dir,yolo=args.yolo)
else:
    value=report(args.output_dir);result={key:value[key] for key in ('accepted','rejected','planned')}
print(json.dumps(result,indent=2))

if args.command=='render' and result['status'] not in {'complete','budget-limited'}:raise SystemExit(1)
