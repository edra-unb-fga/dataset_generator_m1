#!/usr/bin/env python3
"""Apply an explicitly selected saved experimental execution profile to a pilot config."""
import argparse
import json
from pathlib import Path
from dataset_generator_m1.blender_pilot import PilotConfig, load_config


def apply_profile(config_path, catalog_path, profile_name, output_path, resolution=None):
    config=load_config(config_path).model_dump(mode='json')
    catalog=json.loads(Path(catalog_path).read_text())
    if catalog.get('schema_version')!=1 or profile_name not in catalog.get('profiles',{}):
        raise ValueError('Unknown or invalid execution profile')
    if resolution is not None:
        config['resolution']=list(resolution)
    pixels=config['resolution'][0]*config['resolution'][1]
    rules=catalog['profiles'][profile_name]['rules']
    rule=next((x for x in rules if x['max_pixels'] is None or pixels<=x['max_pixels']),None)
    if rule is None:raise ValueError('Profile has no rule for this resolution')
    for key in ('execution_profile','workers','threads'):
        config[key]=rule[key]
    validated=PilotConfig.model_validate(config).model_dump(mode='json')
    destination=Path(output_path)
    destination.parent.mkdir(parents=True,exist_ok=True)
    with destination.open('x') as f:json.dump(validated,f,indent=2);f.write('\n')
    return {'config':str(destination),'profile':profile_name,'rule':rule,'status':catalog['profiles'][profile_name]['status']}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',required=True);p.add_argument('--profile',required=True)
    p.add_argument('--catalog',default='experiments/blenderproc/execution/quick-screen-profiles.json')
    p.add_argument('--output',required=True);p.add_argument('--resolution',nargs=2,type=int)
    args=p.parse_args()
    print(json.dumps(apply_profile(args.config,args.catalog,args.profile,args.output,args.resolution),indent=2))

if __name__=='__main__':main()
