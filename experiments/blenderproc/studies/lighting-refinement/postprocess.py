#!/usr/bin/env python3
"""Verify recovered evidence and create a self-contained local lighting review."""
import argparse
import hashlib
import html
import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path, PurePosixPath

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
VARIANTS = ('baseline', 'soft', 'soft-fill')
CONDITIONS = ('outdoor-night', 'indoor')

def study_layout(relative_parts):
    if relative_parts == ('round3',):
        return ('open', 'outdoor-night', 'indoor'), ('baseline', 'broad', 'soft')
    if relative_parts in ((), ('round2',)):
        return CONDITIONS, VARIANTS
    raise ValueError('Unknown study scripts directory')


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''): h.update(chunk)
    return h.hexdigest()


def extract(archive, dest):
    # Reject links and traversal; allow repeated regular entries only if byte-identical.
    with tarfile.open(archive, 'r:gz') as tar:
        seen = {}; total = 0
        for member in tar:
            name = PurePosixPath(member.name)
            if name.is_absolute() or '..' in name.parts or not name.parts:
                raise ValueError(f'Unsafe archive path: {member.name}')
            key = name.as_posix(); target = dest.joinpath(*name.parts)
            if member.isdir():
                if key in seen and seen[key] != ('directory', None): raise ValueError(f'Conflicting archive entry: {key}')
                seen[key] = ('directory', None); target.mkdir(parents=True, exist_ok=True); continue
            if not member.isfile(): raise ValueError(f'Unsupported archive member: {member.name}')
            total += member.size
            if total > 4 * 1024**3: raise ValueError('Archive exceeds 4 GiB extraction limit')
            if key in seen:
                if seen[key][0] != 'file': raise ValueError(f'Conflicting archive entry: {key}')
                h = hashlib.sha256()
                with tar.extractfile(member) as source:
                    for chunk in iter(lambda: source.read(1024 * 1024), b''): h.update(chunk)
                if h.hexdigest() != seen[key][1]: raise ValueError(f'Conflicting duplicate archive file: {key}')
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            h = hashlib.sha256()
            with tar.extractfile(member) as source, target.open('xb') as out:
                for chunk in iter(lambda: source.read(1024 * 1024), b''):
                    out.write(chunk); h.update(chunk)
            seen[key] = ('file', h.hexdigest())


