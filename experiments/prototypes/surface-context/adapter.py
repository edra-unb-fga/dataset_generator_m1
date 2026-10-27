"""Prepare and verify a sealed, isolated derivative of a prepared Blender pilot."""
import copy
import hashlib
import json
from pathlib import Path

from dataset_generator_m1.blender_pilot import atomic_json, digest, digest_file, load_study, validate_inputs
from dataset_generator_m1.blender_execution import load_execution


def verify_prototype(study, manifest_path, renderer):
    manifest_path = Path(manifest_path).resolve()
    manifest = json.loads(manifest_path.read_text())
    sealed = study['contract']['prototype']
    if digest(manifest) != sealed['manifest_sha256']:
        raise ValueError('Prototype manifest changed')
    entry = Path(manifest['entry_script']).resolve()
    if digest_file(entry) != sealed['entry_sha256'] or digest_file(entry) != manifest['entry_sha256']:
        raise ValueError('Prototype entry changed')
    if manifest['kind'] not in ('relief', 'imported'):
        raise ValueError('Unknown prototype')
    if manifest['kind'] == 'imported' and len(manifest['assets']) != 2:
        raise ValueError('Imported prototype needs two assets')
    if manifest['kind'] == 'relief' and manifest['assets']:
        raise ValueError('Relief prototype has no imported assets')
    for item in manifest['assets']:
        path = Path(item['path']).resolve()
        if path.suffix.lower() != '.glb' or digest_file(path) != item['sha256']:
            raise ValueError('Prototype asset changed: '+str(path))
        provenance = json.loads(Path(item['provenance_manifest']).read_text())
        if digest(provenance) != item['provenance_sha256'] or provenance['license'] != 'CC0-1.0' or provenance['derived_glb']['sha256'] != item['sha256']:
            raise ValueError('Prototype asset provenance changed')
    validate_inputs(study, Path(renderer).resolve())
    return manifest


def prepare_prototype(base_study, destination, manifest_path):
    """Derive a fresh study; manifest job_ids explicitly selects one to four jobs."""
    base = Path(base_study).resolve()
    if base.is_file(): base = base.parent
    dest = Path(destination).resolve()
    if dest.exists(): raise ValueError('Destination must be new')
    study = load_study(base)
    execution = load_execution(base, study)
    manifest_path = Path(manifest_path).resolve()
    manifest = json.loads(manifest_path.read_text())
    ids = manifest['job_ids']
    if not 1 <= len(ids) <= 4 or len(ids) != len(set(ids)):
        raise ValueError('Select one to four unique jobs')
    jobs = {job['id']: job for job in study['jobs']}
    if not set(ids) <= jobs.keys(): raise ValueError('Unknown prototype job')
    result = copy.deepcopy(study)
    result['jobs'] = [jobs[job_id] for job_id in ids]
    result['contract']['jobs_sha256'] = digest(result['jobs'])
    result['contract']['prototype'] = {'base_study_identity':study['identity'], 'manifest_sha256':digest(manifest), 'entry_sha256':manifest['entry_sha256']}
    result['identity'] = digest(result['contract'])
    verify_prototype(result, manifest_path, manifest['renderer'])
    dest.mkdir(parents=True)
    atomic_json(dest/'study.json', result)
    execution['study_identity'] = result['identity']
    atomic_json(dest/'execution.json', execution)
    load_study(dest); load_execution(dest, result)
    return result


def write_manifest(path, *, kind, renderer, job_ids, provenance_manifests=()):
    """Construct a portable manifest after copying assets into the execution host."""
    path = Path(path).resolve()
    if path.exists(): raise ValueError('Manifest already exists')
    entry = Path(__file__).resolve().with_name('render_context.py')
    assets = []
    for file in provenance_manifests:
        file = Path(file).resolve(); provenance = json.loads(file.read_text())
        model = file.parent/provenance['derived_glb']['path']
        assets.append({'path':str(model.resolve()), 'sha256':digest_file(model), 'provenance_manifest':str(file), 'provenance_sha256':digest(provenance)})
    manifest={'kind':kind, 'renderer':str(Path(renderer).resolve()), 'entry_script':str(entry), 'entry_sha256':digest_file(entry), 'job_ids':list(job_ids), 'assets':assets}
    if kind not in ('relief','imported') or len(assets) != (2 if kind == 'imported' else 0):
        raise ValueError('Choose relief with no assets or imported with two')
    atomic_json(path, manifest)
    return manifest
