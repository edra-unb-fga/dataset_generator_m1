"""Unlabeled procedural scene-plane geometry; no imported assets or physical shadows."""
from dataclasses import dataclass

import cv2
import numpy as np

from .imaging import composite_linear_srgb


@dataclass(frozen=True)
class SceneOccluder:
    kind: str
    points: tuple[tuple[float, float], ...]
    color: tuple[int, int, int]
    opacity: float

    def geometry(self):
        return {'kind': self.kind, 'points': self.points, 'opacity': self.opacity}

    def evidence(self):
        return {**self.geometry(), 'color': self.color}


def sample_occluders(config, camera_rect, rng):
    if config is None or rng.random() >= config.probability:
        return ()
    x, y, w, h = camera_rect
    layers = []
    for _ in range(int(rng.integers(config.count[0], config.count[1]+1))):
        kind = str(rng.choice(['blade','debris'])) if config.kind == 'mixed' else config.kind
        cx, cy = x+float(rng.uniform(-.1,1.1))*w, y+float(rng.uniform(-.1,1.1))*h
        length, width = float(rng.uniform(*config.length_fraction))*w, float(rng.uniform(*config.width_fraction))*w
        angle = float(rng.uniform(0,2*np.pi))
        along = np.array([np.cos(angle),np.sin(angle)])
        across = np.array([-along[1],along[0]])
        if kind == 'blade':
            points = np.array([np.array([cx,cy])-across*width/2,
                               np.array([cx,cy])+across*width/2,
                               np.array([cx,cy])+along*length+across*width*.3])
            base = np.array([72,91,40])
        else:
            phases = np.arange(7)*2*np.pi/7
            points = np.array([cx,cy])+np.cos(phases)[:,None]*along*length/2+np.sin(phases)[:,None]*across*width
            points = np.array([cx,cy])+(points-np.array([cx,cy]))*rng.uniform(.65,1.,(7,1))
            base = np.array([111,87,55])
        color = tuple(int(v) for v in np.clip(base+rng.integers(-15,16,3),0,255))
        layers.append(SceneOccluder(kind,tuple(tuple(float(v) for v in p) for p in points), color,
                                    float(rng.uniform(*config.opacity))))
    return tuple(layers)


def composite_occluders(rgb, layers, scene_to_output, *, compositing="legacy"):
    """Stream one projected layer and cumulative external coverage in output coordinates."""
    if not layers:
        return rgb, None
    h, w = rgb.shape[:2]
    total = np.zeros((h,w),np.float32)
    result = rgb
    for layer in layers:
        points = cv2.perspectiveTransform(np.array([layer.points],np.float64),scene_to_output)[0]
        # A sampled quad cannot normally cross infinity; fail safely before integer overflow.
        if not np.isfinite(points).all() or np.max(np.abs(points)) > 1e6:
            raise ValueError('Occluder projection lies outside supported raster range')
        mask = np.zeros((h,w),np.uint8)
        cv2.fillPoly(mask,[np.rint(points*256).astype(np.int32)],255,lineType=cv2.LINE_AA,shift=8)
        alpha = mask.astype(np.float32)/255.*layer.opacity
        if compositing == "linear-srgb":
            result = composite_linear_srgb(result, np.array(layer.color, np.uint8), alpha)
        else:
            result = np.rint(np.clip(result.astype(np.float32)*(1-alpha[:,:,None])+np.array(layer.color,np.float32)*alpha[:,:,None],0,255)).astype(np.uint8)
        total = alpha+total*(1-alpha)
    return result,np.rint(total*255).astype(np.uint8)
