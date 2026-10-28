#!/usr/bin/env python3
"""Apply an explicitly selected saved experimental execution profile to a pilot config."""
import argparse
import json
from pathlib import Path
from dataset_generator_m1.blender_pilot import PilotConfig, load_config
from dataset_generator_m1.blender_screen_profiles import select_screen_profile


def apply_profile(config_path, catalog_path, profile_name, output_path, resolution=None):
    config=load_config(config_path).model_dump(mode='json')
    if resolution is not None:
        config['resolution']=list(resolution)
    rule,status=select_screen_profile(catalog_path,profile_name,config['resolution'])
    for key in ('execution_profile','workers','threads'):
        config[key]=rule[key]
    validated=PilotConfig.model_validate(config).model_dump(mode='json')
    destination=Path(output_path)
    destination.parent.mkdir(parents=True,exist_ok=True)
    with destination.open('x') as f:json.dump(validated,f,indent=2);f.write('\n')
    return {'config':str(destination),'profile':profile_name,'rule':rule,'status':status}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',required=True);p.add_argument('--profile',required=True)
    p.add_argument('--catalog',default='experiments/blenderproc/execution/quick-screen-profiles.json')
    p.add_argument('--output',required=True);p.add_argument('--resolution',nargs=2,type=int)
    args=p.parse_args()
    print(json.dumps(apply_profile(args.config,args.catalog,args.profile,args.output,args.resolution),indent=2))

if __name__=='__main__':main()
