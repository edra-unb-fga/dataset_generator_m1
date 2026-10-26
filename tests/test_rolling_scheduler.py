"""Adversarial completion/control cases exercise the real coordinator and store."""
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
import threading
import time

import numpy as np
import pytest

import dataset_generator_m1.generator as generator
from dataset_generator_m1.config import load_profile
from dataset_generator_m1.generator import GenerationOptions, generate_pool
from dataset_generator_m1.run_control import request_run_action, run_status
from dataset_generator_m1.runstore import RunStore


def fixture():
    return load_profile('examples/configs/landing-pad_minimal.yaml', overrides={
        'output.image_size': [192, 128], 'run.num_images': 6,
        'execution.max_in_flight': 2, 'report.qa_samples': 0,
    })


def result(slot, attempt=0):
    return {'accepted': True, 'image': np.full((128,192,3),slot,np.uint8),
            'mask_archive': b'', 'rejections': [], 'record': {
        'schema_version':2,'slot':slot,'candidate_attempt':attempt,'geometry_signature':f'slot-{slot}',
        'intentional_negative':True,'attempted_instances':0,'annotations':[],'rejected_instances':[],
        'mask_evidence':{'schema_version':1,'format':'npz-cropped-alpha-v1','sha256':hashlib.sha256(b'').hexdigest(),
                         'byte_count':0,'image_size':[192,128],'alpha_threshold':8,'instances':[]},
        'background':{'recipe_id':'direct','node_timings_ns':{},'qa':{},'warnings':[]},
        'stage_timings_ns':{'scene_render':1},'execution':{'worker_pid':1,'worker_process':True}}}


def threads(monkeypatch, submitted, admitted=None):
    class Executor(ThreadPoolExecutor):
        def __init__(self, max_workers, **kwargs):
            super().__init__(max_workers=max_workers)
        def submit(self, fn, *args):
            submitted.append(args[2])
            if admitted is not None and len(submitted)==2:admitted.set()
            return super().submit(fn,*args)
    monkeypatch.setattr(generator,'ProcessPoolExecutor',Executor)


def test_refills_after_commit_without_waiting_for_later_slot(monkeypatch,tmp_path):
    submitted=[];committed=[];release=threading.Event();outstanding=[]
    threads(monkeypatch,submitted)
    original=RunStore.commit_sample
    def commit(self, record,*args,**kwargs):
        outstanding.append(len(submitted)-len(committed))
        value=original(self,record,*args,**kwargs);committed.append(record['slot']);return value
    monkeypatch.setattr(RunStore,'commit_sample',commit)
    def produce(_r,_c,slot,attempt,_pid):
        if slot==1:
            assert release.wait(5),'batch barrier prevented slot2 admission'
        if slot==2:release.set()
        return result(slot,attempt)
    monkeypatch.setattr(generator,'_produce_slot',produce)
    summary=generate_pool(fixture(),tmp_path/'pool',GenerationOptions(display='quiet',workers=2))
    assert summary['status']=='complete',summary['fatal_error']
    assert committed==list(range(6))
    assert max(outstanding)<=2


@pytest.mark.parametrize('action',['stop','pause'])
def test_control_stops_admission_and_drains_then_resumes(monkeypatch,tmp_path,action):
    submitted=[];entered=threading.Event();release=threading.Event();admitted=threading.Event()
    threads(monkeypatch,submitted,admitted)
    def produce(_r,_c,slot,attempt,_pid):
        if slot==0:
            entered.set();assert release.wait(5)
        return result(slot,attempt)
    monkeypatch.setattr(generator,'_produce_slot',produce)
    pool=tmp_path/'pool';summary={}
    thread=threading.Thread(target=lambda:summary.update(generate_pool(fixture(),pool,GenerationOptions(display='quiet',workers=2))))
    thread.start();assert entered.wait(10) and admitted.wait(10)
    request_run_action(pool,action);release.set()
    if action=='pause':
        deadline=time.monotonic()+8
        while time.monotonic()<deadline and run_status(pool)['actual_state']!='paused':time.sleep(.02)
        assert run_status(pool)['actual_state']=='paused'
        assert submitted==[0,1]
        request_run_action(pool,'continue')
    thread.join(15);assert not thread.is_alive()
    if action=='stop':
        assert summary['status']=='interrupted'
        assert summary['accepted_samples']==2
        assert submitted==[0,1]
        summary=generate_pool(fixture(),pool,GenerationOptions(display='quiet',workers=2,resume=True))
    assert summary['status']=='complete'
    rows=[json.loads(v) for v in (pool/'samples.jsonl').read_text().splitlines()]
    assert [v['slot'] for v in rows]==list(range(6))


