"""Versioned, bounded procedural choices for the optional physical harness."""
from __future__ import annotations
import hashlib
from pathlib import Path
from typing import Literal
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, allow_inf_nan=False)

class WeightedLight(Strict):
    value: Literal['sun', 'environment', 'overcast', 'shade', 'night-single', 'night-mixed']
    weight: float = Field(gt=0, le=1000)

class WeightedType(Strict):
    value: Literal['AREA', 'POINT', 'SPOT']
    weight: float = Field(gt=0, le=1000)

class WeightedShape(Strict):
    value: Literal['box', 'cylinder', 'sphere', 'overhead-slab', 'overhead-slats']
    weight: float = Field(gt=0, le=1000)

class WeightedGround(Strict):
    index: int = Field(ge=0, le=5)
    weight: float = Field(gt=0, le=1000)

class Preset(Strict):
    schema_version: Literal[1] = 1
    id: str = Field(pattern=r'^[a-z0-9][a-z0-9-]{0,63}$')
    environment: Literal['open', 'outdoor', 'indoor']
    lighting: tuple[WeightedLight, ...] = Field(min_length=1, max_length=6)
    ground_weights: tuple[WeightedGround, ...] | None = Field(default=None, min_length=1, max_length=6)
    wall_texture: Literal['none', 'base'] = 'none'
    wall_colors: tuple[tuple[float, float, float], ...] = Field(min_length=1, max_length=16)
    ceiling_colors: tuple[tuple[float, float, float], ...] = Field(min_length=1, max_length=16)
    wall_heights_m: tuple[float, float]
    wall_roughness: tuple[float, float]
    ceiling_roughness: tuple[float, float]
    roughness: tuple[float, float]
    environment_strength: tuple[float, float]
    sun_azimuth_degrees: tuple[float, float]
    sun_elevation_degrees: tuple[float, float]
    sun_angular_size: tuple[float, float]
    sun_power: tuple[float, float]
    sun_colors: tuple[tuple[float, float, float], ...] = Field(min_length=1, max_length=16)
    lamp_count: tuple[int, int]
    lamp_types: tuple[WeightedType, ...] = Field(min_length=1, max_length=3)
    lamp_x_m: tuple[float, float]
    lamp_y_m: tuple[float, float]
    lamp_z_m: tuple[float, float]
    lamp_size_m: tuple[float, float]
    lamp_colors: tuple[tuple[float, float, float], ...] = Field(min_length=1, max_length=16)
    lamp_power_w: tuple[float, float]
    spot_size_rad: tuple[float, float]
    spot_blend: tuple[float, float]
    caster_count: tuple[int, int]
    caster_shapes: tuple[WeightedShape, ...] = Field(min_length=1, max_length=5)
    caster_distance_m: tuple[float, float]
    caster_height_m: tuple[float, float]
    caster_width_m: tuple[float, float]
    overhead_height_m: tuple[float, float]
    overhead_width_m: tuple[float, float]
    overhead_thickness_m: tuple[float, float]
    caster_visible_camera: bool = False

    @model_validator(mode='after')
    def bounds(self):
        ranges=((self.wall_heights_m,.2,20),(self.wall_roughness,0,1),(self.ceiling_roughness,0,1),
                (self.roughness,0,1),(self.environment_strength,0,10), (self.sun_azimuth_degrees,-180,180),
                (self.sun_elevation_degrees,5,90),(self.sun_angular_size,.001,.5),(self.sun_power,.01,10),
                (self.lamp_count,0,8),(self.lamp_x_m,-20,20),(self.lamp_y_m,-20,20),(self.lamp_z_m,.2,20),
                (self.lamp_size_m,.01,10),(self.lamp_power_w,1,10000),(self.spot_size_rad,.01,3.141592653589793),(self.spot_blend,0,1),(self.caster_count,0,12),
                (self.caster_distance_m,2,20),(self.caster_height_m,.2,10),(self.caster_width_m,.02,5),
                (self.overhead_height_m,1,20),(self.overhead_width_m,.2,20),(self.overhead_thickness_m,.02,2))
        for values,low,high in ranges:
            if not low <= values[0] <= values[1] <= high: raise ValueError('Invalid preset range')
        for colors in (self.wall_colors,self.ceiling_colors,self.sun_colors,self.lamp_colors):
            if any(not 0 <= x <= 1 for color in colors for x in color): raise ValueError('Invalid preset color')
        for options in (self.lighting,self.lamp_types,self.caster_shapes,self.ground_weights or ()):
            values=[getattr(option,'value',None) if not isinstance(option,WeightedGround) else option.index for option in options]
            if len(values)!=len(set(values)): raise ValueError('Duplicate weighted option')
        if self.overhead_height_m[0] <= self.overhead_thickness_m[1]/2:
            raise ValueError('Overhead geometry must clear the ground')
        if self.environment == 'indoor' and any(x.value == 'sun' for x in self.lighting):
            raise ValueError('Indoor preset cannot select sun')
        return self

def catalog():
    return Path(__file__).resolve().parents[2] / 'experiments/blenderproc/scene-presets'

