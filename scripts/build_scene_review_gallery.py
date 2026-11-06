#!/usr/bin/env python3
"""Build a portable, image-first review from a manifest of actual results.

The manifest is JSON with ``title`` and ``images``. Each image has a relative
``path``, ``engine``, ``family``, ``condition``, and a ``metadata`` object.
Paths are relative to the manifest, and the report must be written beside it.
"""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from urllib.parse import quote


def build(manifest: Path, output: Path) -> int:
    manifest, output = manifest.resolve(), output.resolve()
    if output == manifest:
        raise ValueError('Report output must not overwrite its manifest')
    if output.parent != manifest.parent:
        raise ValueError('Write the report beside its manifest so image paths remain portable')
    data = json.loads(manifest.read_text(encoding='utf-8'))
    if not isinstance(data.get('images'), list):
        raise ValueError('images must be a list')
    cards = []
    for index, item in enumerate(data['images']):
        relative = Path(item['path'])
        resolved = (manifest.parent / relative).resolve()
        if relative.is_absolute() or not resolved.is_relative_to(manifest.parent) or not resolved.is_file():
            raise ValueError(f'Image {index} must exist inside the manifest directory: {relative}')
        if relative.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp'):
            raise ValueError(f'Unsupported image type: {relative}')
        metadata = item.get('metadata', {})
        if not isinstance(metadata, dict):
            raise ValueError('metadata must be an object')
        engine, family, condition = (str(item.get(k, 'unknown')) for k in ('engine', 'family', 'condition'))
        label = str(item.get('label', relative.stem))
        source = quote(relative.as_posix(), safe='/')
        attrs = ' '.join(f'data-{key}="{html.escape(value, quote=True)}"' for key, value in
                         (('engine', engine), ('family', family), ('condition', condition)))
        detail = html.escape(json.dumps(metadata, indent=2, ensure_ascii=False))
        cards.append(f'<article {attrs}><button class="image-button" type="button" aria-label="Open {html.escape(label, quote=True)} full screen"><img loading="lazy" src="{source}" alt="{html.escape(label, quote=True)}"></button><h2>{html.escape(label)}</h2><p>{html.escape(engine)} · {html.escape(family)} · {html.escape(condition)}</p><details><summary>Image metadata</summary><pre>{detail}</pre></details><a href="{source}">Open original image</a></article>')
    title = html.escape(str(data.get('title', 'Scene review')))
    page = TEMPLATE.replace('__TITLE__', title).replace('__CARDS__', '\n'.join(cards))
    output.write_text(page, encoding='utf-8')
    return len(cards)


TEMPLATE = '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title><style>
:root{color-scheme:light dark;font-family:system-ui,sans-serif}body{margin:0;padding:1.2rem;line-height:1.45}header{max-width:80rem;margin:auto}label{display:inline-block;margin:.4rem}select{font:inherit;padding:.3rem}main{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:1rem;max-width:90rem;margin:auto}article{border:1px solid #777;border-radius:.5rem;padding:.6rem;min-width:0}article[hidden]{display:none}h2{font-size:1rem;overflow-wrap:anywhere}article p{font-size:.9rem}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:.8rem}.image-button{border:0;background:none;padding:0;width:100%;cursor:zoom-in}.image-button img{width:100%;aspect-ratio:1;object-fit:contain;background:#222}dialog{width:96vw;height:94vh;max-width:none;max-height:none;box-sizing:border-box;background:#111;color:white;border:1px solid #888}dialog[open]{display:flex;flex-direction:column}dialog::backdrop{background:#000d}dialog .toolbar{display:flex;gap:.5rem;align-items:center;flex-wrap:wrap}dialog button,dialog a{font:inherit;color:inherit}dialog img{display:block;width:100%;flex:1;min-height:0;object-fit:contain}dialog details{max-height:30vh;overflow:auto}dialog:fullscreen{width:100vw;height:100vh}
</style></head><body><header><h1>__TITLE__</h1><p>Open any image for a larger view, full screen, its original file and its recorded metadata. Filters apply to the review gallery.</p><div id="filters"></div><p id="count" aria-live="polite"></p></header><main>__CARDS__</main>
<dialog aria-label="Large image viewer"><div class="toolbar"><button type="button" id="close">Close (Esc)</button><button type="button" id="previous">Previous</button><button type="button" id="next">Next</button><button type="button" id="fullscreen">Full screen</button><a id="original" target="_blank" rel="noopener">Open original</a><span id="caption"></span></div><details><summary>Image metadata</summary><pre id="large-metadata"></pre></details><img id="large" alt=""></dialog>
<script>
const cards=[...document.querySelectorAll('article')], filters=document.querySelector('#filters'), count=document.querySelector('#count'), dialog=document.querySelector('dialog'), large=document.querySelector('#large');let current=null;
for(const key of ['engine','family','condition']){const label=document.createElement('label');label.textContent=key+': ';const select=document.createElement('select');select.dataset.key=key;const any=document.createElement('option');any.value='';any.textContent='All';select.append(any);for(const value of [...new Set(cards.map(c=>c.dataset[key]))].sort()){const o=document.createElement('option');o.value=value;o.textContent=value;select.append(o)}select.addEventListener('change',apply);label.append(select);filters.append(label)}
function apply(){const selections=[...filters.querySelectorAll('select')];for(const card of cards)card.hidden=selections.some(s=>s.value&&card.dataset[s.dataset.key]!==s.value);count.textContent=cards.filter(c=>!c.hidden).length+' of '+cards.length+' images'}
function show(card){current=card;const img=card.querySelector('img');large.src=img.src;large.alt=img.alt;document.querySelector('#caption').textContent=img.alt;document.querySelector('#original').href=img.src;document.querySelector('#large-metadata').textContent=card.querySelector('pre').textContent;if(!dialog.open)dialog.showModal()}
for(const card of cards)card.querySelector('.image-button').addEventListener('click',()=>show(card));document.querySelector('#close').addEventListener('click',()=>dialog.close());function step(delta){const visible=cards.filter(c=>!c.hidden), i=visible.indexOf(current);if(visible.length)show(visible[(i+delta+visible.length)%visible.length])}document.querySelector('#previous').addEventListener('click',()=>step(-1));document.querySelector('#next').addEventListener('click',()=>step(1));document.querySelector('#fullscreen').addEventListener('click',()=>{if(document.fullscreenElement)document.exitFullscreen();else if(dialog.requestFullscreen)dialog.requestFullscreen()});dialog.addEventListener('keydown',e=>{if(e.key==='ArrowLeft')step(-1);if(e.key==='ArrowRight')step(1)});apply();
</script></body></html>'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(f'Wrote {build(args.manifest, args.output)} images to {args.output}')


if __name__ == '__main__':
    main()
