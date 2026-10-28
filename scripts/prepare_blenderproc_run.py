#!/usr/bin/env python3
"""Create a fresh study with a recorded, machine-derived resource policy."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

from dataset_generator_m1.blender_pilot import PilotConfig, load_config, prepare
from dataset_generator_m1.blender_execution import load_catalog
from dataset_generator_m1.blender_screen_profiles import select_screen_profile

ROOT=Path(__file__).resolve().parents[1]


def prepare_run(config_path, output_dir, *, screen_profile=None, gpu_guard='auto',
                guard_settings=None, screen_catalog=None):
    """Resolve hardware once; retain the config and guard basis alongside the study.

    Resuming the study uses its frozen policy. A fresh preparation requires a fresh output directory.
    """
    output=Path(output_dir).resolve()
    if output.exists():raise FileExistsError('Use a fresh preparation output directory')
    if gpu_guard not in ('auto','required','off'):raise ValueError('Invalid GPU guard mode')
    config=load_config(config_path).model_dump(mode='json')
    screen=Path(screen_catalog or ROOT/'experiments/blenderproc/execution/quick-screen-profiles.json')
    status=None
    if screen_profile:
        rule,status=select_screen_profile(screen,screen_profile,config['resolution'])
        for key in ('execution_profile','workers','threads'):config[key]=rule[key]
    settings=Path(guard_settings or ROOT/'experiments/blenderproc/execution/adaptive-guards.json').resolve()
    source_policy=Path(config['execution_policy']) if config.get('execution_policy') else ROOT/'experiments/blenderproc/execution/profiles.json'
    catalog=load_catalog(source_policy)
    explicit=next((p for p in catalog.profiles if p.id==config['execution_profile']),None)
    guard_gpu=(gpu_guard=='required' or gpu_guard=='auto' and shutil.which('nvidia-smi') is not None
               and (explicit is None or explicit.settings.device=='GPU'))
    if gpu_guard=='auto' and not guard_gpu and explicit is not None and explicit.settings.device=='GPU':
        raise ValueError('GPU profile requires NVIDIA telemetry or explicit --gpu-guard off')
    output.mkdir(parents=True)
    policy=output/'execution-policy.json';config_file=output/'config.json';status_file=output/'setup-status.json'
    try:
        cmd=[sys.executable,str(ROOT/'scripts/blenderproc_adaptive_guards.py'),'--policy',str(source_policy),
             '--settings',str(settings),'--output',str(policy)]
        if guard_gpu:cmd.append('--gpu')
        elif gpu_guard=='off':cmd.append('--disable-gpu-guard')
        try:subprocess.run(cmd,check=True,capture_output=True,text=True,timeout=30)
        except subprocess.CalledProcessError as exc:
            raise RuntimeError('Adaptive guard setup failed: '+exc.stderr.strip()) from exc
        config['execution_policy']=str(policy)
        resolved=PilotConfig.model_validate(config).model_dump(mode='json')
        config_file.write_text(json.dumps(resolved,indent=2)+'\n')
        study=prepare(config_file,output/'study')
        basis=json.loads((output/'execution-policy.json.basis.json').read_text())
        value={'status':'complete','study':str(output/'study'),'study_identity':study['identity'],
               'execution_policy':str(policy),'guard_basis':str(output/'execution-policy.json.basis.json'),
               'guards':basis['resolved_guards'],'gpu_guard_measured':guard_gpu,
               'gpu_guard_active':basis['resolved_guards'].get('min_gpu_free_mib') is not None,
               'screen_profile':screen_profile,
               'screen_status':status,
               'warning':('No VRAM telemetry was measured; automatic GPU selection may not be guarded.'
                   if gpu_guard=='auto' and not guard_gpu and explicit is None else None),
               'note':'Frozen guard policy; rerun setup to measure a different machine or starting headroom.'}
        status_file.write_text(json.dumps(value,indent=2)+'\n')
        return value
    except BaseException as exc:
        status_file.write_text(json.dumps({'status':'failed','error':f'{type(exc).__name__}: {exc}'},indent=2)+'\n')
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True);parser.add_argument('--output-dir',required=True)
    parser.add_argument('--screen-profile',help='Optional explicit experimental saved profile')
    parser.add_argument('--screen-catalog',help='Optional saved screen-profile catalog')
    parser.add_argument('--guard-settings',help='Optional adaptive-guard parameters JSON')
    parser.add_argument('--gpu-guard',choices=('auto','required','off'),default='auto',
                        help='NVIDIA VRAM guard: auto, explicitly require it, or explicitly disable it')
    args=parser.parse_args()
    print(json.dumps(prepare_run(args.config,args.output_dir,screen_profile=args.screen_profile,
        gpu_guard=args.gpu_guard,guard_settings=args.guard_settings,screen_catalog=args.screen_catalog),indent=2))


if __name__=='__main__':main()
