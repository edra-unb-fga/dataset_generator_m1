#!/usr/bin/env python3
"""Add an effect-size overview to the paired 2D report, preserving local image links."""
import argparse
import html
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean


def build(report, metrics, output):
    report, output = Path(report), Path(output)
    if report.parent.resolve() != output.parent.resolve():
        raise ValueError('Output must stay beside the original report so image links work')
    data = json.loads(Path(metrics).read_text(encoding='utf-8'))
    groups = defaultdict(list)
    for row in data['rows']:
        groups[row['variant']].append(row)
    sections = ['<section style="margin:1rem 0;padding:1rem;background:#f3f6fa;border:1px solid #ccd4dc">',
        '<h2>How much each treatment changed the image</h2>',
        '<p>Average absolute RGB difference from the paired baseline, in levels from 0–255. Target uses the baseline visible mask; background uses its complement. Larger means more changed, not better. These are small, selected synthetic samples; JPEG and capture effects can affect both regions.</p>',
        '<table style="border-collapse:collapse"><thead><tr><th>Treatment</th><th>Scenes</th><th>Target Δ</th><th>Background Δ</th><th>Relative target change</th></tr></thead><tbody>']
    for name, rows in groups.items():
        target=[r['inside_mae_rgb_0_255'] for r in rows if r.get('inside_mae_rgb_0_255') is not None]
        outside=[r['outside_mae_rgb_0_255'] for r in rows if r.get('outside_mae_rgb_0_255') is not None]
        t=mean(target) if target else 0; b=mean(outside) if outside else 0
        sections.append('<tr><th style="text-align:left;padding:.3rem">'+html.escape(name)+'</th><td>'+str(len(rows))+'</td><td>'+f'{t:.2f}'+'</td><td>'+f'{b:.2f}'+'</td><td><span style="display:inline-block;background:#4b77ae;height:12px;width:'+str(min(250,round(t*5)))+'px"></span></td></tr>')
    sections.append('</tbody></table></section>')
    raw = report.read_text(encoding='utf-8')
    if '<h1>' not in raw: raise ValueError('Expected an HTML report with a heading')
    output.write_text(raw.replace('<h1>', ''.join(sections)+'<h1>', 1), encoding='utf-8')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',required=True);p.add_argument('--metrics',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();build(a.report,a.metrics,a.output)
