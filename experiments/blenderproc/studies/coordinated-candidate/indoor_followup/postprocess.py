"""Fail-closed recovery and paired gallery for the targeted indoor study."""
import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
LIGHTING = HERE.parents[1] / 'lighting-refinement'


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-dir',type=Path,required=True);p.add_argument('--input-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run,inputs,out=(x.resolve() for x in (a.run_dir,a.input_dir,a.output))
    if out.exists() or out.is_relative_to(run) or out.is_relative_to(inputs):raise ValueError('Output must be fresh and separate')
    spec=json.loads((inputs/'spec.json').read_text());status=json.loads((run/'status.json').read_text());meta=json.loads((run/'result-metadata.json').read_text())
    for name,key in (('input.tar.gz','bundle_sha256'),('input.tar.gz.run.py','bootstrap_sha256'),('generate_scene_presets.py','cli_sha256')):
        if sha(inputs/name)!=spec[key]:raise ValueError('Input checksum mismatch '+name)
    with tarfile.open(inputs/'input.tar.gz','r:gz') as tar:manifest=json.load(tar.extractfile('manifest.json'))
    ident=hashlib.sha256(json.dumps({k:v for k,v in manifest.items() if k!='identity'},sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if ident!=manifest['identity']:raise ValueError('Bundle identity mismatch')
    prefix='source/experiments/blenderproc/studies/coordinated-candidate/indoor_followup/'
    for name in ('remote.py','transform.py','verify.py','postprocess.py'):
        if sha(HERE/name)!=manifest['files'][prefix+name]['sha256']:raise ValueError('Source mismatch '+name)
    if sha(HERE/'remote.py')!=spec['remote_sha256']:raise ValueError('Remote checksum mismatch')
    archive=run/'results.tar.gz'
    if sha(archive)!=meta['sha256'] or archive.stat().st_size!=meta['bytes']:raise ValueError('Archive checksum mismatch')
    helper=load_module('light_postprocess',LIGHTING/'postprocess.py')
    transform=load_module('indoor_followup_transform',HERE/'transform.py')
    out.mkdir(parents=True);recovered=out/'recovered';recovered.mkdir();helper.extract(archive,recovered)
    if json.loads((recovered/'spec.json').read_text())!=spec:raise ValueError('Remote spec mismatch')
    results=recovered/'results'
    check=subprocess.run([sys.executable,str(HERE/'verify.py'),str(results)],capture_output=True,text=True)
    (out/'verification.log').write_text(check.stdout+check.stderr)
    errors=[];records=[];diagnostics=[]
    if check.returncode:errors.append('Matching verifier failed')
    else:diagnostics=json.loads(check.stdout)['diagnostics']
    for variant in transform.VARIANTS:
        study_path=results/variant/'study.json'
        if not study_path.is_file():errors.append('Missing study '+variant);continue
        study=json.loads(study_path.read_text());contract=study.get('contract',{});sources=contract.get('harness_sources',{})
        if contract.get('config',{}).get('input_bundle_identity')!=ident or not sources or any(manifest['files'].get('source/'+name,{}).get('sha256')!=value for name,value in sources.items()):errors.append('Source provenance mismatch '+variant)
        for index,job in enumerate(study.get('jobs',[])):
            try:
                if job['id'] not in transform.SELECTED:raise ValueError('Unexpected job')
                if variant=='baseline' and transform.digest(transform.canonical_job(job))!=spec['original_job_hashes'][job['id']]:raise ValueError('Original job mismatch')
                scene=results/variant/'scenes'/job['id'];result=json.loads((scene/'result.json').read_text())
                if result.get('status')!='accepted' or result.get('identity')!=study['identity'] or result.get('job')!=job:raise ValueError('Result identity mismatch')
                for name in ('rgb.png','masks.npz'):
                    wanted=result.get('files',{}).get(name)
                    if isinstance(wanted,dict):wanted=wanted.get('sha256')
                    if not wanted or sha(scene/name)!=wanted:raise ValueError('Result checksum mismatch '+name)
                with Image.open(scene/'rgb.png') as image:rgb=np.asarray(image.convert('RGB'))
                with np.load(scene/'masks.npz',allow_pickle=False) as masks:metrics=helper.stats(rgb,masks['visible'])
                dest=out/'images'/f'{variant}-{job["id"]}.png';dest.parent.mkdir(exist_ok=True);shutil.copyfile(scene/'rgb.png',dest)
                records.append({'condition':'indoor','variant':variant,'job_id':job['id'],'index':index,'image':dest.relative_to(out).as_posix(),'metrics':metrics,'seed':job['seed'],'reference_scene_index':job['reference_scene_index'],'lamps':job['treatment']['lamps'],'environment_geometry_diagnostics':result.get('environment_geometry_diagnostics'),'ground_diagnostics':result.get('ground_diagnostics'),'image_sha256':sha(dest)})
            except (OSError,ValueError,KeyError) as exc:errors.append(f'{variant}: {exc}')
    expected=len(transform.SELECTED)*len(transform.VARIANTS)
    complete=(meta.get('status')=='complete' and status.get('step')=='closed' and status.get('stop_confirmed') is True and not errors and len(records)==expected)
    report={'complete':complete,'strict_triplet_verification':check.returncode==0,'stop_confirmed':status.get('stop_confirmed'),'accepted_checksum_verified_images':len(records),'expected_images':expected,'bundle_identity':ident,'original_study_identity':spec['original_study_identity'],'variants':list(transform.VARIANTS),'conditions':['indoor'],'warnings':errors,'caster_mask_diagnostics':diagnostics,'images':records,'treatment_note':'Selected stress cases, not prevalence. Lighting masks must match; caster-off mask differences are explicitly recorded in metrics.json. Cap applies to main lights; fill only to a single spot.'}
    report['treatment_note'] += ' Caster-off mask comparison: ' + (', '.join(item['job_id'] + (' matched' if item['caster_diagnostic_masks_match'] else ' DIFFERED') for item in diagnostics) if diagnostics else 'unavailable') + '.'
    (out/'metrics.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    data=json.dumps(report,ensure_ascii=False,allow_nan=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    template=(LIGHTING/'gallery.html').read_text().replace('Stress candidates are preselected originals; confirm glare visually.','All three scenes were selected as challenging cases; they do not estimate prevalence.').replace('Click an image to inspect its triplet full screen.','Click an image to inspect all variants full screen.').replace('triplet verification','matched verification').replace('Stress candidates</label>','First two selected scenes</label>')
    (out/'index.html').write_text(template.replace('__DATA__',data))
    print(json.dumps({'complete':complete,'images':len(records),'errors':errors,'caster_mask_diagnostics':diagnostics}))
    if not complete:sys.exit(2)


if __name__=='__main__':main()
