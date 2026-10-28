#!/usr/bin/env python3
"""Build a portable camera study report from the raw experiment bundle."""
import argparse
import base64
import html
import json
from pathlib import Path

def read(path, default=None):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default

def case(path):
    progress = read(path / 'progress.json', {}) or {}
    scenes = []
    for file in sorted(path.glob('scenes/*/result.json')):
        result = read(file, {}) or {}
        scenes.append({'job': file.parent.name, 'status': result.get('status'),
                       'tilt': (result.get('job', {}).get('camera_pose') or {}).get('tilt_degrees'),
                       'mask_present': (file.parent / 'masks.npz').is_file(),
                       'rgb_present': (file.parent / 'rgb.png').is_file(),
                       'attempts': len(result.get('attempts', [])),
                       'supports': [a.get('support') for a in result.get('attempts', [])]})
    keys = ('status', 'reason', 'peak_rss_bytes', 'minimum_available_bytes', 'swap_out_delta_bytes')
    return {'status': progress.get('status', 'missing'), 'resources': {k: progress[k] for k in keys if k in progress}, 'scenes': scenes}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=Path('outputs/experiments/realism-camera-round'))
    parser.add_argument('--output', type=Path, default=Path('docs/experiments/camera-environments-v1'))
    args = parser.parse_args()
    root, out = args.input, args.output
    summary = read(root / '2d/summary.json')
    if not summary:
        raise SystemExit('2d/summary.json is required')
    fixtures = []
    for f in summary['fixtures']:
        keys = ('comparison_baseline', 'annotation_equal', 'masks_equal', 'mean_abs_rgb_difference', 'max_abs_rgb_difference', 'changed_pixel_fraction')
        fixtures.append({'subject': f['subject'], 'occlusion': f['occlusion'], 'treatments': {n: {k: t.get(k) for k in keys} for n, t in f['treatments'].items()}})
    development = []
    for record in (read(root / 'development/summary.json', {}) or {}).get('records', []):
        outcome = record.get('outcome', {})
        keys = ('status', 'reason', 'peak_rss_bytes', 'minimum_available_bytes', 'swap_out_delta_bytes')
        development.append({'cell': record.get('cell'), 'resources': {k: outcome.get(k) for k in keys}, 'rows': [{'job': r.get('job'), 'status': r.get('status'), 'tilt': (r.get('camera', {}).get('pose') or {}).get('tilt_degrees')} for r in record.get('rows', [])]})
    compact = {'schema_version': 1, '2d': {'fixture_count': summary['fixture_count'], 'rendered_images': summary['rendered_images'], 'notes': summary.get('notes', []), 'fixtures': fixtures}, 'early_prototype': {x: case(root / 'smoke' / x) for x in ('open-r1', 'indoor-r1', 'outdoor-r1')}, 'development_partial': development, 'current_reduced': {x: case(root / 'reduced-3d' / x) for x in ('open-view', 'indoor-view', 'outdoor-view', 'motion-distortion')}}
    compact['retry_once'] = case(root / 'retry-once' / 'open-view')
    out.mkdir(parents=True, exist_ok=True)
    (out / 'compact.json').write_text(json.dumps(compact, indent=2) + '\n')
    e = html.escape
    images = []
    for name in ('2d-landing-pad-paired', '2d-landing-paired', '2d-manometro-paired', '2d-generic-rgba-paired', '2d-occ0-crops', '2d-occ1-crops', '3d-smoke-r1-comparison'):
        path = root / 'reviews' / (name + '.png')
        if path.is_file():
            uri = base64.b64encode(path.read_bytes()).decode()
            images.append('<figure><img loading="lazy" src="data:image/png;base64,' + uri + '" alt="' + e(name) + '"><figcaption>' + e(name) + '</figcaption></figure>')
    bars = []
    for f in fixtures:
        for name in ('linear', 'linear-shade'):
            t = f['treatments'][name]; v = t['mean_abs_rgb_difference']
            label = f['subject'] + ' / occlusion ' + str(int(f['occlusion'])) + ' / ' + name + ' vs ' + t['comparison_baseline']
            bars.append('<div class="bar"><span>' + e(label) + '</span><i style="width:' + str(min(100, v * 4)) + '%"></i><b>' + f'{v:.3f}' + '</b></div>')
    rows = []
    for name, c in compact['current_reduced'].items():
        r = c['resources']
        vals = (name, c['status'], r.get('reason', '—'), len(c['scenes']), sum(s['mask_present'] for s in c['scenes']), r.get('peak_rss_bytes', '—'), r.get('minimum_available_bytes', '—'), r.get('swap_out_delta_bytes', '—'))
        rows.append('<tr>' + ''.join('<td>' + e(str(v)) + '</td>' for v in vals) + '</tr>')
    early = compact['early_prototype']
    count = sum(len(c['scenes']) for c in early.values())
    masks = sum(s['mask_present'] for c in early.values() for s in c['scenes'])
    equal = sum(t['annotation_equal'] is True and t['masks_equal'] is True for f in fixtures for t in f['treatments'].values())
    dev = e(json.dumps(development, indent=2))
    retry = e(json.dumps(compact['retry_once'], indent=2))
    page = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Camera and environments evidence</title><style>body{font:16px/1.5 system-ui;max-width:1100px;margin:auto;padding:2rem;color:#25313a;background:#f5f6f3}section{background:white;padding:1.5rem;margin:1rem 0;border-radius:12px}img{max-width:100%;height:auto}figure{margin:1rem 0}.bar{display:grid;grid-template-columns:290px 1fr 55px;gap:.5rem;font-size:.8rem}.bar i{background:#327b83;height:1rem;min-width:1px}table{border-collapse:collapse;font-size:.8rem}td,th{padding:.5rem;border-bottom:1px solid #ddd;text-align:left}.scroll{overflow:auto}pre{white-space:pre-wrap}</style><body><h1>Camera and environments · evidence snapshot</h1><section><h2>Interpretation</h2><p>The paired 2D screen covers FIXTURES fixtures and IMAGES images; EQUAL treatment records report equal masks and annotations. Linear compositing visibly changes translucent occluder color; shade darkens the scene. Effects are qualitative and opt-in. Generic RGBA is a substitute in the pad family.</p><p>Early 3D views are an older prototype snapshot. Current camera and environment results remain unqualified. No real-image reference or model evaluation supports a realism or detector-performance claim. Sharp geometry masks may differ from blurred RGB boundaries.</p></section><section><h2>2D differences</h2><p>Mean absolute RGB difference in 8-bit units per channel. Linear compares with legacy; linear+shade compares with linear. Bars cap at 25 units.</p>BARS</section><section><h2>Paired views and crops</h2>VIEWS</section><section><h2>Older 3D prototype</h2><p>EARLY result records and MASKS mask files. One target, ground and pose across the three views; this is not a viewpoint distribution or proof of mask correctness. Plain wall wedges and the outdoor strip did not establish convincing scene context.</p>IMAGEPROTOTYPE</section><section><h2>Current reduced 3D</h2><p>Counts are result JSON and mask files present, not annotation validation. Resource values are local guard evidence, not benchmark comparisons. Missing means no progress record.</p><div class="scroll"><table><tr><th>Condition</th><th>Status</th><th>Reason</th><th>Results</th><th>Mask files</th><th>Peak RSS bytes</th><th>Min available bytes</th><th>Swap-out delta bytes</th></tr>ROWS</table></div><h3>Single guarded retry</h3><pre>RETRY</pre><h3>Earlier development attempt</h3><p>Accepted row tilts below are partial results, not a distribution or camera coverage evidence.</p><pre>DEV</pre></section><section><h2>Limits and next evidence</h2><p>The 2D screen uses one background seed. Inspect native masks and edges and test additional backgrounds, scales and translucent references. Obtain completed current-revision scenes before evaluating geometry, motion or distortion; vary viewpoints and inspect mask overlays, clipping and rejection. No performance or default-promotion conclusion follows from these partial runs.</p></section></body></html>'''
    replacements = {'FIXTURES': str(len(fixtures)), 'IMAGES': str(summary['rendered_images']), 'EQUAL': str(equal), 'BARS': ''.join(bars), 'VIEWS': ''.join(images[:6]), 'IMAGEPROTOTYPE': ''.join(images[6:]), 'EARLY': str(count), 'MASKS': str(masks), 'ROWS': ''.join(rows), 'DEV': dev, 'RETRY': retry}
    for key in ('FIXTURES', 'IMAGES', 'EQUAL', 'EARLY', 'MASKS', 'ROWS', 'DEV', 'RETRY', 'BARS', 'VIEWS', 'IMAGEPROTOTYPE'):
        page = page.replace(key, replacements[key])
    (out / 'index.html').write_text(page)
    (out / 'README.md').write_text('# Camera and environments evidence\n\nOpen [the standalone report](index.html) locally. It embeds the available reviewed sheets and needs no network. `compact.json` contains selected measurements and statuses without local absolute paths.\n\nReproduce from the repository root when the ignored raw experiment bundle is available:\n\n```sh\npython3 scripts/report_camera_environments.py --input outputs/experiments/realism-camera-round --output docs/experiments/camera-environments-v1\n```\n\nMissing reduced cases are marked missing. Old smoke imagery is an earlier prototype; the current 3D work is unqualified. The small 2D screen and partial 3D runs do not support real-reference, model-performance, benchmark or promotion claims. Raw experiment outputs remain ignored.\n')

if __name__ == '__main__':
    main()
