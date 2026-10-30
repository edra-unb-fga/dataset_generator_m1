#!/usr/bin/env python3
"""Build a portable paired-image report from an extracted camera-study archive."""
from __future__ import annotations
import argparse, base64, html, io, json, re
from pathlib import Path
import numpy as np
from PIL import Image


def load_masks(path):
    with np.load(path, allow_pickle=False) as f:
        return {key: np.asarray(f[key]) for key in f.files}


def compare_images(base_image, image, base_masks, masks):
    """Numbers show visual changes, not realism, utility, or statistical significance."""
    a, b = np.asarray(base_image.convert('RGB'), dtype=np.int16), np.asarray(image.convert('RGB'), dtype=np.int16)
    masks_equal = sorted(base_masks) == sorted(masks) and all(np.array_equal(base_masks[k], masks[k]) for k in base_masks)
    out = {'masks_equal':bool(masks_equal), 'rgb_shape_match':a.shape == b.shape, 'rgb_mae':None, 'foreground_rgb_mae':None, 'background_rgb_mae':None, 'visible_pixels':None}
    if a.shape != b.shape:
        return out
    delta = np.abs(a-b).astype(np.float32).mean(axis=2)
    out['rgb_mae'] = float(delta.mean())
    visible=base_masks.get('visible')
    if visible is not None and visible.ndim == 3 and visible.shape[1:] == delta.shape:
        support=np.any(visible != 0,axis=0)
        out['visible_pixels']=int(support.sum())
        if support.any(): out['foreground_rgb_mae']=float(delta[support].mean())
        if (~support).any(): out['background_rgb_mae']=float(delta[~support].mean())
    return out


def crop_box(masks, size):
    """One baseline-derived crop for all matched variants, so framing is not cherry-picked."""
    w,h=size
    visible=masks.get('visible')
    if visible is None or visible.ndim != 3 or visible.shape[1:] != (h,w): return None
    if visible.shape[0] == 0:return None
    areas=np.count_nonzero(visible,axis=(1,2))
    support=visible[int(np.argmax(areas))] != 0
    if not support.any():return None
    ys,xs=np.where(support); margin=max(8,round(max(xs.max()-xs.min()+1,ys.max()-ys.min()+1)*.15))
    return (max(0,int(xs.min())-margin), max(0,int(ys.min())-margin),min(w,int(xs.max())+1+margin),min(h,int(ys.max())+1+margin))


def embedded(image, limit, alt):
    image=image.convert('RGB');image.thumbnail((limit,limit),Image.Resampling.LANCZOS)
    data=io.BytesIO();image.save(data,format='JPEG',quality=82)
    return '<img loading="lazy" alt="'+html.escape(alt,quote=True)+'" src="data:image/jpeg;base64,'+base64.b64encode(data.getvalue()).decode()+'">'


def image_at(root, cell, job):
    if not re.fullmatch(r'[a-z0-9-]+',cell) or not re.fullmatch(r'[a-z0-9-]+',job): raise ValueError('Unsafe cell or job ID')
    return root/'cells'/cell/'scenes'/job


def numeric(value):
    return '—' if value is None else f'{value:.2f}'


