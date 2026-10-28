#!/usr/bin/env python3
"""Small paired appearance study; reports image/mask evidence, never throughput."""
from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import html
import json
from pathlib import Path

import numpy as np
from PIL import Image

from dataset_generator_m1.assets import build_asset_catalog
from dataset_generator_m1.backgrounds import BackgroundSynthesizer
from dataset_generator_m1.config import load_profile
from dataset_generator_m1.generator import _annotation_record
from dataset_generator_m1.models import AppearanceConfig, EnvironmentalShadeConfig, SceneLightingConfig, SceneOcclusionConfig
from dataset_generator_m1.scene import ScenePlanner, SceneRenderer
from dataset_generator_m1.scene_occlusion import SceneOccluder


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--matrix', type=Path, default=Path('experiments/planar/linear-compositing-study.json'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    matrix = json.loads(args.matrix.read_text())
    if set(matrix) != {'schema_version', 'image_size', 'samples_per_subject', 'background_seed', 'subjects', 'occlusion', 'treatments'} or matrix['schema_version'] != 1:
        raise ValueError('Unexpected or invalid study matrix')
    if matrix['treatments'] != ['legacy', 'linear', 'linear-shade'] or not 1 <= matrix['samples_per_subject'] <= 8:
        raise ValueError('Unsupported study treatments or sample count')
    if not matrix['subjects'] or any(v not in {'landing-pad', 'landing', 'manometro', 'generic-rgba'} for v in matrix['subjects']):
        raise ValueError('Unsupported subject')
    if matrix['occlusion'] != [False, True] or len(matrix['image_size']) != 2 or any(not 64 <= int(v) <= 1280 for v in matrix['image_size']):
        raise ValueError('Unsupported occlusion cases or image dimensions')
    root = args.output
    root.mkdir(parents=True, exist_ok=False)
    generic = np.zeros((128, 128, 4), np.uint8)
    yy, xx = np.indices(generic.shape[:2])
    generic[:, :, :3] = [230, 55, 130]
    generic[:, :, 3] = np.clip((55-np.sqrt((xx-63.5)**2 + (yy-63.5)**2))*20, 0, 255).astype(np.uint8)
    Image.fromarray(generic).save(root/'generic-rgba.png')
    rows = []
    cards = []
    for subject in matrix['subjects']:
        family = 'landing-pad' if subject == 'generic-rgba' else subject
        resolved = load_profile(f'examples/configs/{family}_minimal.yaml', overrides={
            'output.image_size': matrix['image_size'], 'sampling.instances_per_image': [1, 1],
            'sampling.min_visible_bbox_fraction': .1, 'run.num_images': matrix['samples_per_subject'],
            'scene.foreground_resampling': 'premultiplied'})
        scene = resolved.profile.scene.model_copy(update={
            'lighting': None, 'occlusion': SceneOcclusionConfig(probability=1, min_visible_support=0)})
        profile = resolved.profile.model_copy(update={'scene': scene, 'appearance': AppearanceConfig()})
        resolved = resolved.model_copy(update={'profile': profile})
        catalog = build_asset_catalog(resolved)
        for slot in range(matrix['samples_per_subject']):
            plan = ScenePlanner(resolved, catalog).plan(slot, 0)
            if subject == 'generic-rgba':
                original = plan.instances[0]
                asset = replace(original.asset, path=root/'generic-rgba.png', width=128, height=128,
                                logical_path='study/generic-rgba.png', content_hash=digest((root/'generic-rgba.png').read_bytes()))
                plan = replace(plan, instances=(replace(original, asset=asset),))
            background = BackgroundSynthesizer(catalog, resolved.recipes).synthesize(
                plan.recipe_id, plan.canvas_size, np.random.default_rng(matrix['background_seed'] + slot))
            for with_occlusion in matrix['occlusion']:
                instance = plan.instances[0]
                x, y = instance.center
                # A narrow translucent rectangle is anchored to the selected object.
                half_width = plan.camera_rect[2]*instance.width_fraction*.12
                half_height = plan.camera_rect[2]*instance.width_fraction*.45
                blocker = SceneOccluder('debris', ((x-half_width,y-half_height),(x+half_width,y-half_height),
                    (x+half_width,y+half_height),(x-half_width,y+half_height)), (34, 72, 22), .55)
                fixture = replace(plan, occluders=(blocker,) if with_occlusion else ())
                outputs = {}
                for treatment in matrix['treatments']:
                    changes = {'compositing': 'legacy' if treatment == 'legacy' else 'linear-srgb'}
                    if treatment == 'linear-shade':
                        changes['lighting'] = SceneLightingConfig(probability=0, shade=EnvironmentalShadeConfig(
                            probability=1, strength=(.45,.45), radius_fraction=(.6,.6)))
                    candidate = resolved.model_copy(update={'profile': profile.model_copy(update={'scene': scene.model_copy(update=changes)})})
                    result = SceneRenderer(candidate).render(fixture, background)
                    outputs[treatment] = result
                reference = outputs['legacy']
                record = {'subject': subject, 'family': family, 'slot': slot, 'occlusion': with_occlusion,
                          'geometry_signature': fixture.geometry_signature(), 'recipe_id': fixture.recipe_id,
                          'background_seed': matrix['background_seed'] + slot, 'background_source_assets': background.source_assets,
                          'background_graph_hash': background.graph_hash, 'background_sampled_parameters': background.sampled_parameters,
                          'foreground_source': {'logical_path': instance.asset.logical_path, 'sha256': instance.asset.content_hash},
                          'treatments': {}}
                bbox = reference.annotations[0].bbox
                x1, y1, x2, y2 = bbox
                margin = max(8, int(max(x2-x1, y2-y1)*.3))
                crop = (max(0,x1-margin), max(0,y1-margin), min(matrix['image_size'][0],x2+margin), min(matrix['image_size'][1],y2+margin))
                thumbs = []
                for treatment, result in outputs.items():
                    annotations_equal = [_annotation_record(a) for a in reference.annotations] == [_annotation_record(a) for a in result.annotations]
                    masks_equal = (len(reference.full_coverages) == len(result.full_coverages) and len(reference.visible_coverages) == len(result.visible_coverages) and
                        all(np.array_equal(a,b) for a,b in zip(reference.full_coverages + reference.visible_coverages, result.full_coverages + result.visible_coverages)))
                    if not annotations_equal or not masks_equal or reference.rejected_instances != result.rejected_instances:
                        raise RuntimeError(f'Geometry or annotation mismatch: {subject} slot={slot} {treatment}')
                    stem = f'{subject}-{slot:02d}-occ{int(with_occlusion)}-{treatment}'
                    full_name, crop_name = f'{stem}.png', f'{stem}-crop.png'
                    image = Image.fromarray(result.image)
                    image.save(root/full_name)
                    image.crop(crop).save(root/crop_name)
                    np.savez_compressed(root/f'{stem}-masks.npz', **{**{f'full_{i}':a for i,a in enumerate(result.full_coverages)},
                                                                   **{f'visible_{i}':a for i,a in enumerate(result.visible_coverages)}})
                    baseline = 'linear' if treatment == 'linear-shade' else 'legacy'
                    delta = np.abs(result.image.astype(np.int16)-outputs[baseline].image.astype(np.int16))
                    record['treatments'][treatment] = {'image':full_name, 'crop':crop_name,
                        'image_sha256':digest((root/full_name).read_bytes()), 'comparison_baseline':baseline, 'annotation_equal':annotations_equal, 'masks_equal':masks_equal,
                        'mean_abs_rgb_difference':float(delta.mean()), 'max_abs_rgb_difference':int(delta.max()),
                        'changed_pixel_fraction':float(np.any(delta != 0, axis=2).mean()), 'scene_effects':result.scene_effects}
                    thumbs.append(f'<figure><figcaption>{html.escape(treatment)}</figcaption><a href="{full_name}"><img src="{full_name}"></a><a href="{crop_name}"><img src="{crop_name}"></a></figure>')
                rows.append(record)
                cards.append(f'<section><h2>{html.escape(subject)} · sample {slot} · occlusion {with_occlusion}</h2><div class="pair">{"".join(thumbs)}</div></section>')
    summary = {'schema_version': 1, 'matrix': matrix, 'fixture_count':len(rows), 'rendered_images':len(rows)*len(matrix['treatments']),
               'purpose':'paired visual and annotation comparison; no throughput measurements',
               'notes':['generic-rgba substitutes a generated alpha-gradient asset into the pad family; it is not a separate family',
                        'shade is a qualitative scene-wide elliptical field, not a physical shadow',
                        'each layer is quantized to 8-bit sRGB between linear-light compositing steps'], 'fixtures':rows}
    (root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    (root/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Paired planar compositing study</title>'
        '<style>body{font:16px system-ui;max-width:1400px;margin:auto;padding:24px}.pair{display:flex;flex-wrap:wrap;gap:12px}figure{margin:0;flex:1;min-width:240px}img{max-width:100%;height:auto;display:block;margin:8px 0}section{border-top:1px solid #bbb;padding:12px 0}</style>'
        f'<h1>Paired planar compositing study</h1><p>{len(rows)} fixtures, {len(rows)*len(matrix["treatments"])} images. Full frame and native crop shown; click to inspect. No timings.</p>'
        '<p>Generic RGBA is a synthetic alpha-gradient substituted into the pad family. Shade is qualitative and scene-wide. Linear is compared with legacy; shade is compared with linear.</p>' + ''.join(cards))
    print(json.dumps({'output':str(root), 'fixtures':len(rows), 'rendered_images':len(rows)*len(matrix['treatments'])}))


if __name__ == '__main__':
    main()