def load_preset(name=None, *, path=None):
    if (name is None)==(path is None): raise ValueError('Choose exactly one preset ID or file')
    if path is None:
        if not name or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in name): raise ValueError('Invalid preset ID')
        path=catalog() / (name+'.json')
    value=Preset.model_validate_json(Path(path).read_text())
    if name is not None and value.id != name: raise ValueError('Preset ID does not match filename')
    return value

def stream(seed, scene_index, name):
    value=hashlib.sha256(f'procedural-v1:{seed}:{scene_index}:{name}'.encode()).digest()
    return np.random.default_rng(int.from_bytes(value[:8], 'big'))

def sample(preset, seed, scene_index, treatment, settings, ground_count, environment_count):
    """Resolve independent choices into a complete, reproducible job record."""
    if ground_count<1 or environment_count<1: raise ValueError('At least one ground and environment is required')
    if preset.ground_weights and any(item.index>=ground_count for item in preset.ground_weights):
        raise ValueError('Preset ground index is outside the supplied ground catalog')
    def rng(name): return stream(seed,scene_index,name)
    def choice(name,values): return values[int(rng(name).integers(len(values)))]
    def weighted(name,values):
        weights=np.array([v.weight for v in values],dtype=float); weights/=weights.sum()
        return values[int(rng(name).choice(len(values),p=weights))]
    def uniform(name,bounds): return float(rng(name).uniform(*bounds))
    t=dict(treatment)
    selected_lighting=weighted('lighting',preset.lighting).value
    t.update(lighting=selected_lighting,roughness=uniform('roughness',preset.roughness),
             environment_strength=uniform('environment-strength',preset.environment_strength),
             environment_index=int(rng('environment').integers(environment_count)),shadows=True,
             casters={'count':0,'seed':0,'distance_m':6,'height_m':3,'width_m':.12},lamps=[])
    if selected_lighting=='sun':
        az=np.radians(uniform('sun-azimuth',preset.sun_azimuth_degrees)); el=np.radians(uniform('sun-elevation',preset.sun_elevation_degrees))
        t['lighting']='environment'
        t['lamps'].append({'kind':'SUN','location':[float(np.cos(az)*np.cos(el)*10),float(np.sin(az)*np.cos(el)*10),float(np.sin(el)*10)],
            'target':[0,0,0],'color':choice('sun-color',preset.sun_colors),'power_w':uniform('sun-power',preset.sun_power),
            'size_m':.7,'angular_size_rad':uniform('sun-angular-size',preset.sun_angular_size)})
    if preset.environment=='indoor' or selected_lighting.startswith('night'):
        count=int(rng('lamp-count').integers(preset.lamp_count[0],preset.lamp_count[1]+1))
        for i in range(count):
            name=f'lamp-{i}'
            t['lamps'].append({'kind':weighted(name+'-type',preset.lamp_types).value,
                'location':[uniform(name+'-x',preset.lamp_x_m),uniform(name+'-y',preset.lamp_y_m),uniform(name+'-z',preset.lamp_z_m)],
                'target':[0,0,0],'color':choice(name+'-color',preset.lamp_colors),
                'power_w':uniform(name+'-power',preset.lamp_power_w),'size_m':uniform(name+'-size',preset.lamp_size_m),
                'spot_size_rad':uniform(name+'-spot-size',preset.spot_size_rad),'spot_blend':uniform(name+'-spot-blend',preset.spot_blend)})
    s=dict(settings)
    s.update(wall_color=choice('wall-color',preset.wall_colors),ceiling_color=choice('ceiling-color',preset.ceiling_colors),
        wall_roughness=uniform('wall-roughness',preset.wall_roughness),ceiling_roughness=uniform('ceiling-roughness',preset.ceiling_roughness),
        outdoor_wall_height_m=uniform('wall-height',preset.wall_heights_m))
    if preset.wall_texture == 'none': s['wall_ground_index']=None
    count=int(rng('caster-count').integers(preset.caster_count[0],preset.caster_count[1]+1)); casters=[]
    for i in range(count):
        name=f'caster-{i}'; shape=weighted(name+'-shape',preset.caster_shapes).value
        angle=uniform(name+'-angle',(0,2*np.pi)); distance=uniform(name+'-distance',preset.caster_distance_m)
        if shape.startswith('overhead'):
            height=uniform(name+'-height',preset.overhead_height_m); width=uniform(name+'-width',preset.overhead_width_m)
            thickness=uniform(name+'-thickness',preset.overhead_thickness_m)
            location=[float(np.cos(angle)*distance/2),float(np.sin(angle)*distance/2),height]; scale=[width,width,thickness]
        else:
            height=uniform(name+'-height',preset.caster_height_m); width=uniform(name+'-width',preset.caster_width_m)
            location=[float(np.cos(angle)*distance),float(np.sin(angle)*distance),height/2]; scale=[width,width,height]
        casters.append({'shape':shape,'location':location,'scale':scale,'visible_camera':preset.caster_visible_camera})
    ground=weighted('ground',preset.ground_weights).index if preset.ground_weights else int(rng('ground').integers(ground_count))
    return {'preset':preset.model_dump(mode='json'),'treatment':t,'environment_geometry':preset.environment,
            'environment_geometry_settings':s,'selected_lighting':selected_lighting,'ground_index':ground,'casters':casters}
