"""Read one trusted local native sample per invocation; validate prototype and evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image
from contract import Sample
from dataset_generator_m1.annotation_evidence import decode_mask_evidence

LIMIT = 32 * 1024 * 1024


def read(path):
    if path.stat().st_size > LIMIT: raise ValueError('File exceeds 32 MiB limit')
    return path.read_bytes()


def sha(data): return hashlib.sha256(data).hexdigest()


def planar(pool):
    run = json.loads(read(pool/'run.json'))
    with (pool/'samples.jsonl').open('rb') as stream:
        line = stream.readline(LIMIT + 1)
    if len(line) > LIMIT: raise ValueError('Sample row exceeds limit')
    row = json.loads(line)
    manifest = row['mask_evidence']; raw = read(pool/manifest['path'])
    decoded = decode_mask_evidence(raw, manifest)
    width,height = manifest['image_size']; annotations=[]
    refs = {v['instance_id']:v for v in manifest['instances']}
    for a in row['annotations']:
        item=refs[a['instance_id']]
        def evidence(kind):
            ref=item[kind]
            if ref.get('same_as') == 'full': ref=item['full']
            return dict(archive=manifest['path'],archive_sha256=manifest['sha256'],key=ref['key'],
                encoding='cropped-alpha-u8',origin_xy=ref['origin'],shape_hw=ref['shape'],threshold=manifest['alpha_threshold'])
        arrays=decoded[a['instance_id']]
        if np.any(arrays['visible'] > arrays['full']): raise ValueError('Visible alpha exceeds full')
        annotations.append(dict(instance_id=a['instance_id'],source_instance_id=None,class_id=a['class_id'],class_name=a['class_name'],bbox_xyxy=a['bbox'],full=evidence('full'),visible=evidence('visible')))
    image=read(pool/row['image_path'])
    with Image.open(pool/row['image_path']) as im:
        if im.size != (width,height): raise ValueError('Image shape mismatch')
    return Sample.model_validate_json(json.dumps(dict(version='cross-engine-sample-v1',engine='planar-2d',sample_id=str(row['slot']),source_identity=run['generation_identity']['sha256'],image_uri=row['image_path'],image_sha256=sha(image),width=width,height=height,intentional_negative=row.get('intentional_negative'),source_revision=None,annotations=annotations)))


def blender(scene):
    row=json.loads(read(scene/'result.json'))
    if row['status']!='accepted': raise ValueError('Expected accepted result')
    raw=read(scene/'masks.npz'); image=read(scene/'rgb.png')
    if sha(raw)!=row['files']['masks.npz'] or sha(image)!=row['files']['rgb.png']: raise ValueError('File hash mismatch')
    with Image.open(scene/'rgb.png') as im: width,height=im.size
    with np.load(scene/'masks.npz',allow_pickle=False) as archive:
        full=archive['full']; visible=archive['visible']
    if full.shape!=visible.shape or full.ndim!=3 or full.shape[1:]!=(height,width) or full.dtype!=np.bool_ or visible.dtype!=np.bool_: raise ValueError('Invalid binary masks')
    if np.any(visible & ~full): raise ValueError('Visible mask exceeds full')
    originals=(row.get('placement_diagnostics') or {}).get('retained_original_indices')
    if originals is not None and len(originals)!=len(full): raise ValueError('Original index count mismatch')
    annotations=[]
    for index,mask in enumerate(visible):
        ys,xs=np.where(mask)
        bbox=[int(xs.min()),int(ys.min()),int(xs.max()+1),int(ys.max()+1)] if len(xs) else None
        def evidence(kind):
            return dict(archive='masks.npz',archive_sha256=sha(raw),key=f'{kind}[{index}]',encoding='binary-array',origin_xy=None,shape_hw=[height,width],threshold=None)
        annotations.append(dict(instance_id=str(index),source_instance_id=str(originals[index]) if originals is not None else None,class_id=1,class_name='pad',bbox_xyxy=bbox,full=evidence('full'),visible=evidence('visible')))
    return Sample.model_validate_json(json.dumps(dict(version='cross-engine-sample-v1',engine='blenderproc-3d',sample_id=row['job']['id'],source_identity=row['identity'],image_uri='rgb.png',image_sha256=sha(image),width=width,height=height,intentional_negative=row['job']['scene'].get('negative'),source_revision=None,annotations=annotations)))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('engine',choices=('planar','blender'))
    parser.add_argument('path',type=Path,help='2D pool or accepted Blender scene directory')
    args=parser.parse_args()
    print((planar(args.path) if args.engine=='planar' else blender(args.path)).model_dump_json(indent=2))
