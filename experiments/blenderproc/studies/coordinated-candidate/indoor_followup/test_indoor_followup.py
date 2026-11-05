import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('followup_transform', HERE / 'transform.py')
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)


def test_conditional_cap_fill_and_casters_leave_original_intact():
    spot = {'kind':'SPOT', 'power_w':751}
    scene = {'treatment': {'lamps':[spot]}, 'casters':[{'shape':'box'}]}
    combined = module.transform(scene, 'combined')
    assert len(combined['treatment']['lamps']) == 2
    assert combined['treatment']['lamps'][-1]['power_w'] == 150
    assert module.transform(scene, 'cap') == scene
    assert module.transform(scene, 'no-casters')['casters'] == []
    assert len(scene['treatment']['lamps']) == len(scene['casters']) == 1
    many = {'treatment': {'lamps':[{'kind':'AREA','power_w':900}, {'kind':'AREA','power_w':1800}]}, 'casters':[]}
    capped = module.transform(many, 'cap')
    assert abs(sum(x['power_w'] for x in capped['treatment']['lamps']) - 1200) < 1e-8
    assert capped['treatment']['lamps'][1]['power_w'] == 2 * capped['treatment']['lamps'][0]['power_w']
    assert module.transform(many, 'fill') == many


def test_verifier_rejects_changed_masks(tmp_path):
    import hashlib
    import json
    import subprocess
    import sys
    import numpy as np
    jobs = [{'id':name, 'treatment':{'lamps':[{'kind':'SPOT','power_w':751}]}, 'casters':[{'shape':'box'}]} for name in module.SELECTED]
    for variant in module.VARIANTS:
        transformed = [module.transform(job, variant) for job in jobs]
        contract = {'jobs_sha256':module.digest(transformed)}
        identity = module.digest(contract)
        folder = tmp_path / variant
        folder.mkdir()
        (folder/'study.json').write_text(json.dumps({'contract':contract,'identity':identity,'jobs':transformed}))
        for job in transformed:
            scene = folder/'scenes'/job['id'];scene.mkdir(parents=True)
            (scene/'rgb.png').write_bytes(b'visual')
            np.savez(scene/'masks.npz',visible=np.array([1]),full=np.array([1]))
            files = {name:hashlib.sha256((scene/name).read_bytes()).hexdigest() for name in ('rgb.png','masks.npz')}
            (scene/'result.json').write_text(json.dumps({'identity':identity,'job':job,'status':'accepted','files':files}))
    cmd = [sys.executable, str(HERE/'verify.py'), str(tmp_path)]
    assert subprocess.run(cmd,capture_output=True).returncode == 0
    path = tmp_path/'fill/scenes/003-base-fast/masks.npz'
    path.write_bytes(b'broken')
    assert subprocess.run(cmd,capture_output=True).returncode != 0


def test_postprocessor_gallery_reports_diagnostic_mask_differences(tmp_path):
    import hashlib
    import io
    import json
    import subprocess
    import sys
    import tarfile
    import numpy as np
    from PIL import Image

    def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
    inputs=tmp_path/'inputs';inputs.mkdir();run=tmp_path/'run';run.mkdir();output=tmp_path/'output'
    (inputs/'input.tar.gz.run.py').write_text('bootstrap');(inputs/'generate_scene_presets.py').write_text('cli')
    prefix='source/experiments/blenderproc/studies/coordinated-candidate/indoor_followup/'
    files={prefix+name:{'sha256':sha(HERE/name)} for name in ('remote.py','transform.py','verify.py','postprocess.py')}
    files['source/fake.py']={'sha256':'1234'}
    identity=module.digest({'schema_version':1,'files':files});manifest={'schema_version':1,'files':files,'identity':identity}
    with tarfile.open(inputs/'input.tar.gz','w:gz') as tar:
        data=json.dumps(manifest).encode(); info=tarfile.TarInfo('manifest.json');info.size=len(data);tar.addfile(info,io.BytesIO(data))
    jobs=[{'id':name,'seed':1,'reference_scene_index':0,'scene':{},'treatment':{'lamps':[{'kind':'SPOT','power_w':751}]},'casters':[{'shape':'box'}]} for name in module.SELECTED]
    settings={'bundle_sha256':sha(inputs/'input.tar.gz'),'bootstrap_sha256':sha(inputs/'input.tar.gz.run.py'),'cli_sha256':sha(inputs/'generate_scene_presets.py'),'remote_sha256':sha(HERE/'remote.py'),'original_study_identity':'original','original_job_hashes':{j['id']:module.digest(module.canonical_job(j)) for j in jobs}}
    (inputs/'spec.json').write_text(json.dumps(settings))
    content=tmp_path/'content';content.mkdir();(content/'spec.json').write_text(json.dumps(settings))
    for variant in module.VARIANTS:
        prepared=[module.transform(job,variant) for job in jobs]
        contract={'jobs_sha256':module.digest(prepared),'config':{'input_bundle_identity':identity},'harness_sources':{'fake.py':'1234'}}
        study_identity=module.digest(contract);folder=content/'results'/variant;folder.mkdir(parents=True)
        (folder/'study.json').write_text(json.dumps({'contract':contract,'identity':study_identity,'jobs':prepared}))
        for job in prepared:
            scene=folder/'scenes'/job['id'];scene.mkdir(parents=True)
            Image.new('RGB',(2,1),'blue').save(scene/'rgb.png')
            np.savez(scene/'masks.npz',visible=np.array([[0,1]]) if variant=='no-casters' else np.array([[1,1]]),full=np.array([[1,1]]))
            hashes={name:sha(scene/name) for name in ('rgb.png','masks.npz')}
            (scene/'result.json').write_text(json.dumps({'status':'accepted','identity':study_identity,'job':job,'files':hashes}))
    with tarfile.open(run/'results.tar.gz','w:gz') as tar:
        tar.add(content/'spec.json',arcname='spec.json');tar.add(content/'results',arcname='results')
    (run/'result-metadata.json').write_text(json.dumps({'status':'complete','sha256':sha(run/'results.tar.gz'),'bytes':(run/'results.tar.gz').stat().st_size}))
    (run/'status.json').write_text(json.dumps({'step':'closed','stop_confirmed':True}))
    cmd=[sys.executable,str(HERE/'postprocess.py'),'--run-dir',str(run),'--input-dir',str(inputs),'--output',str(output)]
    result=subprocess.run(cmd,capture_output=True,text=True)
    assert result.returncode==0, result.stderr
    report=json.loads((output/'metrics.json').read_text());assert report['complete'] and len(report['images'])==15
    assert all(not row['caster_diagnostic_masks_match'] for row in report['caster_mask_diagnostics'])
    assert (output/'index.html').is_file()
    (run/'status.json').write_text(json.dumps({'step':'closed','stop_confirmed':False}))
    cmd[-1]=str(tmp_path/'incomplete');assert subprocess.run(cmd,capture_output=True).returncode==2