def stats(rgb, visible):
    if visible.ndim == 3: visible = visible.any(axis=0)
    if visible.ndim != 2 or visible.shape != rgb.shape[:2]: raise ValueError('Mask/image dimensions differ')
    target = rgb[visible.astype(bool)]
    result = {'image_mean_rgb': float(rgb.mean()), 'image_fraction_rgb_all_ge250': float((rgb >= 250).all(axis=2).mean()),
              'image_fraction_rgb_all_le10': float((rgb <= 10).all(axis=2).mean()), 'visible_pixels': int(len(target)),
              'visible_target_mean_rgb': None, 'visible_target_fraction_rgb_all_ge250': None,
              'visible_target_fraction_any_channel_ge250': None, 'visible_target_fraction_rgb_all_le10': None}
    if len(target):
        result.update(visible_target_mean_rgb=float(target.mean()),
                      visible_target_fraction_rgb_all_ge250=float((target >= 250).all(axis=1).mean()),
                      visible_target_fraction_any_channel_ge250=float((target >= 250).any(axis=1).mean()),
                      visible_target_fraction_rgb_all_le10=float((target <= 10).all(axis=1).mean()))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True, help='Closed supervisor output directory')
    parser.add_argument('--input-dir', type=Path, required=True, help='Sealed input directory used for this run')
    parser.add_argument('--output', type=Path, required=True, help='Fresh output directory')
    parser.add_argument('--study-scripts', type=Path, default=HERE, help='Study directory containing the matching verify.py')
    args = parser.parse_args(); run = args.run_dir.resolve(); inputs = args.input_dir.resolve(); out = args.output.resolve(); scripts = args.study_scripts.resolve()
    relative_scripts=scripts.relative_to(HERE)
    conditions, variants = study_layout(relative_scripts.parts)
    if out.exists(): raise FileExistsError('Use a fresh output directory')
    if out.is_relative_to(run) or out.is_relative_to(inputs): raise ValueError('Output must be outside run and input directories')
    meta = json.loads((run/'result-metadata.json').read_text()); status = json.loads((run/'status.json').read_text())
    spec = json.loads((inputs/'spec.json').read_text()); archive = run/'results.tar.gz'
    if sha(archive) != meta.get('sha256') or archive.stat().st_size != meta.get('bytes'): raise ValueError('Result archive hash or size mismatch')
    for name, key in [('input.tar.gz', 'bundle_sha256'), ('input.tar.gz.run.py', 'bootstrap_sha256'), ('generate_scene_presets.py', 'cli_sha256')]:
        if sha(inputs/name) != spec.get(key): raise ValueError(f'Sealed input mismatch: {name}')
    with tarfile.open(inputs/'input.tar.gz', 'r:gz') as bundle:
        bundle_manifest=json.load(bundle.extractfile('manifest.json'))
    raw={k:v for k,v in bundle_manifest.items() if k != 'identity'}
    identity=hashlib.sha256(json.dumps(raw,sort_keys=True,separators=(',', ':')).encode()).hexdigest()
    if bundle_manifest.get('identity') != identity: raise ValueError('Invalid bundle manifest identity')
    source_prefix='source/experiments/blenderproc/studies/lighting-refinement/' + (relative_scripts.as_posix()+'/' if relative_scripts.parts else '')
    remote_name=source_prefix+'remote.py'
    if bundle_manifest['files'][remote_name]['sha256'] != spec.get('remote_sha256'): raise ValueError('Bundled remote script fingerprint mismatch')
    expected = spec.get('scenes_per_condition')
    if type(expected) is not int or not 1 <= expected <= 8: raise ValueError('Invalid expected count in spec')
    out.mkdir(parents=True); evidence = out/'evidence'; evidence.mkdir()
    # Preserve operator-visible control evidence and full sealed inputs, with a manifest of copied bytes.
    manifest = {}
    for base, folder, names in [(run,'run',['result-metadata.json','status.json','cost-gate.json','cost-gate-allocated.json','usage-before.txt','usage-allocated.txt','usage-after.txt','watchdog.log','transfer.json']),
                                 (inputs,'input',['input.tar.gz','input.tar.gz.run.py','generate_scene_presets.py','spec.json'])]:
        for name in names:
            source = base/name
            if source.is_file():
                target=evidence/folder/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
                manifest[f'{folder}/{name}']={'sha256':sha(target),'bytes':target.stat().st_size}
    manifest['results.tar.gz']={'sha256':sha(archive),'bytes':archive.stat().st_size,'source':str(archive)}
    (evidence/'preserved-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    unpacked=out/'recovered';unpacked.mkdir();extract(archive,unpacked)
    remote_spec=unpacked/'spec.json'
    if not remote_spec.is_file() or json.loads(remote_spec.read_text()) != spec: raise ValueError('Remote spec differs from sealed local spec')
    results=unpacked/'results'; verifier=scripts/'verify.py'
    check=subprocess.run([sys.executable,str(verifier),str(results),str(expected)],capture_output=True,text=True)
    (out/'verification.log').write_text(check.stdout+check.stderr)
    warnings=[]; records=[]
    for condition in conditions:
        for variant in variants:
            batch=results/f'{condition}-{variant}'; study_path=batch/'study.json'
            if not study_path.exists(): warnings.append(f'Missing {batch.name} study');continue
            study=json.loads(study_path.read_text())
            contract=study.get('contract', {})
            if contract.get('config', {}).get('input_bundle_identity') != identity:
                warnings.append(f'{batch.name}: bundle identity differs')
            for name, fingerprint in contract.get('harness_sources', {}).items():
                if bundle_manifest['files'].get('source/'+name, {}).get('sha256') != fingerprint:
                    warnings.append(f'{batch.name}: source fingerprint mismatch: {name}')
            if not contract.get('harness_sources'): warnings.append(f'{batch.name}: missing source fingerprints')
            for i, job in enumerate(study.get('jobs', [])):
                if not isinstance(job.get('id'), str) or Path(job['id']).name != job['id'] or job['id'] in ('.', '..'):
                    warnings.append(f'Unsafe job ID in {batch.name}'); continue
                path=batch/'scenes'/job['id']; result_path=path/'result.json'
                if not result_path.exists(): warnings.append(f'Missing {batch.name}/{job["id"]}');continue
                try:
                    result=json.loads(result_path.read_text())
                    if result.get('status')!='accepted' or result.get('identity') != study['identity'] or result.get('job') != job: raise ValueError('Result status, identity or job mismatch')
                    for name in ('rgb.png','masks.npz'):
                        expected_hash=result.get('files',{}).get(name)
                        if isinstance(expected_hash,dict): expected_hash=expected_hash.get('sha256')
                        if not expected_hash or sha(path/name)!=expected_hash: raise ValueError(f'{name} checksum mismatch')
                    with Image.open(path/'rgb.png') as img: rgb=np.asarray(img.convert('RGB'))
                    with np.load(path/'masks.npz',allow_pickle=False) as masks:
                        if not {'visible','full'}.issubset(masks.files): raise ValueError('Missing masks')
                        metrics=stats(rgb,masks['visible'])
                    dest=out/'images'/f'{condition}-{variant}-{job["id"]}.png';dest.parent.mkdir(exist_ok=True)
                    shutil.copyfile(path/'rgb.png',dest)
                    records.append({'condition':condition,'variant':variant,'job_id':job['id'],'index':i,
                        'stress_candidate':i<2,'image':dest.relative_to(out).as_posix(),'metrics':metrics,
                        'seed':job['seed'],'scene_index':job['scene_index'],'reference_scene_index':job['reference_scene_index'],
                        'lamps':job['treatment']['lamps'],'environment_geometry_diagnostics':result.get('environment_geometry_diagnostics'),
                        'ground_diagnostics':result.get('ground_diagnostics'),'image_sha256':sha(dest)})
                except (OSError, ValueError, KeyError) as exc: warnings.append(f'{batch.name}/{job.get("id")}: {exc}')
    verifier_matches_bundle = sha(verifier) == bundle_manifest['files'].get(source_prefix+'verify.py',{}).get('sha256')
    if not verifier_matches_bundle: warnings.append('Verifier fingerprint differs from bundled source')
    expected_images = expected * len(conditions) * len(variants)
    complete=(meta.get('status')=='complete' and status.get('step')=='closed' and status.get('stop_confirmed') is True and check.returncode==0 and len(records)==expected_images and not warnings)
    report={'complete':complete,'remote_status':meta.get('status'),'controller_status':status.get('step'),'stop_confirmed':status.get('stop_confirmed'),
            'strict_triplet_verification':check.returncode==0,'strict_verifier_sha256':sha(verifier),'verifier_matches_bundle':verifier_matches_bundle,'bundle_identity':identity,
            'conditions':conditions,'variants':variants,'expected_images':expected_images,'accepted_checksum_verified_images':len(records),'warnings':warnings,'images':records,
            'metrics_note':'Display RGB 0–255; visible target is the union of visible masks. Thresholds are display-pixel diagnostics, not calibrated radiometry.',
            'treatment_note': ('Baseline: original; broad and soft: matched candidate range transformations, with lamp types and colors held fixed.' if relative_scripts.parts == ('round3',) else 'Baseline: original; soft: broader geometry and 0.8 main lamp power; soft-fill: same plus 60 W fill.' if relative_scripts.parts else 'Baseline: original; soft: broader geometry at original power; soft-fill: same plus 120 W fill.')}
    (out/'metrics.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    data=json.dumps(report,ensure_ascii=False,allow_nan=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    template=(HERE/'gallery.html').read_text();(out/'index.html').write_text(template.replace('__DATA__',data))
    print(json.dumps({'complete':complete,'images':len(records),'expected':expected_images,'warnings':len(warnings),'output':str(out)}))
    if not complete: sys.exit(2)


if __name__=='__main__': main()
