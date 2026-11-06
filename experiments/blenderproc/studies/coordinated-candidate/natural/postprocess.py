"""Recover, verify and build a natural-mixture gallery from a closed supervisor run."""
import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', required=True, type=Path)
    parser.add_argument('--input-dir', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    run, inputs, output = (p.resolve() for p in (args.run_dir, args.input_dir, args.output))
    if output.exists() or output.is_relative_to(run) or output.is_relative_to(inputs):
        raise ValueError('Output must be fresh and separate from inputs and run')
    spec = json.loads((inputs / 'spec.json').read_text())
    for name, key in [('input.tar.gz','bundle_sha256'), ('input.tar.gz.run.py','bootstrap_sha256'), ('generate_scene_presets.py','cli_sha256')]:
        if sha(inputs / name) != spec[key]: raise ValueError('Input checksum mismatch: ' + name)
    with tarfile.open(inputs / 'input.tar.gz', 'r:gz') as bundle:
        manifest = json.load(bundle.extractfile('manifest.json'))
    actual_identity = hashlib.sha256(json.dumps({k:v for k,v in manifest.items() if k != 'identity'}, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if manifest['identity'] != actual_identity: raise ValueError('Bundle identity mismatch')
    for name in ('remote.py', 'verify.py'):
        key = 'source/experiments/blenderproc/studies/coordinated-candidate/natural/' + name
        if manifest['files'][key]['sha256'] != sha(HERE / name): raise ValueError('Bundled source mismatch: '+name)
    if spec['remote_sha256'] != sha(HERE / 'remote.py'): raise ValueError('Remote spec mismatch')
    meta = json.loads((run / 'result-metadata.json').read_text())
    status = json.loads((run / 'status.json').read_text())
    archive = run / 'results.tar.gz'
    if archive.stat().st_size != meta['bytes'] or sha(archive) != meta['sha256']: raise ValueError('Archive checksum mismatch')
    extractor = importlib.util.spec_from_file_location('safe_extract', HERE.parents[1] / 'lighting-refinement/postprocess.py')
    module = importlib.util.module_from_spec(extractor); extractor.loader.exec_module(module)
    output.mkdir(parents=True); recovered = output / 'recovered'; recovered.mkdir()
    module.extract(archive, recovered)
    if json.loads((recovered / 'spec.json').read_text()) != spec: raise ValueError('Remote spec mismatch')
    study = recovered / 'results/natural'
    check = subprocess.run([sys.executable, str(HERE / 'verify.py'), str(study), str(spec['scenes'])], capture_output=True, text=True)
    (output / 'verification.log').write_text(check.stdout + check.stderr)
    provenance_ok = False
    if (study / 'study.json').is_file():
        contract = json.loads((study / 'study.json').read_text()).get('contract', {})
        sources = contract.get('harness_sources', {})
        provenance_ok = (contract.get('config', {}).get('input_bundle_identity') == actual_identity and bool(sources) and all(manifest['files'].get('source/' + name, {}).get('sha256') == fingerprint for name, fingerprint in sources.items()))
    complete = provenance_ok and meta.get('status') == 'complete' and status.get('step') == 'closed' and status.get('stop_confirmed') is True and check.returncode == 0
    evidence = {'complete': complete, 'verified': check.returncode == 0, 'provenance_verified': provenance_ok, 'stop_confirmed': status.get('stop_confirmed'), 'remote_status': meta.get('status'), 'bundle_identity': actual_identity, 'archive_sha256': meta['sha256'], 'expected_images': spec['scenes'], 'note': 'Fresh seeds reuse the original reference assets; sampled proportions do not establish calibrated prevalence.'}
    (output / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    if complete:
        gallery = output / 'gallery'
        subprocess.run([sys.executable, str(ROOT / 'scripts/collect_3d_review_gallery.py'), str(recovered / 'results'), str(gallery)], check=True)
        subprocess.run([sys.executable, str(ROOT / 'scripts/build_scene_review_gallery.py'), str(gallery / 'manifest.json'), '--output', str(gallery / 'index.html')], check=True)
    print(json.dumps(evidence))
    if not complete: sys.exit(2)


if __name__ == '__main__': main()
