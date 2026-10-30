import importlib.util
from pathlib import Path

import pytest


def supervisor():
    spec=importlib.util.spec_from_file_location('context_colab_supervisor',Path('experiments/foreground-context/colab_supervisor.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def entry(phase, seconds, status='closed'):
    return {'phase':phase,'status':status,'start_unix':100,'end_unix':100+seconds}


def test_budget_accounts_for_prior_actual_and_reserved_two_dimensional_and_3d_allowances():
    module=supervisor()
    policy=module.SupervisorPolicy.model_validate_json(module.DEFAULT_POLICY.read_bytes())
    three={'entries':[entry('development',354)]}
    first=module.budget_check(three,{'entries':[]},'development',policy)
    assert first['conservative_total_seconds']==4854
    second=module.budget_check(three,{'entries':[entry('development',300)]},'reserved',policy)
    assert second['conservative_total_seconds']==4254
    with pytest.raises(ValueError,match='budget insufficient'):
        module.budget_check({'entries':[entry('development',1200)]},{'entries':[]},'development',policy)
    with pytest.raises(ValueError,match='unconfirmed shutdown'):
        module.budget_check({'entries':[entry('development',1,'stop-unconfirmed')]},{'entries':[]},'development',policy)
    with pytest.raises(ValueError,match='already attempted'):
        module.budget_check(three,{'entries':[entry('development',10)]},'development',policy)


def test_budget_counts_completed_reserved_3d_as_actual_instead_of_pending():
    module=supervisor()
    policy=module.SupervisorPolicy.model_validate_json(module.DEFAULT_POLICY.read_bytes())
    three={'entries':[entry('development',354),entry('reserved',500)]}
    result=module.budget_check(three,{'entries':[entry('development',300)]},'reserved',policy)
    assert result['three_d_reserved_seconds']==0
    assert result['conservative_total_seconds']==2054


def test_remote_budget_leaves_retrieval_margin():
    module=supervisor()
    policy=module.SupervisorPolicy.model_validate_json(module.DEFAULT_POLICY.read_bytes())
    assert module.remote_budget(20,policy)==600
    assert module.remote_budget(400,policy)==230
    with pytest.raises(TimeoutError,match='handoff'):
        module.remote_budget(520,policy)


def test_policy_validation_and_bundle_binding(tmp_path):
    import io
    import tarfile
    module=supervisor()
    policy_bytes=module.DEFAULT_POLICY.read_bytes()
    bundle=tmp_path/'bundle.tar.gz'
    with tarfile.open(bundle,'w:gz') as tar:
        info=tarfile.TarInfo(module.POLICY_BUNDLE_PATH);info.size=len(policy_bytes)
        tar.addfile(info,io.BytesIO(policy_bytes))
    module.check_bundle_policy(bundle,policy_bytes)
    with pytest.raises(ValueError,match='does not match'):
        module.check_bundle_policy(bundle,policy_bytes+b' ')
    policy=module.SupervisorPolicy.model_validate_json(policy_bytes).model_dump()
    policy['shutdown_watchdog_seconds']=policy['phase_allowance_seconds']
    with pytest.raises(ValueError,match='Watchdog must precede'):
        module.SupervisorPolicy.model_validate(policy)


def test_run_refuses_allocation_until_3d_reserved_closes(tmp_path,monkeypatch):
    import json
    import sys
    module=supervisor()
    three=tmp_path/'three';three.mkdir()
    (three/'budget-ledger.json').write_text(json.dumps({'entries':[entry('development',354)]}))
    bundle=tmp_path/'bundle';bundle.write_bytes(b'')
    monkeypatch.setattr(module,'check_bundle_policy',lambda *_:None)
    monkeypatch.setattr(module.subprocess,'Popen',lambda *a,**kw:pytest.fail('must not start runtime or watchdog'))
    monkeypatch.setattr(sys,'argv',['supervisor','run','--phase','development','--output',str(tmp_path/'two'),
        '--three-d-root',str(three),'--bundle',str(bundle),'--session','never-start'])
    with pytest.raises(ValueError,match='3D reserved phase must be closed'):
        module.main()


def test_one_explicit_upload_retry_charges_prior_allocation():
    module=supervisor();policy=module.SupervisorPolicy.model_validate_json(module.DEFAULT_POLICY.read_bytes())
    previous=entry('development',47)|{'retrieved':False,'error':'RuntimeError: upload exited 1'}
    three={'entries':[entry('development',354),entry('reserved',216)]}
    result=module.budget_check(three,{'entries':[previous]},'development',policy,retry_failed_development=True)
    assert result['conservative_total_seconds']==2417
    with pytest.raises(ValueError,match='upload failure'):
        module.budget_check(three,{'entries':[previous|{'error':'host-swap-out'}]},'development',policy,retry_failed_development=True)
    with pytest.raises(ValueError,match='upload failure'):
        module.budget_check(three,{'entries':[previous,previous]},'development',policy,retry_failed_development=True)
    with pytest.raises(ValueError,match='already attempted'):
        module.budget_check(three,{'entries':[previous]},'development',policy)


def test_chunk_transfer_round_trip_and_corruption_rejected(tmp_path):
    import hashlib
    import runpy
    helper=runpy.run_path('experiments/foreground-context/colab_chunking.py')
    source=tmp_path/'source';payload=b'abcde'*1000;source.write_bytes(payload)
    transfer=helper['split_bundle'](source,tmp_path/'chunks',1024)
    assert len(transfer['chunks'])==5 and all(c['bytes']<=1024 for c in transfer['chunks'])
    assert transfer['sha256']==hashlib.sha256(payload).hexdigest()
    assembled=tmp_path/'assembled'
    helper['assemble_bundle'](tmp_path/'chunks',assembled,transfer)
    assert assembled.read_bytes()==payload
    (tmp_path/'chunks'/transfer['chunks'][1]['name']).write_bytes(b'bad')
    with pytest.raises(ValueError,match='checksum or size mismatch'):
        helper['assemble_bundle'](tmp_path/'chunks',tmp_path/'bad',transfer)
    assert not (tmp_path/'bad').exists() and not (tmp_path/'bad.partial').exists()
    with pytest.raises(ValueError,match='32 MiB'):
        helper['split_bundle'](source,tmp_path/'oversized',33*1024*1024)


def test_retry_preserves_old_attempt_and_freezes_selected_evidence(tmp_path,monkeypatch):
    import hashlib
    import json
    import sys
    from types import SimpleNamespace
    module=supervisor();policy_bytes=module.DEFAULT_POLICY.read_bytes()
    bundle=tmp_path/'bundle';bundle.write_bytes(b'sealed bundle')
    three=tmp_path/'three';three.mkdir()
    (three/'budget-ledger.json').write_text(json.dumps({'entries':[entry('development',354),entry('reserved',216)]}))
    root=tmp_path/'output';dev=root/'development';dev.mkdir(parents=True)
    previous=entry('development',47)|{'retrieved':False,'error':'RuntimeError: upload exited 1'}
    ledger=root/'budget-ledger.json';ledger.write_text(json.dumps({'entries':[previous]}))
    (dev/'status.json').write_text(json.dumps({'stop_confirmed':True}))
    (dev/'phase.json').write_text(json.dumps({'bundle_sha256':module.sha(bundle),
        'supervisor_policy_sha256':hashlib.sha256(policy_bytes).hexdigest()}))
    monkeypatch.setattr(module,'check_bundle_policy',lambda *_:None)
    monkeypatch.setattr(module.subprocess,'Popen',lambda *a,**kw:SimpleNamespace())
    archive=b'recovered result'; calls=[]
    def fake_call(_colab,*args,**kwargs):
        calls.append(args)
        if args[0]=='download':
            path=Path(args[-1])
            if args[-2].endswith('.json'):
                path.write_text(json.dumps({'status':'complete','sha256':hashlib.sha256(archive).hexdigest(),'bytes':len(archive)}))
            else:path.write_bytes(archive)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(module,'call',fake_call)
    monkeypatch.setattr(sys,'argv',['supervisor','run','--phase','development','--retry-failed-development',
        '--output',str(root),'--three-d-root',str(three),'--bundle',str(bundle),'--session','retry'])
    module.main()
    entries=json.loads(ledger.read_text())['entries']
    assert entries[0]==previous and entries[1]['attempt_directory']=='development-retry-01'
    assert entries[1]['status']=='closed' and entries[1]['retrieved']
    assert json.loads((root/'development-selection.json').read_text())['attempt_directory']=='development-retry-01'
    assert any(call[0]=='upload' and call[-1].endswith('.part') for call in calls)
    review=tmp_path/'review.md';review.write_text('Reviewed')
    monkeypatch.setattr(sys,'argv',['supervisor','freeze','--output',str(root),'--review',str(review)])
    module.main()
    frozen=json.loads((root/'freeze.json').read_text())
    assert frozen['development_attempt']=='development-retry-01'
    assert frozen['development_sha256']==hashlib.sha256(archive).hexdigest()
