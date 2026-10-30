"""Bounded opt-in physical ground mapping and material study contracts."""
from __future__ import annotations
import hashlib
from typing import Literal
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid', frozen=True, allow_inf_nan=False)

class GroundMapping(Strict):
    ground_spans: tuple[float,float]=(.5,1.5)
    extent_bounds_m: tuple[float,float]=(40,500)
    tile_bounds_m: tuple[float,float]=(.1,500)
    footprint_margin: float=Field(default=1.1,ge=1,le=3)
    @model_validator(mode='after')
    def bounds(self):
        for values,lo,hi in ((self.ground_spans,.1,10),(self.extent_bounds_m,1,1000),(self.tile_bounds_m,.01,1000)):
            if not lo<=values[0]<=values[1]<=hi: raise ValueError('Invalid ground mapping bounds')
        return self

class GroundMaterial(Strict):
    mode: Literal['color-only','full','coherent-blend','rgb-blend-stress','donor-mismatch-stress']
    primary_index: int | None=Field(default=None,ge=0,le=5)
    donor_index: int | None=Field(default=None,ge=0,le=5)
    blend_scale: float=Field(default=2,ge=.1,le=20)
    blend_amount: float=Field(default=.5,ge=0,le=1)
    blend_seed: int=Field(default=0,ge=0,le=1000000)
    @model_validator(mode='after')
    def donor(self):
        needs=self.mode in ('coherent-blend','rgb-blend-stress','donor-mismatch-stress')
        if needs != (self.donor_index is not None): raise ValueError('Donor index is required exactly for blend and mismatch modes')
        if self.primary_index is not None and self.primary_index == self.donor_index:
            raise ValueError('Primary and donor ground indices must differ')
        return self

def sample_spans(seed, sequence_index, bounds):
    key=hashlib.sha256(f'ground-mapping-v1:{seed}:{sequence_index}'.encode()).digest()
    return float(np.random.default_rng(int.from_bytes(key[:8],'big')).uniform(*bounds))


def required_maps(mode):
    """Map roles consumed from the selected primary and donor for each mode."""
    return {
        'color-only': ({'color'}, set()),
        'full': ({'color','roughness','normal'}, set()),
        'coherent-blend': ({'color','roughness','normal'}, {'color','roughness','normal'}),
        'rgb-blend-stress': ({'color','roughness','normal'}, {'color'}),
        'donor-mismatch-stress': ({'color'}, {'roughness','normal'}),
    }[mode]