@pytest.mark.parametrize('failure',[0,1])
def test_future_exception_cannot_commit_later_slots(monkeypatch,tmp_path,failure):
    submitted=[];threads(monkeypatch,submitted)
    def produce(_r,_c,slot,attempt,_pid):
        if slot==failure:raise RuntimeError('deliberate worker failure')
        return result(slot,attempt)
    monkeypatch.setattr(generator,'_produce_slot',produce)
    pool=tmp_path/'pool';summary=generate_pool(fixture(),pool,GenerationOptions(display='quiet',workers=2))
    assert summary['status']=='failed'
    rows=[json.loads(v) for v in (pool/'samples.jsonl').read_text().splitlines()]
    assert [v['slot'] for v in rows]==list(range(failure))


def test_interrupt_reaps_admitted_work_without_duplicate_commits(monkeypatch,tmp_path):
    submitted=[];threads(monkeypatch,submitted)
    original=generator.wait;raised=False
    release=threading.Event();both_started=threading.Event();lock=threading.Lock();started=0
    def interrupt(*args,**kwargs):
        nonlocal raised
        if not raised:
            assert both_started.wait(5)
            raised=True;release.set();raise KeyboardInterrupt
        return original(*args,**kwargs)
    def produce(_r,_c,slot,attempt,_pid):
        nonlocal started
        with lock:
            started+=1
            if started==2:both_started.set()
        assert release.wait(5)
        return result(slot,attempt)
    monkeypatch.setattr(generator,'wait',interrupt)
    monkeypatch.setattr(generator,'_produce_slot',produce)
    pool=tmp_path/'pool';summary=generate_pool(fixture(),pool,GenerationOptions(display='quiet',workers=2))
    assert raised and summary['status']=='interrupted'
    rows=[json.loads(v) for v in (pool/'samples.jsonl').read_text().splitlines()]
    assert [v['slot'] for v in rows]==[0,1]
    resumed=generate_pool(fixture(),pool,GenerationOptions(display='quiet',workers=2,resume=True))
    assert resumed['status']=='complete'

@pytest.mark.parametrize('family',['landing','manometro','landing-pad'])
def test_multislot_process_images_masks_and_records_equal_serial(tmp_path,family):
    resolved=load_profile(f'examples/configs/{family}_minimal.yaml',overrides={
        'run.num_images':4,'output.image_size':[128,128],
        'execution.native_threads':1,'execution.max_in_flight':3,'report.qa_samples':0})
    pools=[tmp_path/'serial',tmp_path/'process']
    for workers,pool in zip((1,2),pools):
        summary=generate_pool(resolved,pool,GenerationOptions(display='quiet',workers=workers))
        assert summary['status']=='complete',summary['fatal_error']
    rows=[[json.loads(line) for line in (pool/'samples.jsonl').read_text().splitlines()] for pool in pools]
    for left,right in zip(*rows):
        for field in ('slot','candidate_attempt','geometry_signature','annotations','rejected_instances','scene_to_output'):
            assert left[field]==right[field]
        assert (pools[0]/left['image_path']).read_bytes()==(pools[1]/right['image_path']).read_bytes()
        assert left['mask_evidence']['sha256']==right['mask_evidence']['sha256']
