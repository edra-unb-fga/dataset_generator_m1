"""Build a portable visual readout from the retrieved camera-study validation."""
import argparse,base64,html,json
from pathlib import Path

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--validation-dir',required=True,type=Path)
p.add_argument('--output-dir',required=True,type=Path)
p.add_argument('--review',type=Path,help='Optional saved human-readable visual assessment')
a=p.parse_args(); report=json.loads((a.validation_dir/'validation.json').read_text());a.output_dir.mkdir(parents=True,exist_ok=True)
e=html.escape
parts=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>L4 camera and environments evidence</title><style>body{font:16px/1.5 system-ui;max-width:1100px;margin:auto;padding:2rem;background:#f3f5f2;color:#1b2a30}section{background:white;border-radius:10px;padding:1.3rem;margin:1rem 0}img{max-width:100%;height:auto}table{border-collapse:collapse}td,th{text-align:left;padding:.4rem;border-bottom:1px solid #ddd}pre{white-space:pre-wrap}</style><body><h1>Camera and environments: L4 evidence</h1><section><p>Current-revision synthetic scenes, with RGB and sharp geometric mask outlines side by side. This is engineering evidence; no real-image calibration or detector-performance claim is made.</p>']
parts.append('<p>Automated validation errors: '+str(len(report['errors']))+'.</p>')
if report['errors']:parts.append('<pre>'+e('\n'.join(report['errors']))+'</pre>')
roundtrip=report.get('annotation_roundtrip',{})
if roundtrip:
 counts=roundtrip.get('counts',{})
 parts.append('<p>COCO mask and box round trips: '+str(counts.get('pixels_exact',0))+'/'+str(counts.get('annotations',0))+' masks and '+str(counts.get('boxes_exact',0))+'/'+str(counts.get('annotations',0))+' boxes matched their source geometry.</p>')
parts.append('</section>')
for phase,value in report['phases'].items():
 parts.append('<section><h2>'+e(phase.title())+'</h2><p>Status: '+e(str(value.get('status')))+'.</p>')
 if value.get('error'):parts.append('<p>'+e(str(value['error']))+'</p>')
 records=value.get('records',[])
 if records:
  parts.append('<table><tr><th>Condition</th><th>Status</th><th>Accepted</th><th>Workers used</th><th>Command time</th></tr>')
  for r in records:
   accepted=sum(x.get('status')=='accepted' for x in r['rows']);t=r.get('seconds');parts.append('<tr><td>'+e(r['cell'])+'</td><td>'+e(str(r.get('status')))+'</td><td>'+str(accepted)+'</td><td>'+e(str(r.get('workers')))+'</td><td>'+ (f'{t:.2f} s' if isinstance(t,(int,float)) else '—')+'</td></tr>')
  parts.append('</table>')
 sheet=a.validation_dir/(phase+'-review.jpg')
 if sheet.exists():parts.append('<p>Each pair shows RGB at left and visible-mask contours at right.</p><img alt="'+e(phase)+' contact sheet" src="data:image/jpeg;base64,'+base64.b64encode(sheet.read_bytes()).decode()+'">')
 parts.append('</section>')
s=report.get('speed',{});parts.append('<section><h2>Ground-mode timing</h2><p>Status: '+e(str(s.get('status','missing'))) + '. Counts exclude separate warmups; times include worker startup and rendering/annotation.</p>')
if s.get('records'):
 parts.append('<table><tr><th>Order</th><th>Ground mode</th><th>Accepted</th><th>Images/s</th></tr>')
 for r in s['records']:
  v=r.get('images_per_second');parts.append('<tr><td>'+str(r['index']+1)+'</td><td>'+e(r['mode'])+'</td><td>'+str(r['accepted'])+'</td><td>'+(f'{v:.3f}' if isinstance(v,(int,float)) else '—')+'</td></tr>')
 parts.append('</table>')
parts.append('<p>These small single-runtime tests do not establish a universal performance default.</p></section>')
sample_file=a.validation_dir/'sample-comparison.json'
sample_sheet=a.validation_dir/'sample-comparison.jpg'
high_quality=a.validation_dir/'high-quality-summary.json'
if sample_file.exists() and sample_sheet.exists() and high_quality.exists():
 samples=json.loads(sample_file.read_text());quality=json.loads(high_quality.read_text())
 report['high_quality']={'sample_comparisons':samples,'annotation_roundtrip':quality['annotation_roundtrip'],'phase_status':quality['phase']['status']}
 parts.append('<section><h2>1280 px: 32 versus 128 samples</h2><p>Paired scenes use the same geometry. All '+str(sum(x['mask_equal'] for x in samples))+' of '+str(len(samples))+' masks matched. Mean per-channel absolute RGB differences range from '+f"{min(x['rgb_mean_abs_8bit'] for x in samples):.3f} to {max(x['rgb_mean_abs_8bit'] for x in samples):.3f}"+' on an 8-bit scale; these figures do not establish perceptual quality or real-image accuracy.</p>')
 parts.append('<img alt="32 and 128 sample paired scenes" src="data:image/jpeg;base64,'+base64.b64encode(sample_sheet.read_bytes()).decode()+'"></section>')
timing_file=a.validation_dir/'2d-timing-summary.json'
if timing_file.exists():
 timing=json.loads(timing_file.read_text())
 report['2d_timing']={key:timing.get(key) for key in ('status','samples_per_cell','warmups_per_cell','repetitions','all_geometry_annotations_and_mask_signatures_equal','medians_images_per_second','median_paired_percent','paired_results','limitations')}
 parts.append('<section><h2>Paired 2D CPU compositing timing</h2><p>Four distinct 640px slots, two warmups per cell and three alternating repetitions. Generation includes pool writes; this is not a quality verdict or a CPU/GPU speed ratio.</p>')
 parts.append('<table><tr><th>Repeat</th><th>Legacy images/s</th><th>Linear images/s</th><th>Change</th></tr>')
 for r in timing.get('paired_results',[]):parts.append(f'<tr><td>{r["repeat"]+1}</td><td>{r["legacy"]:.3f}</td><td>{r["linear"]:.3f}</td><td>{r["linear_vs_legacy_percent"]:+.2f}%</td></tr>')
 parts.append('</table></section>')
review=a.review or a.validation_dir/'review.md'
if review.exists():parts.append('<section><h2>Visual assessment</h2><pre>'+e(review.read_text())+'</pre></section>')
parts.append('</body></html>')
(a.output_dir/'index.html').write_text(''.join(parts));(a.output_dir/'compact.json').write_text(json.dumps(report,indent=2)+'\n')
(a.output_dir/'README.md').write_text('''# L4 camera and environments evidence

Open [the standalone report](index.html). It embeds visual evidence and is usable offline.
`compact.json` contains the automated validation summary; [review.md](review.md) records the visual
assessment and its limits. The report records both an initial and an independent visual review; no real-image/model evaluation was available.
Raw scenes, handoff archives, input bundles and telemetry remain in ignored experiment outputs.

Rebuild from the retrieved and safely extracted raw bundle (replace `$STUDY` with its local path):

```sh
uv run python scripts/analyze_l4_camera_completion.py "$STUDY/retrieved" "$STUDY/validation"
uv run python scripts/validate_camera_coco.py --results "$STUDY/retrieved/results" --validation-dir "$STUDY/validation"
uv run python scripts/report_l4_camera_completion.py --validation-dir "$STUDY/validation" --review docs/experiments/l4-camera-completion-v1/review.md --output-dir docs/experiments/l4-camera-completion-v1
```

The 128-sample comparison can be rebuilt with `scripts/compare_camera_samples.py` using the
32- and 128-sample cell roots; retain the separately generated `high-quality-summary.json`.
The 2D timing table is included when `validation/2d-timing-summary.json` is present; it is the
`result/study/summary.json` member of the separately retrieved 2D archive. Source/input and archive
hashes, failed attempts, the dynamic guard basis and the exact run definitions remain in that evidence.
The captured [study matrices and controllers](../../../experiments/blenderproc/studies/l4-camera-completion/README.md)
provide the exact tested definitions and rerun instructions.
''')
