#!/usr/bin/env python3
"""Add client-side treatment filters to an existing local effects HTML report."""
import argparse
from pathlib import Path

SCRIPT = r'''<script>
(() => {
  const cards = [...document.querySelectorAll('.cell, .card')];
  const entries = cards.map(card => ({card, name: (card.querySelector('b, strong')?.textContent || '').trim()})).filter(x => x.name);
  const names = [...new Set(entries.map(x => x.name))];
  if (!names.length) return;
  const panel = document.createElement('section');
  panel.setAttribute('aria-label', 'Filter treatments');
  panel.style.cssText = 'position:sticky;top:0;z-index:5;background:#fff;border:1px solid #c9d0d8;padding:10px;margin:12px 0;box-shadow:0 2px 7px #0002';
  const title = document.createElement('strong'); title.textContent = 'Show treatments: '; panel.append(title);
  const boxes = new Map();
  const refresh = () => { for (const e of entries) e.card.style.display = boxes.get(e.name).checked ? '' : 'none'; };
  for (const name of names) {
    const label = document.createElement('label'); label.style.cssText = 'display:inline-block;margin:4px 10px 4px 0';
    const box = document.createElement('input'); box.type = 'checkbox'; box.checked = true; box.addEventListener('change', refresh);
    boxes.set(name, box); label.append(box, document.createTextNode(' ' + name)); panel.append(label);
  }
  const button = (label, predicate) => { const b=document.createElement('button');b.type='button';b.textContent=label;b.style.marginRight='8px';b.onclick=()=>{for(const [name,box] of boxes) box.checked=predicate(name);refresh();};panel.append(b); };
  panel.append(document.createElement('br'));
  button('Show all', () => true);
  const individual = new Set(['baseline','wear','lighting','shade','context','moderate-wear','glossy','matte','overcast','caster-diagnostic']);
  button('Baseline and individual effects', n => individual.has(n));
  button('Baseline and combinations', n => n === 'baseline' || !individual.has(n));
  document.body.insertBefore(panel, document.body.firstChild);
})();
</script>'''

def enhance(source, destination):
    source, destination = Path(source), Path(destination)
    if source.parent.resolve() != destination.parent.resolve():
        raise ValueError('Keep the filtered report beside the original so relative image paths work')
    text = source.read_text(encoding='utf-8')
    if '<script>' in text and 'Filter treatments' in text:
        raise ValueError('Report already contains filters')
    destination.write_text(text + SCRIPT, encoding='utf-8')

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();enhance(args.input,args.output)
