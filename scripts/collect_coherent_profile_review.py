#!/usr/bin/env python3
"""Assemble paired 2D studies and a verified 3D capture study into a gallery."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from PIL import Image

from collect_2d_review_gallery import collect


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect_review(studies, capture, source_3d, output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    for label, study in studies:
        if Path(label).name != label or label in ('.', '..'):
            raise ValueError('Study label must be a simple filename')
        sub = output/label
        result = collect(Path(study), sub)
        for item in result['images']:
            item['path'] = f"{label}/{item['path']}"
            if item['metadata'].get('profile_file'):
                item['metadata']['profile_file'] = f"{label}/{item['metadata']['profile_file']}"
            item['condition'] = f"{label} / {item['condition']}"
            item['label'] = label + ' · ' + item['label']
            rows.append(item)
            sample = item['metadata']['sample']
            if sample.get('annotations'):
                a = max(sample['annotations'], key=lambda x: (x['bbox'][2]-x['bbox'][0])*(x['bbox'][3]-x['bbox'][1]))
                x1,y1,x2,y2 = map(int, a['bbox'])
                original = output/item['path']
                with Image.open(original) as image:
                    box = (max(0,x1-10),max(0,y1-10),min(image.width,x2+10),min(image.height,y2+10))
                    target = original.with_name('crop-'+original.name)
                    image.crop(box).save(target)
                crop = dict(item)
                crop['path'] = target.relative_to(output).as_posix()
                crop['engine'] = '2D crop'
                crop['label'] = item['label'] + ' · target crop'
                crop['metadata'] = {**item['metadata'], 'crop_bbox_xyxy': box, 'crop_sha256': sha(target)}
                rows.append(crop)
    capture = Path(capture).resolve(); source_3d = Path(source_3d).resolve()
    manifest = json.loads((capture/'capture-manifest.json').read_text())
    for item in manifest['images']:
        job = item['job_id']
        if Path(job).name != job or job in ('.', '..'):
            raise ValueError('Unsafe 3D job ID')
        source_result = json.loads((source_3d/'scenes'/job/'result.json').read_text())
        for kind, path, expected in [('source', source_3d/'scenes'/job/'rgb.png', item['source_rgb_sha256']),
                                     ('capture', capture/item['image'], item['image_sha256'])]:
            if sha(path) != expected:
                raise ValueError('3D image checksum differs from capture manifest')
            target = output/'3d'/job/(kind+'.png');target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(path, target)
            rows.append({'path': target.relative_to(output).as_posix(), 'engine':'3D post-render',
                         'family':'landing-pad','condition':'3D '+kind,'label':f'3D · {job} · {kind}',
                         'metadata':{'capture_identity':manifest['identity'],'source_study_identity':manifest['source_study_identity'],
                                     'image_sha256':expected,'capture_trace':item['trace'] if kind=='capture' else [],
                                     'geometric_masks_sha256':item['source_masks_sha256'], 'job':source_result['job']}})
    result={'title':'Coherent profiles and capture: paired review','images':rows}
    (output/'manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study',nargs=2,action='append',required=True,metavar=('LABEL','PATH'))
    parser.add_argument('--capture',required=True);parser.add_argument('--source-3d',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args(); result=collect_review(args.study,args.capture,args.source_3d,args.output)
    print(f"Collected {len(result['images'])} gallery cards")


if __name__=='__main__':
    main()
