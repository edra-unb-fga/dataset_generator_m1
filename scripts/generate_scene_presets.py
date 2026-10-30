#!/usr/bin/env python3
"""List, resolve or prepare experimental procedural physical scenes."""
import argparse
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from dataset_generator_m1.blender_pilot import load_config, prepare
from dataset_generator_m1.scene_presets import catalog, load_preset, sample
from dataset_generator_m1.blender_pilot import EnvironmentGeometrySettings, Treatment

parser = argparse.ArgumentParser(description=__doc__)
sub = parser.add_subparsers(dest='command', required=True)
listing=sub.add_parser('list')
listing.add_argument('--details', action='store_true', help='Show full preset data')
for name in ('resolve', 'prepare'):
    p = sub.add_parser(name)
    p.add_argument('--config', required=True)
    choice=p.add_mutually_exclusive_group(required=True)
    choice.add_argument('--preset')
    choice.add_argument('--preset-file')
    p.add_argument('--output', required=True)
args = parser.parse_args()
if args.command == 'list':
    presets=[load_preset(p.stem) for p in sorted(catalog().glob('*.json'))]
    print(json.dumps([p.model_dump(mode='json') if args.details else p.id for p in presets], indent=2))
else:
    config = load_config(args.config, procedural=load_preset(args.preset, path=args.preset_file))
    resolved=sample(config.procedural, config.seed, 0, config.treatments[0].model_dump(mode='json'),
        (config.environment_geometry_settings or EnvironmentGeometrySettings()).model_dump(mode='json'),
        len(config.grounds), len(config.environments))
    Treatment.model_validate(resolved['treatment'])
    data = config.model_dump(mode='json')
    if args.command == 'resolve':
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('x') as file:
            file.write(json.dumps(data, indent=2)+'\n')
    else:
        with tempfile.TemporaryDirectory() as tmp:
            config_path=Path(tmp)/'config.json'
            config_path.write_text(json.dumps(data))
            study=prepare(config_path,args.output)
        print(json.dumps({'identity':study['identity'],'jobs':len(study['jobs']),'output':str(Path(args.output).resolve())}))
