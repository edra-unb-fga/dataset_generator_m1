"""Bounded qualitative planar appearance, without a physical material/lighting model."""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .models import SurfaceWearConfig


def validate_surface_wear(params: dict, stage: str) -> None:
    if not stage.startswith(('foreground', 'appearance.foreground')):
        raise ValueError('SurfaceWear is foreground-only')
    SurfaceWearConfig.model_validate(params)


@dataclass(frozen=True)
class WearFields:
    """Registered, strength-weighted local fields; no source image or alpha is modified."""

    dirt: np.ndarray
    scratches: np.ndarray
    evidence: dict


def generate_wear_fields(shape: tuple[int, int], config: SurfaceWearConfig,
                         rng: np.random.Generator) -> WearFields:
    """Rasterize the historical normalized lattice without changing its random draws."""
    h, w = shape
    if h < 1 or w < 1:
        raise ValueError('Wear field dimensions must be positive')
    # Fixed normalized lattice means doubling source resolution does not resample the marks.
    work_w, work_h = 512, min(2048, max(1, round(512*h/w)))
    dirt = np.zeros((work_h, work_w), np.float32)
    scratches = np.zeros_like(dirt)
    marks = []
    for _ in range(config.marks):
        x, y = rng.uniform(0, 1, 2)
        radius = float(rng.uniform(.015, .09))
        cv2.ellipse(dirt, (round(x*work_w), round(y*work_h)),
                    (max(1, round(radius*work_w)), max(1, round(radius*work_w*.55))),
                    float(rng.uniform(0, 180)), 0, 360, float(rng.uniform(.2, 1)), -1)
        start = (round(x*work_w), round(y*work_h))
        end = (round((x+float(rng.uniform(-.12, .12)))*work_w), round((y+float(rng.uniform(-.12, .12)))*work_h))
        cv2.line(scratches, start, end, 1., max(1, round(config.scratch_width*work_w)))
        marks.append([round(float(x), 6), round(float(y), 6), round(radius, 6)])
    dirt = cv2.GaussianBlur(dirt, (0, 0), 2.)
    dirt = cv2.resize(dirt, (w, h), interpolation=cv2.INTER_LINEAR)[:, :, None]*config.dirt
    scratches = cv2.resize(scratches, (w, h), interpolation=cv2.INTER_LINEAR)[:, :, None]*config.scratches
    return WearFields(dirt, scratches, {'config': config.model_dump(mode='json'), 'local_marks': marks})


def apply_wear_fields(rgb: np.ndarray, config: SurfaceWearConfig, fields: WearFields) -> np.ndarray:
    """Historical encoded-RGB appearance path, shared by 2D and 3D albedo preparation."""
    dirt, scratches = fields.dirt, fields.scratches
    if dirt.shape != (*rgb.shape[:2], 1) or scratches.shape != dirt.shape:
        raise ValueError('Wear fields and image must have identical dimensions')
    result = rgb.astype(np.float32)
    result = result*(1-config.fade) + np.array([174, 170, 151], np.float32)*config.fade
    result = result*(1-dirt) + np.array([92, 78, 51], np.float32)*dirt
    result = result*(1-scratches) + np.array([209, 204, 183], np.float32)*scratches
    return np.rint(np.clip(result, 0, 255)).astype(np.uint8)


def apply_surface_wear(rgb: np.ndarray, params: dict, rng: np.random.Generator):
    """Apply normalized local RGB wear, preserving source alpha upstream."""
    config = SurfaceWearConfig.model_validate(params)
    fields = generate_wear_fields(rgb.shape[:2], config, rng)
    return apply_wear_fields(rgb, config, fields), fields.evidence


def srgb_to_linear(rgb):
    value = np.asarray(rgb, np.float32)/255.
    return np.where(value <= .04045, value/12.92, ((value+.055)/1.055)**2.4)


def linear_to_srgb(value):
    value = np.clip(value, 0, 1)
    result = np.where(value <= .0031308, value*12.92, 1.055*value**(1/2.4)-.055)
    return np.rint(np.clip(result*255, 0, 255)).astype(np.uint8)


def sample_lighting(config, rng):
    if config is None:
        return None
    applied = bool(rng.random() < config.probability)
    evidence = {'applied': applied, 'source_assumption': config.source_assumption,
                'model': 'scene-linear-irradiance-v1'}
    if applied:
        angle = float(rng.uniform(0, 2*np.pi))
        strength = float(rng.uniform(*config.gradient))
        evidence.update(gain=float(rng.uniform(*config.gain)),
                        gradient=[strength*float(np.cos(angle)), strength*float(np.sin(angle))],
                        tint=rng.uniform(-config.tint, config.tint, 3).tolist())
    return evidence


def sample_environmental_shade(config, rng):
    """Sample a smooth, qualitative canopy/shade patch on its own random stream."""
    if config is None or config.probability == 0 or config.strength[1] == 0:
        return None
    evidence = {'applied': bool(rng.random() < config.probability),
                'model': 'scene-soft-ellipse-shade-v1',
                'physical_claim': 'qualitative-environmental-shade'}
    if evidence['applied']:
        evidence.update(center=rng.uniform(-.15, 1.15, 2).tolist(),
                        radius=rng.uniform(*config.radius_fraction, 2).tolist(),
                        angle=float(rng.uniform(0, 2*np.pi)),
                        strength=float(rng.uniform(*config.strength)))
    return evidence


def apply_scene_lighting(rgb, scene_to_output, canvas_size, evidence, shade=None):
    lighting_active = evidence is not None and evidence['applied']
    shade_active = shade is not None and shade['applied'] and shade.get('strength', 0) > 0
    if not lighting_active and not shade_active:
        return rgb
    inverse = np.linalg.inv(scene_to_output)
    h, w = rgb.shape[:2]
    result = np.empty_like(rgb)
    # Tile rows: workspace scales with output width, not the oversize scene canvas.
    for top in range(0, h, 128):
        ys, xs = np.mgrid[top:min(top+128, h), :w].astype(np.float32)
        denominator = inverse[2, 0]*xs+inverse[2, 1]*ys+inverse[2, 2]
        if np.any(np.abs(denominator) < 1e-9):
            raise ValueError('Scene illumination inverse homography crosses infinity')
        sx = (inverse[0, 0]*xs+inverse[0, 1]*ys+inverse[0, 2])/denominator/canvas_size[0]-.5
        sy = (inverse[1, 0]*xs+inverse[1, 1]*ys+inverse[1, 2])/denominator/canvas_size[1]-.5
        if lighting_active:
            field = np.clip(evidence['gain']+evidence['gradient'][0]*sx+evidence['gradient'][1]*sy, .1, 2.)
            factor = field[:, :, None]*(1+np.array(evidence['tint'], np.float32))
        else:
            factor = np.ones((*sx.shape, 1), np.float32)
        if shade_active:
            # One analytic elliptical Gaussian has no raster workspace tied to canvas size.
            dx, dy = sx+.5-shade['center'][0], sy+.5-shade['center'][1]
            cosine, sine = np.cos(shade['angle']), np.sin(shade['angle'])
            u = (cosine*dx+sine*dy)/shade['radius'][0]
            v = (-sine*dx+cosine*dy)/shade['radius'][1]
            attenuation = 1-shade['strength']*np.exp(-.5*(u*u+v*v))
            factor = factor*attenuation[:, :, None]
        result[top:top+len(ys)] = linear_to_srgb(srgb_to_linear(rgb[top:top+len(ys)])*factor)
    return result
