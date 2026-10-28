"""Data-driven optional Blender execution selection; no Blender import on the host."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, allow_inf_nan=False)


class Settings(Strict):
    device: Literal['CPU', 'GPU']
    denoiser: Literal['compositor-oidn', 'compositor-fast', 'native-gpu-oidn', 'native-cpu-oidn', 'none']
    workers: int = Field(ge=1, le=8)
    threads: int | Literal['available']
    thread_cap: int = Field(ge=1, le=64)
    denoiser_prefilter: Literal['ACCURATE', 'FAST', 'NONE']
    denoiser_quality: Literal['HIGH', 'BALANCED', 'FAST']
    denoiser_input_passes: Literal['RGB', 'RGB_ALBEDO', 'RGB_ALBEDO_NORMAL']
    max_bounces: int = Field(ge=0, le=64)
    diffuse_bounces: int = Field(ge=0, le=64)
    glossy_bounces: int = Field(ge=0, le=64)
    transparent_bounces: int = Field(ge=0, le=64)
    renderer_initialization: Literal['stock', 'guarded']

    @model_validator(mode='after')
    def validate_settings(self):
        if isinstance(self.threads, bool) or isinstance(self.threads, int) and not 1 <= self.threads <= 64:
            raise ValueError('threads must be available or1–64')
        if self.denoiser=='compositor-fast' and self.denoiser_prefilter!='FAST':
            raise ValueError('compositor-fast requires FAST prefilter')
        if self.denoiser == 'native-gpu-oidn' and self.device != 'GPU':
            raise ValueError('GPU denoising requires GPU execution')
        return self


class Match(Strict):
    environment: Literal['colab'] | None = None
    gpu_name_pattern: str | None = Field(default=None, max_length=128)
    oidn_gpu: bool | None = None
    min_cpu_count: int | None = Field(default=None, ge=1)
    max_cpu_count: int | None = Field(default=None, ge=1)
    min_gpu_memory_mib: int | None = Field(default=None, ge=1)
    max_pixels: int | None = Field(default=None, ge=1)

    @model_validator(mode='after')
    def valid_pattern(self):
        if self.min_cpu_count is not None and self.max_cpu_count is not None and self.min_cpu_count>self.max_cpu_count:
            raise ValueError('CPU match range is empty')
        if self.gpu_name_pattern is not None:
            try: re.compile(self.gpu_name_pattern)
            except re.error as error: raise ValueError('Invalid GPU name pattern') from error
        return self


class Profile(Strict):
    id: str = Field(pattern=r'^[a-z0-9][a-z0-9-]{0,63}$')
    automatic: bool
    match: Match
    settings: Settings
    evidence: str


class Guards(Strict):
    min_available_gib: float = Field(gt=0)
    rss_limit_gib: float = Field(gt=0)
    max_swap_out_mib: float = Field(ge=0)
    probe_timeout_seconds: float = Field(gt=0, le=1800)
    min_gpu_free_mib: float | None = Field(default=None, ge=0)


class Catalog(Strict):
    schema_version: Literal[1]
    backend_order: tuple[Literal['OPTIX', 'CUDA', 'HIP', 'ONEAPI', 'METAL'], ...]
    guards: Guards
    profiles: tuple[Profile, ...]

    @model_validator(mode='after')
    def unique_profiles(self):
        ids=[p.id for p in self.profiles]
        if not ids or len(ids)!=len(set(ids)): raise ValueError('Unique nonempty execution profiles required')
        if len(set(self.backend_order))!=len(self.backend_order): raise ValueError('Duplicate backend priority')
        return self


def catalog_path():
    return Path(__file__).resolve().parents[2]/'experiments/blenderproc/execution/profiles.json'


def load_catalog(path=None):
    def pairs(items):
        result={}
        for k,v in items:
            if k in result: raise ValueError('Duplicate execution key: '+k)
            result[k]=v
        return result
    return Catalog.model_validate(json.loads(Path(path or catalog_path()).read_text(), object_pairs_hook=pairs))


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def resolve_execution(catalog, hardware, resolution, *, profile='auto', threads=None, workers=None):
    """Resolve one immutable policy from measured capabilities and saved ordered rules."""
    catalog_value=catalog.model_dump(mode="json") if isinstance(catalog,Catalog) else catalog
    catalog=Catalog.model_validate(catalog_value)
    cpu_count=hardware['cpu_count']
    if not isinstance(cpu_count,int) or isinstance(cpu_count,bool) or cpu_count<1:
        raise ValueError('Invalid hardware CPU count')
    candidates=[]
    for backend in catalog.backend_order:
        candidates.extend(d for d in hardware['devices'] if d['backend']==backend)
    decisions=[]
    for p in catalog.profiles:
        if profile!='auto' and p.id!=profile or profile=='auto' and not p.automatic: continue
        match=p.match
        for device in candidates if p.settings.device=='GPU' else [None]:
            failures=[]
            if match.environment and hardware.get('environment')!=match.environment: failures.append('environment')
            if match.min_cpu_count and cpu_count<match.min_cpu_count: failures.append('CPU count')
            if match.max_cpu_count and cpu_count>match.max_cpu_count: failures.append('CPU count')
            if match.max_pixels and resolution[0]*resolution[1]>match.max_pixels: failures.append('resolution')
            if device is None and (match.gpu_name_pattern or match.min_gpu_memory_mib or match.oidn_gpu):failures.append('GPU criteria require GPU execution')
            if device is not None:
                if match.gpu_name_pattern and not re.search(match.gpu_name_pattern,device['name']): failures.append('GPU name')
                if (match.oidn_gpu is not None and device.get('oidn_gpu')!=match.oidn_gpu) or (p.settings.denoiser=='native-gpu-oidn' and not device.get('oidn_gpu')): failures.append('GPU OIDN capability')
                if match.min_gpu_memory_mib and (device.get('memory_mib') or 0)<match.min_gpu_memory_mib: failures.append('VRAM')
            if failures:
                decisions.append({'profile':p.id,'device':device['name'] if device else 'CPU','unmatched':failures});continue
            settings=p.settings.model_dump(mode='json')
            settings['threads']=threads if threads is not None else min(cpu_count,settings['thread_cap']) if settings['threads']=='available' else settings['threads']
            settings['workers']=workers if workers is not None else settings['workers']
            Settings.model_validate(settings)
            selection={'profile':p.id,'settings':settings,'device':device,'hardware':hardware,
                       'catalog_sha256':fingerprint(catalog_value),'decisions':decisions,
                       'overrides':{k:v for k,v in {'threads':threads,'workers':workers}.items() if v is not None},'evidence':p.evidence}
            selection['identity']=fingerprint(selection)
            return selection
        if p.settings.device=='GPU' and not candidates: decisions.append({'profile':p.id,'unmatched':['no GPU available']})
    raise ValueError('No compatible execution profile: '+profile)


def load_execution(root, study):
    value=json.loads((Path(root)/'execution.json').read_text())
    selection=value['selection']
    if value['study_identity']!=study['identity'] or selection['identity']!=fingerprint({k:v for k,v in selection.items() if k!='identity'}):
        raise ValueError('Execution record changed')
    expected=resolve_execution(study['execution_catalog'],selection['hardware'],study['config']['resolution'],profile=study['config'].get('execution_profile','auto'),threads=study['config'].get('threads'),workers=study['config'].get('workers'))
    if expected!=selection:raise ValueError('Execution profile differs from prepared policy')
    return value
