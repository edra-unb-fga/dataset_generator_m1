"""PROTOTYPE: fixed-plane normal/roughness lighting, deliberately separate from production."""
import numpy as np


def shade(color, normal, roughness, *, azimuth=45.0, use_roughness=True):
    linear = np.where(color <= .04045, color / 12.92, ((color + .055) / 1.055) ** 2.4)
    n = normal * 2 - 1
    n = n / np.maximum(np.linalg.norm(n, axis=2, keepdims=True), 1e-6)
    angle = np.deg2rad(azimuth)
    light = np.array([np.cos(angle) * .6, np.sin(angle) * .6, .8], dtype=np.float32)
    diffuse = np.clip(n @ light, 0, 1)
    result = linear * (.35 + .65 * diffuse[..., None])
    if use_roughness:
        half = light + np.array([0, 0, 1], dtype=np.float32)
        half /= np.linalg.norm(half)
        exponent = np.clip(2 / np.maximum(roughness, .12) ** 2 - 2, 2, 128)
        highlight = np.clip(n @ half, 0, 1) ** exponent
        result += (.07 * (1 - roughness) * highlight)[..., None]
    result = np.clip(result, 0, 1)
    return np.where(result <= .0031308, result * 12.92, 1.055 * result ** (1 / 2.4) - .055)
