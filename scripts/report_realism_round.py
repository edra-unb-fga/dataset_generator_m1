#!/usr/bin/env python3
"""Create a self-contained visual report from an extracted realism study phase."""
import argparse
import base64
import html
import io
import json
from pathlib import Path

from PIL import Image


def image_tag(path):
    if not path.is_file():
        return '<p>Image unavailable</p>'
    with Image.open(path) as image:
        image = image.convert('RGB')
        image.thumbnail((480, 480))
        data = io.BytesIO()
        image.save(data, format='JPEG', quality=82)
    encoded = base64.b64encode(data.getvalue()).decode('ascii')
    return f'<img loading="lazy" src="data:image/jpeg;base64,{encoded}" alt="Synthetic render">'


def build(root, output, analysis_path=None):
    root, output = Path(root), Path(output)
    summary = json.loads((root / 'summary.json').read_text())
    records = summary.get('records', [])
    comparisons = summary.get('comparisons', [])
    analysis = json.loads(Path(analysis_path).read_text()) if analysis_path else None
    if analysis is not None:
        comparisons = analysis.get('paired_checks', comparisons)
    text = ['<!doctype html><html><head><meta charset="utf-8"><title>Realism study</title>',
        '<style>body{font:16px system-ui;max-width:1500px;margin:2rem auto;padding:0 1rem}',
        'table{border-collapse:collapse;width:100%}td,th{padding:.5rem;border-bottom:1px solid #ddd;vertical-align:top}',
        'img{max-width:100%;height:auto}td{width:43%}.warning{background:#fff3cc;padding:1rem}</style></head><body>',
        '<h1>Physical rendering study</h1>',
        '<p class="warning">Synthetic engineering evidence. Shared source assets and a reference pool are reused; visual preference does not establish realism or detector accuracy. Images are reduced for this report; inspect original renders for contact and small details.</p>',
        f'<p>Study status: {html.escape(str(summary.get("status", "unknown")))}. ',
        f'Elapsed study time: {summary.get("elapsed_seconds", 0):.1f} s. ',
        f'Paired mask comparisons: {len(comparisons)}; exact matches: {sum(bool(c.get("all_masks_equal", c.get("masks_equal"))) for c in comparisons)}.</p>',
        '<table><tr><th>Cell</th><th>Accepted / observed</th><th>Command seconds</th><th>Peak sampled GPU MiB</th></tr>']
    for rec in records:
        outcome = rec.get('outcome', {})
        rows = rec.get('rows', [])
        text.append('<tr><td>' + html.escape(rec['cell']) + '</td><td>' +
            f'{sum(r.get("status") == "accepted" for r in rows)} / {len(rows)}</td><td>' +
            html.escape(str(outcome.get('command_seconds', 'unavailable'))) + '</td><td>' +
            html.escape(str(outcome.get('sampled_peak_gpu_memory_mib', 'unavailable'))) + '</td></tr>')
    text.append('</table>')
    if analysis is not None:
        text.append('<p>Paired metrics shown above were independently re-analyzed after the original phase failed; the original status remains unchanged.</p>')
    baseline = next((r for r in records if r['cell'] == 'baseline'), None)
    candidate = next((r for r in records if r['cell'] == 'surface-light'), None)
    if baseline and candidate:
        a = {r['job']: r for r in baseline['rows']}
        b = {r['job']: r for r in candidate['rows']}
        text.append('<h2>Paired baseline and surface-light treatment</h2><table><tr><th>Intent</th><th>Baseline</th><th>Surface-light candidate</th></tr>')
        for job in sorted(a.keys() | b.keys()):
            text.append('<tr><th>' + html.escape(job) + '</th>')
            for cell, rows in ((baseline, a), (candidate, b)):
                status = rows.get(job, {}).get('status', 'missing')
                path = root / 'cells' / cell['cell'] / 'scenes' / job / 'rgb.png'
                text.append('<td>' + image_tag(path) + '<p>' + html.escape(str(status)) + '</p></td>')
            text.append('</tr>')
        text.append('</table>')
    for rec in records:
        if rec['cell'] in ('baseline', 'surface-light'):
            continue
        text.append('<h2>' + html.escape(rec['cell']) + '</h2><table>')
        for row in rec.get('rows', []):
            path = root / 'cells' / rec['cell'] / 'scenes' / row['job'] / 'rgb.png'
            text.append('<tr><th>' + html.escape(row['job']) + '</th><td>' + image_tag(path) + '</td><td>' + html.escape(str(row.get('status'))) + '</td></tr>')
        text.append('</table>')
    text.append('</body></html>')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(''.join(text), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, help='Extracted results directory for one study phase')
    parser.add_argument('--output', required=True, help='HTML output file')
    parser.add_argument('--analysis', help='Optional independently recovered comparison JSON')
    args = parser.parse_args()
    build(args.input, args.output, args.analysis)


if __name__ == '__main__':
    main()