def build(root, output, metrics_path=None):
    root,output=Path(root),Path(output)
    summary=json.loads((root/'summary.json').read_text())
    matrix=json.loads((root/'matrix.json').read_text())
    cells=matrix['cells'];names=[cell['id'] for cell in cells]
    if not names or names[0]!='baseline' or len(set(names))!=len(names): raise ValueError('Unique cells with baseline first are required')
    records={r['cell']:r for r in summary.get('records',[])}
    jobs=list(dict.fromkeys(job for cell in cells for job in cell['jobs']))
    results=[]; pictures={}; crops={}
    for job in jobs:
        base_path=image_at(root,'baseline',job)
        try:
            with Image.open(base_path/'rgb.png') as im: base=im.convert('RGB')
            base_masks=load_masks(base_path/'masks.npz');box=crop_box(base_masks,base.size)
        except (OSError,ValueError,KeyError):base=None;base_masks=None;box=None
        for cell in cells:
            name=cell['id']
            if job not in cell['jobs']:continue
            path=image_at(root,name,job);metrics={'cell':name,'job':job,'status':'missing','reason':None}
            try:
                with Image.open(path/'rgb.png') as im:image=im.convert('RGB')
                masks=load_masks(path/'masks.npz')
                result=json.loads((path/'result.json').read_text())
                metrics['status']=result.get('status','unknown')
                if base is not None and base_masks is not None:
                    metrics.update(compare_images(base,image,base_masks,masks))
                pictures[name,job]=embedded(image,400,f'{name}: {job}, full render')
                if box and image.size==base.size:
                    crops[name,job]=embedded(image.crop(box),320,f'{name}: {job}, matching target crop')
            except (OSError,ValueError,KeyError) as exc:metrics['reason']=str(exc)
            results.append(metrics)
    by_pair={(r['cell'],r['job']):r for r in results}
    esc=html.escape
    text=['<!doctype html><html><head><meta charset="utf-8"><title>Paired physical realism effects</title><style>body{font:16px system-ui;max-width:1600px;margin:2rem auto;padding:0 1rem;color:#202832}table{border-collapse:collapse;width:100%;font-size:.92em}th,td{padding:.5rem;border-bottom:1px solid #ddd;text-align:left;vertical-align:top}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:1rem}.card{border:1px solid #ccc;border-radius:6px;padding:.7rem;min-width:0}.images{display:grid;grid-template-columns:1fr 1fr;gap:.25rem}.images img{width:100%;height:auto;object-fit:contain;align-self:start}.note{background:#fff4d4;padding:1rem}small{color:#4a5260}.bad{color:#a20d0d}code{font-size:.85em}</style></head><body><h1>Paired physical rendering effects</h1>',
      '<p class="note">Exploratory synthetic scenes reuse source assets and were selected for visual diversity. The caster treatment is diagnostic. Wear changes albedo, roughness and bump together; overcast changes lighting and does not isolate cast shadows. Pixel differences measure how much an image changed, not realism, model usefulness or significance. Crop boundaries come from the largest baseline visible target and are reused across variants. JPEGs below are reduced previews; inspect original PNGs for detail.</p>',
      f'<p>Study status: {esc(str(summary.get("status","unknown")))}; elapsed study time: {numeric(summary.get("elapsed_seconds"))} s. Missing or failed outputs are explicitly identified.</p>',
      '<h2>Per-treatment measurements</h2><p>RGB mean absolute difference is in 8-bit levels from 0–255, averaged over paired images; foreground uses baseline visible masks and background is its complement. Exact masks compare all arrays by name and value. Command times include per-cell startup and are not controlled throughput benchmarks.</p>',
      '<table><thead><tr><th>Treatment</th><th>Accepted / requested</th><th>Exact masks / comparable</th><th>Mean RGB Δ</th><th>Foreground Δ</th><th>Background Δ</th><th>Command s</th><th>Peak GPU MiB</th></tr></thead><tbody>']
    for cell in cells:
        name=cell['id'];rows=[r for r in results if r['cell']==name];record=records.get(name,{});outcome=record.get('outcome',{})
        comparable=[r for r in rows if 'masks_equal' in r]
        def avg(k):
            values=[r[k] for r in rows if r.get(k) is not None]
            return sum(values)/len(values) if values else None
        text.append('<tr><td>'+esc(name)+'</td><td>'+str(sum(r['status']=='accepted' for r in rows))+' / '+str(len(cell['jobs']))+'</td><td>'+str(sum(r['masks_equal'] for r in comparable))+' / '+str(len(comparable))+'</td><td>'+numeric(avg('rgb_mae'))+'</td><td>'+numeric(avg('foreground_rgb_mae'))+'</td><td>'+numeric(avg('background_rgb_mae'))+'</td><td>'+numeric(outcome.get('command_seconds'))+'</td><td>'+numeric(outcome.get('sampled_peak_gpu_memory_mib'))+'</td></tr>')
    text.append('</tbody></table><h2>Paired scenes</h2><p>Each row uses the same scene intent. Full view appears on the left and the common target crop on the right. The close-up is a deliberately constructed diagnostic rather than an ordinary sampled view.</p>')
    for job in jobs:
        text.append('<section><h3>'+esc(job)+'</h3><div class="grid">')
        for cell in cells:
            name=cell['id'];r=by_pair.get((name,job))
            if r is None:continue
            text.append('<article class="card"><strong>'+esc(name)+'</strong><div class="images">'+pictures.get((name,job),'<p>Image unavailable</p>')+crops.get((name,job),'<p>Crop unavailable</p>')+'</div>')
            text.append('<small>Status: '+esc(r['status'])+'; mask match: '+esc(str(r.get('masks_equal','unavailable')))+'; RGB Δ: '+numeric(r.get('rgb_mae'))+'; foreground Δ: '+numeric(r.get('foreground_rgb_mae'))+'; background Δ: '+numeric(r.get('background_rgb_mae'))+'</small></article>')
        text.append('</div></section>')
    text.append('</body></html>')
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(''.join(text),encoding='utf-8')
    payload={'schema_version':1,'status':summary.get('status'),'matrix_purpose':matrix.get('purpose'),'metrics':results}
    destination=Path(metrics_path) if metrics_path else output.with_suffix('.metrics.json')
    destination.parent.mkdir(parents=True,exist_ok=True);destination.write_text(json.dumps(payload,indent=2,allow_nan=False)+'\n')
    return payload


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',required=True,help='Extracted results directory');p.add_argument('--output',required=True,help='Self-contained HTML output');p.add_argument('--metrics-output',help='Optional metrics JSON path')
    args=p.parse_args();build(args.input,args.output,args.metrics_output)
if __name__=='__main__':main()
