#!/usr/bin/env python3
"""Create/refresh a portable, evidence-bounded surface integration report.

Example: python3 scripts/report_surface_integration.py --cpu-study outputs/experiments/surface-integration/cpu-smoke --output outputs/experiments/surface-integration/report-app
Inputs are optional; missing inputs remain visible as gaps. Requires Pillow and Node.
"""
import argparse, base64, hashlib, html, io, json, os, re, shutil, statistics, subprocess
from pathlib import Path
from PIL import Image

NODE = os.environ.get('CODEX_NODE') or str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node')
if not Path(NODE).exists(): NODE = shutil.which('node') or 'node'
PLUGIN = Path(os.environ.get('DATA_ANALYTICS_PLUGIN_ROOT') or Path.home()/'.codex/plugins/cache/openai-curated-remote/data-analytics/1.1.0-exp-baseline')

def read(path, default=None):
    try: return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError): return default

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def picture(path, crop=False, center=None):
    if not path.is_file(): return None
    with Image.open(path) as image:
        image = image.convert('RGB')
        if crop:
            w,h=image.size; side=min(w,h,256); cx,cy=center or (w//2,h//2); left=max(0,min(w-side,int(cx-side/2))); top=max(0,min(h-side,int(cy-side/2)))
            image=image.crop((left,top,left+side,top+side))
        else: image.thumbnail((640,640), Image.Resampling.LANCZOS)
        out=io.BytesIO(); image.save(out,format='PNG' if crop else 'JPEG', **({'optimize':True} if crop else {'quality':84,'optimize':True}))
    return ('data:image/png;base64,' if crop else 'data:image/jpeg;base64,')+base64.b64encode(out.getvalue()).decode()

def mask_center(path):
    try:
        import numpy as np
        with np.load(path, allow_pickle=False) as arrays:
            masks=arrays['visible']; sizes=masks.reshape((len(masks),-1)).sum(axis=1)
            if len(sizes) and sizes.max():
                ys,xs=np.nonzero(masks[int(sizes.argmax())]); return ((int(xs.min())+int(xs.max()))//2,(int(ys.min())+int(ys.max()))//2)
    except (ImportError, OSError, ValueError, KeyError): pass
    return None

def file_ref(p, root):
    try: return p.relative_to(root).as_posix()
    except ValueError: return p.name

def collect_cell(root, label):
    study=read(root/'study.json',{}); execution=read(root/'execution.json',{}); runs=read(root/'runs.json',[])
    if not runs:
        p=read(root/'progress.json'); runs=[p] if p else []
    scenes=[]
    for f in sorted((root/'scenes').glob('*/result.json')):
        d=read(f,{}) or {}; job=d.get('job',{}); treatment=job.get('treatment',{}) or {}; image=f.parent/'rgb.png'
        scenes.append({'id':job.get('id',f.parent.name),'status':d.get('status'),'treatment':treatment.get('id'),'scene_index':job.get('scene_index'), 'reference_scene_index':job.get('reference_scene_index'), 'case':job.get('case'), 'quality':job.get('quality'), 'attempts':len(d.get('attempts',[])), 'rejection_reasons':sorted({a['rejection'] for a in d.get('attempts',[]) if a.get('rejection')}), 'rgb_seconds':d.get('rgb_render_seconds'), 'serial_seconds':d.get('accepted_output_seconds'), 'mask_sha256':d.get('files',{}).get('masks.npz'), 'image_sha256':d.get('files',{}).get('rgb.png'), 'source':file_ref(f,root), 'image_source':file_ref(image,root), 'image':None, 'crop':None})
    # Select a consistent intent and named controls, never the first N files.
    pair_specs=[('Shared-core wear','core','wear','fast','fast',[0,1,2]),('Ground mapping and contextual shade','uv-scale','context','fast','fast',[0]),('Reflection-sensitive wear','glint-clean','glint','fast','fast',[1]),('Mixed-light wear','night-clean','night','fast','fast',[2]),('Close-up wear','close-clean','close-wear','fast','fast',[1]),('Integrated context','wear','integration','fast','fast',[0,1,2]),('Core sample quality','core','core','fast','quality',[2]),('Wear sample quality','wear','wear','fast','quality',[2]),('Glint sample quality','glint','glint','fast','quality',[1]),('Night sample quality','night','night','fast','quality',[2]),('Close-up sample quality','close-wear','close-wear','fast','quality',[0])]
    pairs=[]
    for label_pair,left,right,lq,rq,indices in pair_specs:
      for index in indices:
        a=next((s for s in scenes if s['scene_index']==index and s['case']=='ordinary' and s['quality']==lq and s['treatment']==left and s['status']=='accepted'),None)
        b=next((s for s in scenes if s['scene_index']==index and s['case']=='ordinary' and s['quality']==rq and s['treatment']==right and s['status']=='accepted'),None)
        if not a or not b: continue
        center=mask_center(root / Path(a['source']).parent / 'masks.npz')
        for scene in (a,b):
            image=root/scene['image_source']; scene['image']=picture(image)
        pair={'left_crop':picture(root/a['image_source'],True,center),'right_crop':picture(root/b['image_source'],True,center),'label':label_pair,'left':a['id'],'right':b['id'],'scene_index':index,'reference_scene_index':a.get('reference_scene_index'),'crop_center':center,'mask_arrays_equal':None}
        try:
            import numpy as np
            with np.load(root / Path(a['source']).parent / 'masks.npz',allow_pickle=False) as ma, np.load(root / Path(b['source']).parent / 'masks.npz',allow_pickle=False) as mb:
                pair['mask_arrays_equal']=all(key in ma and key in mb and np.array_equal(ma[key],mb[key]) for key in ('full','visible'))
        except (ImportError,OSError,ValueError,KeyError): pass
        pairs.append(pair)
    # Keep diagnostics visible in the CPU smoke when no named pair exists.
    if not pairs:
        for scene in scenes[:4]:
            image=root/scene['image_source']; center=mask_center(root/Path(scene['source']).parent/'masks.npz')
            scene['crop_center']=center; scene['image']=picture(image); scene['crop']=picture(image,True,center)
    rows=[]
    selected_frequency={}
    for run in runs:
        for job_id in run.get('selected_jobs',[]): selected_frequency[job_id]=selected_frequency.get(job_id,0)+1
    for r in runs:
        ids=r.get('selected_jobs',[]); matched=[s for s in scenes if s['id'] in ids and s['status']=='accepted']
        wall=r.get('command_seconds'); unambiguous=bool(ids) and r.get('status') == 'complete' and all(selected_frequency[job_id] == 1 for job_id in ids); accepted=len(matched) if unambiguous else None
        rows.append({'phase':r.get('phase'),'status':r.get('status'), 'selected_count':len(ids), 'accepted_count':accepted, 'command_seconds':wall, 'accepted_per_second':accepted/wall if wall and accepted is not None else None, 'peak_rss_bytes':r.get('peak_rss_bytes'),'gpu_peak_mib':r.get('sampled_peak_gpu_memory_mib'),'guard_reason':r.get('reason'),'workers':r.get('workers')})
    sourcefiles=[p for p in [root/'study.json',root/'execution.json',root/'runs.json',root/'progress.json',root/'surface-origin.json',root/'bundle-origin.json',root/'summary.json',root/'coco-visible.json',root/'coco-full.json',root/'evaluation-visible.json',root/'evaluation-full.json'] if p.is_file()]
    coco={}
    for mode in ('visible','full'):
        file=root/('coco-'+mode+'.json'); payload=read(file)
        if payload: coco[mode]={'images':len(payload.get('images',[])),'annotations':len(payload.get('annotations',[])),'sha256':sha(file)}
    assets=[]
    for ground in study.get('grounds',[]):
        p=ground.get('provenance',{}); assets.append({'asset_id':p.get('asset_id'),'material_id':p.get('material_id'),'provider':p.get('provider'),'source_page':p.get('source_page'),'license':p.get('license'),'license_url':p.get('license_url'),'archive':p.get('archive')})
    return {'label':label,'root':str(root),'study_identity':study.get('identity'), 'planned_jobs':len(study.get('jobs',[])), 'observed_jobs':len(scenes),'accepted_jobs':sum(s['status']=='accepted' for s in scenes), 'resolution':study.get('config',{}).get('resolution') or study.get('contract',{}).get('config',{}).get('resolution'), 'selection':execution.get('selection',{}), 'origin':read(root/'surface-origin.json'), 'runs':rows,'scenes':scenes,'pairs':pairs,'coco':coco,'artwork':study.get('artwork',[]),'assets':assets,'sources':[{'path':file_ref(p,root),'sha256':sha(p)} for p in sourcefiles]}

def collect_2d(root):
    summary=read(root/'summary.json',{}) or {}; records=summary.get('records') or read(root/'records.json',[]) or []
    compact=[]; pictures=[]
    for r in records:
        compact.append({k:r.get(k) for k in ('resolution','repeat','variant','pool','accepted','candidate_attempts','inspection','content_signature','generation_seconds','preparation_seconds','images_per_second','prepared_command_images_per_second','active_images_per_second','resource_peaks','execution','warmup','unique_measured_scene_intents','evaluation','stage_work')})
        if r.get('repeat') != 0 or len(pictures)>=24: continue
        pool=(root / r.get('pool','')).resolve()
        if not pool.is_relative_to(root.resolve()): continue
        samples=pool/'samples.jsonl'
        if not samples.is_file(): continue
        for line in samples.read_text().splitlines()[:2]:
            sample=json.loads(line); image=(pool / sample.get('image_path','')).resolve()
            if not image.is_relative_to(pool) or not image.is_file(): continue
            annotations=sample.get('annotations',[]); bbox=max((a.get('bbox') for a in annotations if a.get('bbox')), key=lambda b: (b[2]-b[0])*(b[3]-b[1]), default=None)
            center=((bbox[0]+bbox[2])//2,(bbox[1]+bbox[3])//2) if bbox else None
            pictures.append({'crop_center':center,'id':f"{r.get('variant')} / {r.get('resolution')} / slot {sample.get('slot')}",'variant':r.get('variant'),'resolution':r.get('resolution'),'slot':sample.get('slot'),'candidate_attempt':sample.get('candidate_attempt'),'source':file_ref(image,root),'sha256':sha(image),'image':picture(image),'crop':picture(image,True,center)})
    sources=[{'path':p.name,'sha256':sha(p)} for p in (root/'summary.json',root/'records.json',root/'provenance.json',root/'matrix.json',root/'reference-pair-check.json',root/'omitted-operation-check.json') if p.is_file()]
    reference=read(root/'reference-pair-check.json')
    if reference: reference={k:reference.get(k) for k in ('status','comparison_count','all_geometry_equal','all_annotations_equal','all_full_visible_masks_equal')}
    omitted=read(root/'omitted-operation-check.json')
    if omitted: omitted={k:omitted.get(k) for k in ('status','paired_comparisons','all_png_bytes_equal','all_full_visible_masks_equal','all_geometry_annotations_equal','paired_gains','median_paired_gains','scope')}
    return {'root':str(root),'status':summary.get('status','partial'),'scope':summary.get('scope'),'samples':summary.get('samples'),'warmups':summary.get('warmups'),'all_content_signatures_equal':summary.get('all_content_signatures_equal'),'limitations':summary.get('limitations',[]),'records':compact,'medians':summary.get('medians',[]),'provenance':{k:v for k,v in (read(root/'provenance.json',{}) or {}).items() if k in ('driver_sha256','matrix_sha256','input_config_sha256','input_sources','execution_policy_sha256','software','note')}, 'reference_pair_check':reference, 'omitted_check':omitted, 'sources':sources,'pictures':pictures}

def sanitize(value):
    """Remove local filesystem locations from a portable, shareable snapshot."""
    if isinstance(value, dict):
        result={}
        for key,item in value.items():
            clean=sanitize(key)
            if clean in result: clean += '#'+hashlib.sha256(key.encode()).hexdigest()[:8]
            result[clean]=sanitize(item)
        return result
    if isinstance(value, list): return [sanitize(v) for v in value]
    if not isinstance(value,str): return value
    if value.startswith('data:image/'): return value
    if value.startswith('../'): return '[local]/'+Path(value).name
    # URLs and source IDs remain intact; absolute local paths are replaced by file labels.
    return re.sub(r'(?<![\w:/])/(?:[^\s<>"\'(),;]+)', lambda m: '[local]/'+Path(m.group()).name, value)

def collect_performance(root):
    root = root.parent if root.is_file() else root
    summary=read(root/'summary.json',{}) or {}; records=summary.get('records') or read(root/'records.json',[]) or []
    rows=[]
    for r in records:
        measured=r.get('measured_command') or {}; warm=r.get('warmup_command') or {}; mp=r.get('measured_probe') or {}; wp=r.get('warmup_probe') or {}
        wall=measured.get('command_seconds'); accepted=r.get('accepted'); valid=isinstance(accepted,int) and isinstance(wall,(int,float)) and wall>0 and measured.get('status')=='complete'
        rows.append({'cell':r.get('cell'),'resolution':r.get('resolution'),'repeat':r.get('repeat'),'variant':r.get('variant'),'identity':r.get('identity'),'source_fingerprints':r.get('source_fingerprints'),'signature':r.get('signature'),'accepted':accepted,'measured_selected':len(measured.get('selected_jobs',[])),'measured_seconds':wall,'images_per_second':accepted/wall if valid else None,'warmup_selected':len(warm.get('selected_jobs',[])),'warmup_seconds':warm.get('command_seconds'),'warmup_probe_seconds':wp.get('command_seconds'),'measured_probe_seconds':mp.get('command_seconds'),'selected_workers':r.get('selected_workers'),'measured_workers':r.get('measured_workers'),'peak_rss_bytes':measured.get('peak_rss_bytes'),'gpu_peak_mib':measured.get('sampled_peak_gpu_memory_mib'),'execution':r.get('execution')})
    pair_groups={}
    for r in rows: pair_groups.setdefault((tuple(r.get('resolution') or ()),r.get('repeat')),[]).append(r)
    paired_signatures_equal=all(len(g)==2 and {r['variant'] for r in g}=={'core','wear'} and bool(g[0]['signature']) and g[0]['signature']==g[1]['signature'] for g in pair_groups.values()) if pair_groups else None
    paired_changes=[]
    for (size,repeat),group in sorted(pair_groups.items()):
        core=next((r for r in group if r['variant']=='core'),None); wear=next((r for r in group if r['variant']=='wear'),None)
        if core and wear and core['images_per_second'] and wear['images_per_second'] is not None:
            paired_changes.append({'resolution':list(size),'repeat':repeat,'core_rate':core['images_per_second'],'wear_rate':wear['images_per_second'],'wear_over_core_change':wear['images_per_second']/core['images_per_second']-1})
    paired_medians=[{'resolution':list(size),'repetitions':sum(tuple(r['resolution'])==size for r in paired_changes),'median_change':statistics.median(r['wear_over_core_change'] for r in paired_changes if tuple(r['resolution'])==size)} for size in sorted({tuple(r['resolution']) for r in paired_changes})]
    groups={}
    for r in rows:
        if r['images_per_second'] is not None: groups.setdefault((tuple(r['resolution']),r['variant']),[]).append(r['images_per_second'])
    medians=[{'resolution':list(size),'variant':variant,'label':f"{variant} / {' × '.join(map(str,size))}",'median_images_per_second':statistics.median(values),'repetitions':len(values)} for (size,variant),values in sorted(groups.items())]
    files=[{'path':p.name,'sha256':sha(p)} for p in (root/'summary.json',root/'records.json',root/'provenance.json',root/'matrix.json') if p.is_file()]
    return {'status':summary.get('status','partial'),'paired_signatures_equal':paired_signatures_equal,'paired_changes':paired_changes,'paired_medians':paired_medians,'checks':summary.get('checks',{}),'limitations':summary.get('limitations',[]),'budget_used_seconds':summary.get('budget_used_seconds'),'records':rows,'medians':medians,'sources':files,'provenance':{k:v for k,v in (read(root/'provenance.json',{}) or {}).items() if k in ('matrix_sha256','driver_sha256','config_sha256','benchmark','timing')}}

def collect_prototype(path):
    source=path/'comparison-summary.json' if path.is_dir() else path
    if not source.is_file(): return None
    raw=read(source,{}) or {}; jobs=raw.get('jobs',[]); rows=[]
    for name in ('base','relief','imported'):
        conditions=[(j.get('conditions') or {}).get(name,{}) for j in jobs]
        run=next((r for r in (raw.get('runs') or {}).get(name,[]) if r.get('status')=='complete' and (r.get('selected_jobs') or r.get('phase')=='smoke')),None)
        rows.append({'condition':name,'planned':len(jobs),'accepted':sum(c.get('status')=='accepted' for c in conditions),'visible_changed_pixels':sum(c['visible_changed_pixels'] for c in conditions) if conditions and all(isinstance(c.get('visible_changed_pixels'),int) for c in conditions) else None,'full_changed_pixels':sum(c['full_changed_pixels'] for c in conditions) if conditions and all(isinstance(c.get('full_changed_pixels'),int) for c in conditions) else None,'command_seconds':(run or {}).get('command_seconds'),'peak_rss_bytes':(run or {}).get('peak_rss_bytes')})
    return {'source':source.name,'sha256':sha(source),'scope':raw.get('scope'),'jobs':jobs,'rows':rows,'remote_r2_status':'unknown; final remote archive was not recovered'}

def load_reviews(path):
    if not path: return []
    files=sorted(path.glob('*.json')) if path.is_dir() else [path]
    result=[]
    for p in files[:50]:
        if not p.is_file(): continue
        entry={'source':p.name,'sha256':sha(p),'content':read(p)}
        sheet=p.with_suffix('.jpg')
        if sheet.is_file(): entry.update(sheet_source=sheet.name,sheet_sha256=sha(sheet),sheet='data:image/jpeg;base64,'+base64.b64encode(sheet.read_bytes()).decode())
        entry['review_images']=[]
        names=list(dict.fromkeys(((entry.get('content') or {}).get('images') or [])+((entry.get('content') or {}).get('evidence') or [])))
        for name in names:
            candidate=(p.parent/name).resolve()
            if candidate.parent!=p.parent.resolve() or not candidate.is_file() or candidate.suffix.lower() not in ('.jpg','.jpeg'): continue
            entry['review_images'].append({'name':candidate.name,'sha256':sha(candidate),'image':'data:image/jpeg;base64,'+base64.b64encode(candidate.read_bytes()).decode()})
        result.append(entry)
    return result

def query(rows, label, files):
    return {'rows':rows,'source':{'label':label,'files':files,'evidenceFlow':[{'title':'Study files','detail':'Rows extracted from the recorded result, execution and run files. Missing records are not zero.'}], 'metricDefinitions':([{'label':'Accepted per command second','definition':'Accepted result files among the selected job IDs divided by the recorded command wall time. Probe runs may select no jobs.','componentIds':['run-evidence']}] if label=='Study command records' else [])},'methods':[{'language':'text','code':('Join selected job IDs to accepted result.json files within each cell; divide matched accepted count by command_seconds. Serial per-output times are separate.' if label=='Study command records' else 'Read per-scene result.json metadata and recorded file hashes.')}]}

JS = r'''import React from "react";
import {EvidenceChart, ReportSection, RichNarrative, useDataApp} from "../../data-app-public.jsx";
import "./report.css";
export function ReportContent(){
 const {snapshot,visible}=useDataApp(); const data=snapshot.surfaceEvidence||{}; const cells=data.cells||[]; const q=snapshot.queries||{};
 const rows=q.runs?.rows||[]; const scenes=q.scenes?.rows||[]; const rates=q.rates2d?.rows||[]; const gpuRates=q.rates3d?.rows||[]; const controlRates=q.rates2dcontrol?.rows||[]; const stageRows=q.stage2d?.rows||[]; const plot2d=q.figure2d?.rows||[]; const plotT4=q.figuret4?.rows||[]; const figures=data.reportFigures||{};
 const retrieval=(data.reviews||[]).find(r=>r.source==='retrieval.json')?.content; const mapReview=(data.reviews||[]).find(r=>r.source==='material-map-diagnostics.json')?.content; const casterReview=(data.reviews||[]).find(r=>r.source==='caster-visibility.json')?.content;
 const intro="## Executive summary\n\n"+(data.gaps?.length ? "This report is **incomplete**; the missing evidence is listed below. " : "The recorded study evidence is shown below. ")+" A CPU smoke run is a local diagnostic, not a general performance estimate.\n\nThe design targets shared-core intents across 2D and 3D; specialized recipes have distinct stated goals. Completed evidence below determines what was actually paired. Synthetic appearance evidence does not establish real-image or detector benefit.";
 return <article className="surface-report"><header><h1>Surface integration study</h1><p className="kicker">Engineering evidence · {snapshot.buildStatus==='complete'?'complete':'partial'}, source-backed</p></header>
 <RichNarrative id="overview" value={intro} />
 {figures['qualification-coverage-resources.png'] && <ReportSection id="figure-coverage" title="Qualification coverage and sampled resources" queryId="runs" sourceRows={rows} showHeading={false}><figure data-reviewed-rows><img className="evidence-figure" src={figures['qualification-coverage-resources.png']} alt="Qualification result counts and render-command sampled resource peaks"/><RichNarrative id="figure-coverage:caption" value="Qualification result counts include diagnostics. Peak RSS and GPU memory are sampled separately for one render command per cell; probes are separate." /></figure></ReportSection>}
 {figures['2d-throughput.png'] && <ReportSection id="figure-2d" title="2D generation throughput" queryId="figure2d" sourceRows={plot2d} showHeading={false}><figure data-reviewed-rows><img className="evidence-figure" src={figures['2d-throughput.png']} alt="2D generation throughput with per-repetition dots and medians"/><RichNarrative id="figure-2d:caption" value="Each dot is one repetition; lines mark medians. Rates use accepted images per generation wall second. The two studies are separate; stress has one repetition and is omitted." /></figure></ReportSection>}
 {figures['t4-throughput.png'] && <ReportSection id="figure-t4" title="Isolated T4 measured-command throughput" queryId="figuret4" sourceRows={plotT4} showHeading={false}><figure data-reviewed-rows><img className="evidence-figure" src={figures['t4-throughput.png']} alt="Isolated T4 measured-command throughput with per-repetition dots and medians"/><RichNarrative id="figure-t4:caption" value="Each dot is one measured command of 20 accepted images; warmups and probes are separate. These host-specific rates are not a cross-host comparison." /></figure></ReportSection>}

 <ReportSection id="run-evidence" title="Execution and coverage" queryId="runs" sourceRows={rows} showHeading={false}>
 <RichNarrative id="run-copy" value={'## Execution and coverage\n\nCommand throughput uses accepted selected outputs divided by the same command wall time. Serial output timing and render timing below are separate measurements; do not compare CPU and GPU across hosts as a causal speed ratio.'}/>
 <div className="table-wrap" data-reviewed-rows><table><thead><tr><th>Cell / phase</th><th>Status</th><th>Accepted / selected</th><th>Command wall</th><th>Accepted / s</th><th>Peak RSS</th><th>Peak GPU</th></tr></thead><tbody>{rows.map((r,i)=><tr key={i}><td>{r.cell} / {r.phase}</td><td>{r.status}</td><td>{r.accepted_count==null?'unknown':r.accepted_count} / {r.selected_count}</td><td>{r.command_seconds==null?'—':r.command_seconds.toFixed(2)+' s'}</td><td>{r.accepted_per_second==null?'—':r.accepted_per_second.toFixed(3)}</td><td>{r.peak_rss_bytes==null?'—':(r.peak_rss_bytes/1073741824).toFixed(2)+' GiB'}</td><td>{r.gpu_peak_mib==null?'—':r.gpu_peak_mib+' MiB'}</td></tr>)}</tbody></table></div></ReportSection>
 {(data.threeD||[]).filter(x=>x.pair_check).map((x,i)=><p key={i}>Qualification audit: {x.pair_check.comparisons} matched fast/fast pairs checked; full and visible masks {x.pair_check.all_full_visible_masks_equal?'matched':'did not all match'} and geometry {x.pair_check.all_geometry_equal?'matched':'did not all match'}. Same-wear fast/quality comparisons isolate sampling; mixed-treatment fast/quality views do not isolate wear.</p>)}
 <ReportSection id="scene-evidence" title="Paired visual evidence" queryId="scenes" sourceRows={scenes} showHeading={false}><RichNarrative id="scene-copy" value={'## Paired visual evidence\n\nImages are grouped by cell and scene intent; treatment IDs and source IDs remain visible. Full frames are downsampled for inspection. Native crops show unresized 256 × 256 pixels (or the largest square available). Each 3D pair uses the same crop coordinates, centered on the largest visible object in its control when readable; otherwise it uses the frame center.'}/>
 {cells.map(c=><section key={c.label}><h3>{c.label}</h3><p>{c.accepted_jobs} accepted result files / {c.planned_jobs} planned jobs · resolution {c.resolution?.join(' × ')||'unknown'}</p>{c.coco?.visible && <p>Visible COCO: {c.coco.visible.images} images and {c.coco.visible.annotations} annotations. Full-mask COCO: {c.coco.full?.images} images and {c.coco.full?.annotations} annotations.</p>}{c.scenes.some(s=>s.status==='rejected') && <ul>{c.scenes.filter(s=>s.status==='rejected').map(s=><li key={s.id}>{s.id}: rejected after {s.attempts} attempts; {s.rejection_reasons.join(', ')||'reason not recorded'}.</li>)}</ul>}{(c.pairs||[]).length ? c.pairs.map(p=>{const a=c.scenes.find(s=>s.id===p.left),b=c.scenes.find(s=>s.id===p.right); return <figure className="comparison" key={p.left}><figcaption><strong>{p.label}</strong><br/><small>Scene {p.scene_index} · reference intent {p.reference_scene_index}</small><br/><small>Full and visible mask arrays: {p.mask_arrays_equal===null?'not checked':p.mask_arrays_equal?'equal':'different'}; compare only within the stated recipe goals.</small></figcaption><div className="comparison-grid">{[a,b].map((s,index)=><div key={s.id}><strong>{s.id}</strong><div className="pair"><img src={s.image} alt={'Full frame '+s.id}/><img src={index===0?p.left_crop:p.right_crop} alt={'Native crop '+s.id}/></div><small>{s.source} · full frame / native crop · mask SHA-256 {s.mask_sha256||'unavailable'}</small></div>)}</div></figure>}) : <div className="gallery">{c.scenes.filter(s=>s.image).map(s=><figure key={s.id}><figcaption><strong>{s.id}</strong></figcaption><div className="pair"><img src={s.image} alt={'Full frame '+s.id}/><img src={s.crop} alt={'Native crop '+s.id}/></div><small>{s.source}</small></figure>)}</div>}</section>)}</ReportSection>
 {data.twoD && <section><h2>2D paired study</h2><p>Generation throughput is accepted images divided by generation wall time; preparation and active pipeline rates have different denominators. Compare matched resolution, repetition and variant within this host. Stress has one repetition per resolution; the other displayed variants have three. Small differences are observations, not demonstrated speedups. Pristine uses the same SurfaceWear operation at zero severity, so these measurements compare severity within a shared pipeline; they do not measure the cost of enabling wear versus omitting the operation. A no-op fast path and source-size filtering are future optimization candidates requiring measurement.</p><p>{data.twoD.records.reduce((n,r)=>n+(r.accepted||0),0)} accepted measured outputs across {data.twoD.records.length} cells; {data.twoD.records.reduce((n,r)=>n+(r.warmup?.accepted||0),0)} separate warmup outputs.</p>{data.twoD.reference_pair_check && <p>Reference pairing: {data.twoD.reference_pair_check.comparison_count} original scene intents checked; geometry {data.twoD.reference_pair_check.all_geometry_equal?'matched':'did not all match'}, annotations {data.twoD.reference_pair_check.all_annotations_equal?'matched':'did not all match'}, and full/visible masks {data.twoD.reference_pair_check.all_full_visible_masks_equal?'matched':'did not all match'}. See source details for the recorded check.</p>}{rates.length>0 && <EvidenceChart id="two-d-rates" queryId="rates2d" title="2D generation throughput by resolution and variant" spec={{type:"horizontalBar",x:"label",y:"median_images_per_second",xLabel:"Variant and resolution",yLabel:"Accepted images / generation second"}} rows={rates} sourceRows={rates} height={Math.max(300,rates.length*38)} />}<div className="table-wrap"><table><thead><tr><th>Resolution / repeat</th><th>Variant</th><th>Accepted / attempts</th><th>Generation seconds</th><th>Images / s</th></tr></thead><tbody>{(data.twoD.records||[]).map((r,i)=><tr key={i}><td>{r.resolution?.join(' × ')} / {r.repeat}</td><td>{r.variant==='pristine'?'pristine (zero-severity wear)':r.variant}</td><td>{r.accepted} / {r.candidate_attempts}</td><td>{r.generation_seconds?.toFixed(2)}</td><td>{r.images_per_second?.toFixed(3)}</td></tr>)}</tbody></table></div><div className="gallery">{(data.twoD.pictures||[]).map(p=><figure key={p.id}><figcaption>{p.id}<br/><small>{p.source} · SHA-256 {p.sha256}</small></figcaption><div className="pair"><img src={p.image} alt={'Full frame '+p.id}/><img src={p.crop} alt={'Native crop '+p.id}/></div></figure>)}</div></section>}
 {data.twoD?.stage_medians?.length>0 && <ReportSection id="stage-work" title="Recorded 2D stage work" queryId="stage2d" sourceRows={stageRows} showHeading={false}><RichNarrative id="stage-work-copy" value={'## Recorded 2D stage work\n\nEach value is the median across repetitions of captured stage total nanoseconds divided by accepted images, converted to worker milliseconds per accepted image. Captured work can include rejected attempts. Five workers execute concurrently, so these values are not wall-clock latency shares; stages can overlap and must not be added to their parent scene-render total. Only selected stages are shown.'}/><div className="table-wrap" data-reviewed-rows><table><thead><tr><th>Resolution</th><th>Variant</th><th>Stage</th><th>Repetitions</th><th>Median worker ms / accepted image</th></tr></thead><tbody>{data.twoD.stage_medians.map((r,i)=><tr key={i}><td>{r.resolution.join(' × ')}</td><td>{r.variant==='pristine'?'zero-severity wear':r.variant}</td><td>{r.stage}</td><td>{r.repetitions}</td><td>{r.median_worker_ms_per_accepted.toFixed(2)}</td></tr>)}</tbody></table></div></ReportSection>}
 {data.twoDControl && <section><h2>Separate 2D omitted-effect control</h2><p>This separate run compares a truly omitted SurfaceWear operation with a zero-severity operation. It has its own warmups, repetitions and measured generation wall times; its rows and medians are not pooled with the original 2D study. Both variants retain common neutral lighting and premultiplied resampling; omitted wear does not mean every effect is off.</p>{data.twoDControl.omitted_check && <p>Recorded pair checks cover {data.twoDControl.omitted_check.paired_comparisons} images: PNG bytes {data.twoDControl.omitted_check.all_png_bytes_equal?'matched':'did not all match'}, full/visible masks {data.twoDControl.omitted_check.all_full_visible_masks_equal?'matched':'did not all match'}, and geometry and annotations {data.twoDControl.omitted_check.all_geometry_annotations_equal?'matched':'did not all match'}. Review the source record for operation traces and individual comparisons.</p>}{(data.twoDControl.paired_medians||[]).map(m=><p key={m.resolution.join('x')}>{m.resolution.join(' × ')}: median of {m.repetitions} paired omitted/zero-severity throughput ratios minus one = {(m.median_gain*100).toFixed(2)}%. Individual paired results are shown below; small samples may be noisy.</p>)}<p>{data.twoDControl.records.reduce((n,r)=>n+(r.accepted||0),0)} accepted measured outputs across {data.twoDControl.records.length} cells; {data.twoDControl.records.reduce((n,r)=>n+(r.warmup?.accepted||0),0)} separate warmup outputs.</p>{data.twoDControl.status!=='complete' && <p>Control evidence is incomplete: {data.twoDControl.status}.</p>}{controlRates.length>0 && <EvidenceChart id="two-d-control-rates" queryId="rates2dcontrol" title="2D omitted-effect control throughput" spec={{type:"horizontalBar",x:"label",y:"median_images_per_second",yLabel:"Accepted images / generation second"}} rows={controlRates} sourceRows={controlRates} height={Math.max(300,controlRates.length*38)} />}<div className="table-wrap" data-reviewed-rows><table><thead><tr><th>Resolution / repeat / variant</th><th>Accepted / attempts</th><th>Generation seconds</th><th>Images / s</th></tr></thead><tbody>{data.twoDControl.records.map((r,i)=><tr key={i}><td>{r.resolution?.join(' × ')} / {r.repeat} / {r.variant==='pristine'?'pristine (zero-severity wear)':r.variant}</td><td>{r.accepted} / {r.candidate_attempts}</td><td>{r.generation_seconds?.toFixed(2)}</td><td>{r.images_per_second?.toFixed(3)}</td></tr>)}</tbody></table></div><div className="table-wrap"><table><thead><tr><th>Resolution / repeat</th><th>Omitted / s</th><th>Zero-severity / s</th><th>Paired change</th></tr></thead><tbody>{(data.twoDControl.paired_gains||[]).map((r,i)=><tr key={i}><td>{r.resolution.join(' × ')} / {r.repeat}</td><td>{r.omitted_rate.toFixed(3)}</td><td>{r.zero_rate.toFixed(3)}</td><td>{(r.gain*100).toFixed(2)}%</td></tr>)}</tbody></table></div><div className="gallery">{(data.twoDControl.pictures||[]).map(p=><figure key={p.id}><figcaption>{p.id}<br/><small>{p.source} · SHA-256 {p.sha256}</small></figcaption><div className="pair"><img src={p.image} alt={'Full frame '+p.id}/><img src={p.crop} alt={'Native crop '+p.id}/></div></figure>)}</div></section>}
 {data.performance && <section><h2>T4 performance confirmation</h2><p>Rates divide accepted images by the measured render-command wall time. Warmup and both probe commands are recorded separately. These T4 measurements and local 2D/CPU observations are environment-specific; do not infer a causal speed ratio across hosts. The isolated summary and its embedded per-cell resource records were recovered, but full remote archives from the last phase were lost when the allocation was reclaimed. The recorded budget total is a lower bound; conservative reservations may make the final charge higher.</p><p>Recorded lower-bound budget: {data.performance.budget_used_seconds==null?'unavailable':data.performance.budget_used_seconds.toFixed(2)+' s'}. Core denotes the 3D pristine material recipe, distinct from the 2D zero-severity SurfaceWear operation. Paired measured signatures: {data.performance.paired_signatures_equal===true?'equal':data.performance.paired_signatures_equal===false?'not all equal':'unavailable'}. The earlier pass overlapped archive compression and transfer and is excluded.</p>{retrieval?.budget && <p>The conservative post-summary upper bound is {retrieval.budget.conservative_post_summary_upper_bound_seconds?.toFixed(2)} s, based on bounded queued allowances; it is not measured final use.</p>}{(data.performance.paired_medians||[]).map(m=><p key={m.resolution.join('x')}>{m.resolution.join(' × ')}: median of {m.repetitions} per-repetition wear/core rate changes {(100*m.median_change).toFixed(2)}%. This is the median of paired changes, distinct from the ratio of the separate median rates.</p>)}{data.performance.status!=='complete' && <p>Performance evidence is incomplete: {data.performance.status}.</p>}{gpuRates.length>0 && <EvidenceChart id="three-d-rates" queryId="rates3d" title="T4 measured-command throughput" spec={{type:"horizontalBar",x:"label",y:"median_images_per_second",yLabel:"Accepted images / measured command second"}} rows={gpuRates} sourceRows={gpuRates} height={Math.max(300,gpuRates.length*38)} />}<div className="table-wrap" data-reviewed-rows><table><thead><tr><th>Resolution / repeat / variant</th><th>Accepted / selected</th><th>Measured command</th><th>Images / s</th><th>Warmup count / seconds</th><th>Warmup / measured probes</th><th>Workers</th><th>Peak RSS / GPU</th></tr></thead><tbody>{data.performance.records.map((r,i)=><tr key={i}><td>{r.resolution?.join(' × ')} / {r.repeat} / {r.variant==='pristine'?'pristine (zero-severity wear)':r.variant}</td><td>{r.accepted} / {r.measured_selected}</td><td>{r.measured_seconds?.toFixed(2)} s</td><td>{r.images_per_second?.toFixed(3)}</td><td>{r.warmup_selected} / {r.warmup_seconds?.toFixed(2)} s</td><td>{r.warmup_probe_seconds?.toFixed(2)} / {r.measured_probe_seconds?.toFixed(2)} s</td><td>{r.measured_workers}</td><td>{r.peak_rss_bytes==null?'—':(r.peak_rss_bytes/1073741824).toFixed(2)+' GiB'} / {r.gpu_peak_mib==null?'—':r.gpu_peak_mib+' MiB'}</td></tr>)}</tbody></table></div></section>}
 {data.prototype && <section><h2>Local prototype comparison</h2><p>{data.prototype.scope}. This is exploratory CPU evidence, not T4 performance. Remote T4 R2 status remains unknown because the final archive was not recovered.</p><div className="table-wrap" data-reviewed-rows><table><thead><tr><th>Condition</th><th>Accepted / matched jobs</th><th>Visible / full mask changed pixels</th><th>Command wall</th><th>Peak RSS</th></tr></thead><tbody>{data.prototype.rows.map(r=><tr key={r.condition}><td>{r.condition}</td><td>{r.accepted} / {r.planned}</td><td>{r.visible_changed_pixels==null?'unknown':r.visible_changed_pixels} / {r.full_changed_pixels==null?'unknown':r.full_changed_pixels}</td><td>{r.command_seconds==null?'—':r.command_seconds.toFixed(2)+' s'}</td><td>{r.peak_rss_bytes==null?'—':(r.peak_rss_bytes/1073741824).toFixed(2)+' GiB'}</td></tr>)}</tbody></table></div><p>Source: {data.prototype.source} · SHA-256 {data.prototype.sha256}. Command times are exploratory on one host and include setup; they are not evidence of GPU speed.</p></section>}
 <RichNarrative id="limits" value={'## Selection, review and gaps\n\n'+(data.gaps||[]).map(x=>'- '+x).join('\n')+'\n\nNo single aesthetic score is used. Review judgments and rejected candidates must be read alongside their stated criteria.'}/>
 {(mapReview || casterReview) && <section><h3>Material and caster diagnostics</h3>{mapReview?.maps?.[0] && <p>For the first ordinary wear map, roughness codes range from {mapReview.maps[0].maps.roughness.minimum} to {mapReview.maps[0].maps.roughness.maximum} and height codes from {mapReview.maps[0].maps.height.minimum} to {mapReview.maps[0].maps.height.maximum}. These are image-code ranges, not calibrated roughness or physical relief; they may help explain the modest visible response without generalizing to all maps.</p>}{casterReview && <p>A local 64 × 64, one-sample diagnostic recorded {casterReview.names?.length} casters as camera-invisible through segmentation, full-mask restoration and beauty rendering. It tests visibility properties only; it does not establish the origin of the dark features.</p>}</section>}
 <section><h3>Review records</h3>{(data.reviews||[]).length ? data.reviews.map((r,i)=><div key={i}><h4>{r.content?.review||r.source}</h4>{r.content?.conclusion && <p>{r.content.conclusion}</p>}{r.content?.decision && <p>Decision: {r.content.decision}</p>}{r.content?.verdicts && <ul>{Object.entries(r.content.verdicts).map(([name,verdict])=><li key={name}><strong>{name}:</strong> {typeof verdict==='string'?verdict:(verdict.decision||'')} {typeof verdict==='object'?verdict.observations:''}</li>)}</ul>}{r.content?.findings && <ul>{r.content.findings.map((f,j)=><li key={j}>{typeof f==='string' ? f : <span><strong>{f.title}:</strong> {f.status}</span>}</li>)}</ul>}{r.content?.decisions && <ul>{r.content.decisions.map((d,j)=><li key={j}><strong>{d.pair}:</strong> {d.decision}</li>)}</ul>}{(r.review_images||[]).map(im=><figure className="review-sheet" key={im.name}><figcaption>{im.name} · SHA-256 {im.sha256}</figcaption><img src={im.image} alt={'Independent visual review '+im.name}/></figure>)}{r.sheet && <figure className="review-sheet"><figcaption>Independent review: selected shade examples, including slots 16 and 18 · {r.sheet_source} · SHA-256 {r.sheet_sha256}</figcaption><img src={r.sheet} alt="Selected shade comparison contact sheet" /></figure>}<details><summary>Review evidence · {r.source} · SHA-256 {r.sha256}</summary><pre>{JSON.stringify(r.content,null,2)}</pre></details></div>):<p>Review records are not yet available.</p>}</section>
 <section><h3>Source and audit details</h3>{cells.map(c=><details key={c.label}><summary>{c.label} · study {c.study_identity||'unavailable'}</summary><pre>{JSON.stringify({root:c.root,sources:c.sources,execution:c.selection,origin:c.origin,coco:c.coco,artwork:c.artwork,assets:c.assets},null,2)}</pre></details>)}<details><summary>Other study evidence</summary><pre>{JSON.stringify({threeD:data.threeD,twoD:data.twoD && {...data.twoD,pictures:undefined},twoDControl:data.twoDControl && {...data.twoDControl,pictures:undefined},performance:data.performance,prototype:data.prototype},null,2)}</pre></details></section>
 </article>
}'''
CSS = '''.evidence-figure{display:block;width:100%;height:auto}.surface-report {max-width:1050px;margin:auto;line-height:1.55}.surface-report h1{font-size:clamp(2rem,5vw,3.5rem);line-height:1.1}.surface-report h2{margin-top:2.5rem}.kicker{color:var(--secondary)}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;font-size:.9rem}th,td{border-bottom:1px solid var(--border);padding:.55rem;text-align:left;white-space:nowrap}td:nth-child(n+3),th:nth-child(n+3){text-align:right}.gallery{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:1.3rem}.gallery figure{margin:0;padding:.8rem;border:1px solid var(--border);border-radius:8px}.review-sheet{margin:1rem 0}.review-sheet img{max-width:100%;height:auto}.comparison{margin:1.5rem 0;padding:1rem;border:1px solid var(--border);border-radius:8px}.comparison-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:1rem;margin-top:.8rem}.pair{display:grid;grid-template-columns:1fr 1fr;gap:.4rem;margin:.5rem 0}.pair img{width:100%;height:auto;object-fit:contain;align-self:start}small{overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:.75rem;max-height:30rem;overflow:auto}details{margin:.7rem 0}'''

def write_2d_plot(compact, target):
    """Plot independent 2D study repetitions from compact accepted counts and wall times."""
    import tempfile
    os.environ.setdefault('MPLCONFIGDIR', tempfile.mkdtemp(prefix='surface-report-mpl-'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    evidence=compact['surfaceEvidence']; original=evidence.get('twoD'); control=evidence.get('twoDControl')
    if not original or not control: return None
    fig, axes=plt.subplots(2,2,figsize=(13.2,8.8)); fig.patch.set_facecolor('#ffffff')
    groups=[('pristine','Zero-severity wear'),('moderate','Moderate wear'),('shade','Wear + shared shade')]
    controls=[('omitted','Wear omitted'),('pristine','Zero-severity wear')]
    for row,size in enumerate(((640,640),(1280,1280))):
        allrates=[r['accepted']/r['generation_seconds'] for data in (original,control) for r in data['records'] if tuple(r.get('resolution') or ())==size and r.get('generation_seconds') and r.get('accepted') is not None and r.get('variant')!='stress']
        xmax=max(allrates,default=1)*1.25
        for col,(data,variants,title) in enumerate(((original,groups,'Original 2D severity study'),(control,controls,'Separate omitted-effect control'))):
            ax=axes[row,col]; ax.set_title(f'{title}\n{size[0]} × {size[1]}',loc='left',fontweight='bold',fontsize=11,pad=10)
            for position,(variant,label) in enumerate(variants):
                rows=sorted((r for r in data['records'] if tuple(r.get('resolution') or ())==size and r.get('variant')==variant and r.get('generation_seconds')),key=lambda r:r['repeat'])
                vals=[r['accepted']/r['generation_seconds'] for r in rows]
                if not vals: continue
                offsets=[0] if len(vals)==1 else [(-.14 + .28*i/(len(vals)-1)) for i in range(len(vals))]
                ax.scatter(vals,[position+v for v in offsets],s=34,color='#184e70',zorder=4)
                mid=statistics.median(vals); ax.vlines(mid,position-.24,position+.24,color='#a43b24',linewidth=3,zorder=3)
                ax.text(mid+xmax*.015,position-.27,f'{mid:.3f}',fontsize=9,color='#7e291a',va='bottom')
            ax.set_yticks(range(len(variants)),[v[1] for v in variants]); ax.invert_yaxis();ax.set_xlim(0,xmax)
            ax.grid(axis='x',color='#dce4e9',linewidth=.8); ax.set_axisbelow(True); ax.spines[['top','right','left']].set_visible(False)
            ax.tick_params(axis='y',length=0);ax.set_xlabel('Accepted images / generation wall second',fontsize=10)
    fig.suptitle('2D generation throughput within each local study',x=.075,y=.98,ha='left',fontsize=17,fontweight='bold')
    fig.legend(handles=[Line2D([0],[0],marker='o',color='none',markerfacecolor='#184e70',markeredgecolor='#184e70',label='Individual repetition'),Line2D([0],[0],color='#a43b24',linewidth=3,label='Median')],loc='lower left',bbox_to_anchor=(.075,.063),ncol=2,frameon=False)
    fig.text(.075,.028,'Three repetitions per shown variant. Stress is excluded (one repetition). The original pristine row runs zero-severity wear. Separate studies are not pooled.',fontsize=9,color='#364650')
    fig.subplots_adjust(left=.21,right=.97,top=.88,bottom=.16,hspace=.52,wspace=.62)
    dest=target/'2d-throughput.png'; fig.savefig(dest,dpi=150,facecolor='white');plt.close(fig);return dest

def write_t4_plot(compact, target):
    """Plot recovered isolated T4 measured-command rates, without cross-host comparisons."""
    performance=compact['surfaceEvidence'].get('performance')
    if not performance or not performance.get('records'): return None
    import tempfile
    os.environ.setdefault('MPLCONFIGDIR',tempfile.mkdtemp(prefix='surface-report-mpl-'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    fig,axes=plt.subplots(1,2,figsize=(12,5.4)); variants=[('core','3D core (pristine material)'),('wear','3D moderate wear')]
    for ax,size in zip(axes,((640,640),(1280,1280))):
        allrates=[r['accepted']/r['measured_seconds'] for r in performance['records'] if tuple(r.get('resolution') or ())==size and r.get('measured_seconds')]
        xmax=max(allrates,default=1)*1.3
        for position,(variant,label) in enumerate(variants):
            rows=sorted((r for r in performance['records'] if tuple(r.get('resolution') or ())==size and r.get('variant')==variant and r.get('measured_seconds')),key=lambda r:r['repeat'])
            vals=[r['accepted']/r['measured_seconds'] for r in rows]
            if not vals: continue
            offsets=[0] if len(vals)==1 else [-.14+.28*i/(len(vals)-1) for i in range(len(vals))]
            ax.scatter(vals,[position+v for v in offsets],s=38,color='#184e70',zorder=4)
            med=statistics.median(vals); ax.vlines(med,position-.24,position+.24,color='#a43b24',linewidth=3,zorder=3)
            ax.text(med+xmax*.015,position-.27,f'{med:.3f}',fontsize=9,color='#7e291a',va='bottom')
        ax.set_title(f'{size[0]} × {size[1]}',loc='left',fontweight='bold',fontsize=12)
        ax.set_yticks(range(len(variants)),[v[1] for v in variants]);ax.invert_yaxis();ax.set_xlim(0,xmax)
        ax.grid(axis='x',color='#dce4e9',linewidth=.8);ax.set_axisbelow(True);ax.spines[['top','right','left']].set_visible(False);ax.tick_params(axis='y',length=0)
        ax.set_xlabel('Accepted images / measured command second',fontsize=10)
    fig.suptitle('Isolated T4 measured-command throughput',x=.06,y=.98,ha='left',fontsize=17,fontweight='bold')
    fig.legend(handles=[Line2D([0],[0],marker='o',color='none',markerfacecolor='#184e70',markeredgecolor='#184e70',label='Individual repetition'),Line2D([0],[0],color='#a43b24',linewidth=3,label='Median')],loc='lower left',bbox_to_anchor=(.06,.095),ncol=2,frameon=False)
    fig.text(.06,.035,'20 accepted images per measured command; warmup and probes excluded. Three repetitions per variant. Environment-local evidence only.',fontsize=9,color='#364650')
    fig.subplots_adjust(left=.23,right=.97,top=.83,bottom=.27,wspace=.85)
    dest=target/'t4-throughput.png';fig.savefig(dest,dpi=150,facecolor='white');plt.close(fig);return dest

def write_resource_plot(compact, target):
    """Plot retained qualification command peaks and output coverage, not unique intents."""
    cells=[c for c in compact['surfaceEvidence']['cells'] if (c.get('origin') or {}).get('phase') in ('core','quality','reserved')]
    if not cells: return None
    import tempfile
    os.environ.setdefault('MPLCONFIGDIR',tempfile.mkdtemp(prefix='surface-report-mpl-'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    labels=[c['origin']['phase'] for c in cells]; positions=list(range(len(cells))); runs=[next((r for r in c['runs'] if r.get('selected_count')),None) for c in cells]
    fig,axes=plt.subplots(1,2,figsize=(12.5,5.8)); ax=axes[0]
    accepted=[c['accepted_jobs'] for c in cells]; planned=[c['planned_jobs'] for c in cells]
    ax.bar(positions,planned,color='#dce4e9',label='Planned results',width=.6)
    ax.bar(positions,accepted,color='#276789',label='Accepted results',width=.6)
    for i,(a,p) in enumerate(zip(accepted,planned)):ax.text(i,p+max(planned)*.025,f'{a} / {p}',ha='center',fontsize=10)
    ax.set_ylim(0,max(planned)*1.22);ax.set_xticks(positions,labels);ax.set_ylabel('Result files')
    ax.set_title('Qualification coverage',loc='left',fontweight='bold',fontsize=12);ax.legend(loc='upper right',frameon=False,fontsize=9)
    ax=axes[1]; width=.33
    for i,r in enumerate(runs):
        if r and r.get('peak_rss_bytes') is not None:
            value=r['peak_rss_bytes']/1073741824;ax.bar(i-width/2,value,width=width,color='#276789');ax.text(i-width/2,value+.08,f'{value:.2f}',ha='center',fontsize=9)
        if r and r.get('gpu_peak_mib') is not None:
            value=r['gpu_peak_mib']/1024;ax.bar(i+width/2,value,width=width,color='#b65036');ax.text(i+width/2,value+.08,f'{value:.2f}',ha='center',fontsize=9)
    observed=[v for r in runs if r for v in ((r.get('peak_rss_bytes') or 0)/1073741824,(r.get('gpu_peak_mib') or 0)/1024)]
    ax.set_ylim(0,max(observed,default=1)*1.3);ax.set_xticks(positions,labels);ax.set_ylabel('Sampled peak GiB');ax.set_title('Render-command resource peaks',loc='left',fontweight='bold',fontsize=12)
    ax.legend(handles=[Patch(facecolor='#276789',label='Process-tree RSS'),Patch(facecolor='#b65036',label='GPU memory')],loc='upper right',frameon=False,fontsize=9)
    for ax in axes: ax.spines[['top','right']].set_visible(False);ax.grid(axis='y',color='#dce4e9',linewidth=.8);ax.set_axisbelow(True)
    fig.suptitle('Qualification coverage and sampled resources',x=.08,y=.97,ha='left',fontsize=17,fontweight='bold')
    fig.text(.08,.07,'One completed render command per cell; probe time is separate. Counts include diagnostic cases and are not unique scene intents.',fontsize=9,color='#364650')
    fig.text(.08,.035,'Reserved has one rejected diagnostic; sampled peaks are environment-specific observations, not capacity guarantees.',fontsize=9,color='#364650')
    fig.subplots_adjust(left=.09,right=.97,top=.82,bottom=.23,wspace=.36)
    dest=target/'qualification-coverage-resources.png';fig.savefig(dest,dpi=150,facecolor='white');plt.close(fig);return dest

def write_artifacts(target, review_root, asset_root, compact):
    """Write a small evidence index; the interactive report stays in the app output."""
    target.mkdir(parents=True,exist_ok=True)
    (target/'compact.json').write_text(json.dumps(compact,indent=2,allow_nan=False)+'\n')
    selected=[('final-visual.reserved.jpg','review-reserved.jpg','Reserved 3D combinations'),('final-visual.native-crops.jpg','review-native-crops.jpg','Native target crops; some clean/wear views also change sample count and cannot isolate wear'),('targeted-shade.jpg','review-shade.jpg','Selected 2D shade examples; the difference column is amplified eightfold'),('prototypes-final-crops.jpg','review-prototypes.jpg','Exploratory local CPU prototype crops; no T4 verdict')]
    figures=[]
    for name,dest,caption in selected:
        src=review_root/name if review_root and review_root.is_dir() else None
        if src and src.is_file(): shutil.copyfile(src,target/dest); figures.append((dest,caption,sha(src)))
    manifests=[]
    if asset_root:
        for asset in ('rock_07','dry_branches_medium_01'):
            src=asset_root/asset/'manifest.json'
            if src.is_file():
                destination='asset-'+asset+'.json'; (target/destination).write_text(json.dumps(sanitize(read(src)),indent=2)+'\n'); manifests.append((destination,asset))
    plot=write_2d_plot(compact,target)
    resource_plot=write_resource_plot(compact,target)
    evidence=compact['surfaceEvidence']; control=evidence.get('twoDControl') or {}; cells=evidence['cells']; gaps=evidence['gaps']; esc=html.escape
    resource_html='<figure><a href="qualification-coverage-resources.png"><img src="qualification-coverage-resources.png" alt="Qualification coverage and sampled resources"></a><figcaption>Counts include diagnostics; peak RSS and GPU memory are separately sampled observations. Source: compact.json.</figcaption></figure>' if resource_plot else ''
    coverage=''.join(f'<tr><td>{esc(c["label"])}</td><td>{c["accepted_jobs"]} / {c["planned_jobs"]}</td><td>{c.get("coco",{}).get("visible",{}).get("annotations","—")}</td></tr>' for c in cells)
    ratios=''.join(f'<li>{" × ".join(map(str,m["resolution"]))}: median paired omitted versus zero-severity throughput change {100*m["median_gain"]:.2f}% across {m["repetitions"]} repetitions.</li>' for m in control.get('paired_medians',[]))
    plot_html='<figure><a href="2d-throughput.png"><img src="2d-throughput.png" alt="2D generation throughput by resolution and variant"></a><figcaption>Each dot is one repetition; lines mark medians. Accepted images are divided by generation wall seconds. Source: compact.json.</figcaption></figure>' if plot else ''
    t4_plot=write_t4_plot(compact,target)
    t4_plot_html='<figure><a href="t4-throughput.png"><img src="t4-throughput.png" alt="Isolated T4 measured-command throughput"></a><figcaption>Three measured commands per variant and resolution; warmups and probes are separate. Source: compact.json.</figcaption></figure>' if t4_plot else ''
    imgs=''.join(f'<figure><a href="{esc(name)}"><img src="{esc(name)}" alt="{esc(caption)}"></a><figcaption>{esc(caption)} · SHA-256 {digest}</figcaption></figure>' for name,caption,digest in figures)
    assets=''.join(f'<li><a href="{esc(name)}">{esc(label)} CC0 provenance</a></li>' for name,label in manifests)
    paired=''.join(f'<li>{" × ".join(map(str,m["resolution"]))}: median per-repetition wear/core change {100*m["median_change"]:.2f}% across {m["repetitions"]} pairs.</li>' for m in (evidence.get('performance') or {}).get('paired_medians',[]))
    limitations=''.join('<li>'+esc(g)+'</li>' for g in gaps)
    status='Evidence is still incomplete.' if gaps else 'The recorded evidence is summarized here.'
    document=f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Surface integration evidence</title><style>body{{font:16px/1.55 system-ui,sans-serif;max-width:1050px;margin:auto;padding:2rem;color:#152232}}h1{{line-height:1.1}}table{{border-collapse:collapse}}td,th{{text-align:left;border-bottom:1px solid #bac5cf;padding:.5rem}}figure{{margin:2rem 0}}img{{width:100%;height:auto}}figcaption{{font-size:.85rem;overflow-wrap:anywhere}}a{{color:#12538c}}</style></head><body><h1>Surface integration study evidence</h1><p>Compact source-backed evidence page. {status} The full interactive local report contains paired views and the source inspector.</p><p><a href="README.md">Study narrative</a> · <a href="compact.json">Compact reviewed data and source hashes</a></p><h2>Output coverage</h2>{resource_html}<table><tr><th>Cell</th><th>Accepted / planned</th><th>Visible annotations</th></tr>{coverage}</table><p>Reserved diagnostic overlap was rejected after eight attempts below the visible-support floor when present in the data. Complete command status is distinct from accepted outputs.</p><h2>Separate omitted-effect control</h2><p>The original 2D pristine recipe runs zero-severity wear. The separate control compares an omitted operation with that zero-severity operation; both retain neutral lighting and premultiplied resampling. Values are environment-local, with three paired repetitions; one 1280-pixel pair was negative.</p><ul>{ratios}</ul><h2>Measured 2D throughput</h2>{plot_html}<h2>Isolated T4 throughput</h2>{t4_plot_html}<p>The isolated summary and its per-cell resource records were recovered, but the full remote archives from the last phase were lost when the allocation was reclaimed. Its recorded budget total is a lower bound; conservative reservations can make the final charge higher. The earlier timing pass overlapped archive compression and transfer and is excluded.</p><p>These are medians of paired changes, not the ratio of the separate median rates.</p><ul>{paired}</ul><h2>Selection and interpretation</h2><p>Moderate wear remains opt-in, shared shade remains experimental, and the contextual caster recipe is exploratory. Glint and night are specialist scenarios. Dark blocky or pole-like features appear in some caster views; their origin is unverified. A separate diagnostic recorded the caster objects as camera-invisible, which does not establish the source of those features.</p><p>Local relief and imported-mesh prototypes remain exploratory. Their four paired CPU jobs did not alter stored target masks; contact and visibility remain uncertain. The remote T4 prototype outcome was not recovered.</p><h2>Selected reviewed views</h2>{imgs}<h2>Public asset provenance</h2><ul>{assets}</ul><h2>Open evidence gaps</h2><ul>{limitations}</ul><p>Synthetic visual evidence does not establish real-image or detector benefit. Timings across different hosts are not causal speed comparisons.</p></body></html>'''
    (target/'index.html').write_text(document)
    return [p for p in (plot,t4_plot,resource_plot) if p is not None]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--three-d',type=Path,action='append',default=[],help='Study root or cell; repeat to combine separate roots.')
    for name in ('two-d','two-d-control','cpu-study','reviews','prototype','performance'): parser.add_argument('--'+name,type=Path)
    parser.add_argument('--artifact-dir',type=Path,help='Write compact evidence page, figures and public asset provenance.')
    parser.add_argument('--asset-root',type=Path,help='Directory containing public CC0 asset manifests.')
    parser.add_argument('--compact-output',type=Path,help='Write sanitized, image-free compact JSON for an eventual tracked artifact.')
    parser.add_argument('--complete',action='store_true',help='Mark complete only after every required evidence input is present.')
    parser.add_argument('--output',type=Path,required=True); args=parser.parse_args(); out=args.output.resolve(); cells=[]; gaps=[]
    if args.cpu_study and (args.cpu_study/'study.json').is_file(): cells.append(collect_cell(args.cpu_study.resolve(),'Local CPU smoke'))
    else: gaps.append('CPU smoke evidence was not supplied.')
    seen=set()
    for supplied in args.three_d:
        roots=sorted((supplied/'cells').glob('*')) if (supplied/'cells').is_dir() else [supplied]
        for p in roots:
            resolved=p.resolve()
            if resolved in seen or not (resolved/'study.json').is_file(): continue
            seen.add(resolved); cells.append(collect_cell(resolved,'3D / '+resolved.parent.parent.name+' / '+resolved.name))
    if not seen: gaps.append('3D study has no readable study cells yet.')
    phases={((c.get('origin') or {}).get('phase')) for c in cells if c['planned_jobs'] and c['observed_jobs']==c['planned_jobs'] and any(r['status']=='complete' and r['selected_count'] for r in c['runs'])}
    missing_phases=[p for p in ('core','quality','reserved') if p not in phases]
    if missing_phases: gaps.append('Final 3D phases not yet available: '+', '.join(missing_phases)+'.')
    two=collect_2d(args.two_d.resolve()) if args.two_d and args.two_d.is_dir() else read(args.two_d) if args.two_d else None
    if not two or two.get('status') != 'complete': gaps.append('Final 2D summary and paired pools are incomplete or not available.')
    if two:
        selected_stages=('background_synthesis','render.foreground_effects','render.foreground_rotation','render.foreground_resize','render.foreground_warp','render.scene_lighting','image_encode_write','mask_encode')
        stage_rows=[]
        for r in two['records']:
            if r.get('variant') not in ('pristine','moderate') or not r.get('accepted'): continue
            for stage in selected_stages:
                observation=(r.get('stage_work') or {}).get(stage)
                if not observation or not isinstance(observation.get('total_ns'),(int,float)): continue
                stage_rows.append({'resolution':r['resolution'],'variant':r['variant'],'repeat':r['repeat'],'stage':stage,'accepted':r['accepted'],'captured_work_count':observation.get('count'),'total_ns':observation['total_ns'],'worker_ms_per_accepted':observation['total_ns']/r['accepted']/1e6})
        stage_medians=[]
        groups=sorted({(tuple(r['resolution']),r['variant'],r['stage']) for r in stage_rows})
        for size,variant,stage in groups:
            rows=[r for r in stage_rows if tuple(r['resolution'])==size and r['variant']==variant and r['stage']==stage]
            stage_medians.append({'resolution':list(size),'variant':variant,'stage':stage,'repetitions':len(rows),'median_worker_ms_per_accepted':statistics.median(r['worker_ms_per_accepted'] for r in rows)})
        two['stage_rows']=stage_rows;two['stage_medians']=stage_medians

    two_control=collect_2d(args.two_d_control.resolve()) if args.two_d_control and args.two_d_control.is_dir() else None
    if not two_control or two_control.get('status') != 'complete': gaps.append('Separate 2D omitted-effect control is incomplete or unavailable.')
    if two_control:
        paired=[]
        for a in two_control['records']:
            if a.get('variant')!='omitted' or not a.get('images_per_second'): continue
            b=next((r for r in two_control['records'] if r.get('variant')=='pristine' and r.get('repeat')==a.get('repeat') and r.get('resolution')==a.get('resolution')),None)
            if b and b.get('images_per_second'):
                paired.append({'resolution':a['resolution'],'repeat':a['repeat'],'omitted_rate':a['accepted']/a['generation_seconds'],'zero_rate':b['accepted']/b['generation_seconds'],'gain':(a['accepted']/a['generation_seconds'])/(b['accepted']/b['generation_seconds'])-1})
        two_control['paired_gains']=paired
        two_control['paired_medians']=[{'resolution':list(size),'median_gain':statistics.median(r['gain'] for r in paired if tuple(r['resolution'])==size),'repetitions':sum(tuple(r['resolution'])==size for r in paired)} for size in sorted({tuple(r['resolution']) for r in paired})]
    perf_path=args.performance
    performance=collect_performance(perf_path.resolve()) if perf_path and perf_path.exists() else None
    if not performance or performance['status']!='complete': gaps.append('Isolated T4 performance confirmation is incomplete or unavailable; the overlapping timing pass is excluded.')
    elif not performance['records'] or any(r['accepted'] != r['measured_selected'] or r['selected_workers'] != r['measured_workers'] or r['images_per_second'] is None for r in performance['records']) or performance['paired_signatures_equal'] is not True or not all(performance['checks'].get(k) is True for k in ('paired_geometry_acceptance_masks_equal','all_measured_accepted','resolved_worker_counts_match')): gaps.append('T4 performance confirmation has unresolved count, worker, or paired-invariant checks.')
    reviews=load_reviews(args.reviews)
    if not reviews: gaps.append('Independent review, selection and rejection decisions are not available.')
    if not any(r['source']=='final-visual.json' for r in reviews): gaps.append('Independent final visual review is not yet available.')
    proto=collect_prototype(args.prototype.resolve()) if args.prototype and args.prototype.exists() else None
    if not proto: gaps.append('Prototype results or an explicit no-prototype decision are not available.')
    if not any(r['source']=='prototypes-final.json' for r in reviews): gaps.append('Independent local prototype visual review is not yet available.')
    if args.complete and gaps: raise SystemExit('Cannot mark complete while required evidence is missing: '+'; '.join(gaps))
    runrows=[dict(r,cell=c['label']) for c in cells for r in c['runs']]; scenerows=[{k:v for k,v in dict(s,cell=c['label']).items() if k not in ('image','crop')} for c in cells for s in c['scenes']]
    three=[]
    for root in args.three_d:
        if not root.is_dir(): continue
        check_path=root.parent/'qualification-pair-check.json'; check=read(check_path)
        if check: check={k:check.get(k) for k in ('status','comparisons','all_full_visible_masks_equal','all_geometry_equal','cells')}
        three.append({'root':str(root.resolve()),'budget':read(root/'budget.json'),'design':read(root/'design.json'),'pair_check':check,'sources':[{'path':p.name,'sha256':sha(p)} for p in (root/'budget.json',root/'design.json',check_path) if p.is_file()]})
    evidence={'cells':cells,'gaps':gaps,'reviews':reviews,'threeD':three,'twoD':two,'twoDControl':two_control,'performance':performance,'prototype':proto}
    rates=[dict(m,label=f"{'pristine (zero-severity wear)' if m.get('variant')=='pristine' else m.get('variant')} / {' × '.join(map(str,m.get('resolution',[])))}") for m in (two or {}).get('medians',[])]
    perf_rates=(performance or {}).get('medians',[])
    control_rates=[dict(m,label=f"{'pristine (zero-severity wear)' if m.get('variant')=='pristine' else m.get('variant')} / {' × '.join(map(str,m.get('resolution',[])))}") for m in (two_control or {}).get('medians',[])]
    snapshot={'surface':'report','title':'Surface integration study','status':'complete' if args.complete else 'partial','buildStatus':'complete' if args.complete else 'paused','exportPreferences':{'selected':None,'destinations':[]},'surfaceEvidence':evidence,'queries':{'runs':query(runrows,'Study command records',[c['label']+'/'+f['path'] for c in cells for f in c['sources']]),'scenes':query(scenerows,'Per-scene result records',[c['label']+'/'+f['path'] for c in cells for f in c['sources']]),'stage2d':{'rows':(two or {}).get('stage_rows',[]),'source':{'label':'Original 2D recorded stage totals','files':['two-d/'+f['path'] for f in (two or {}).get('sources',[])], 'metricDefinitions':[{'label':'Worker milliseconds per accepted image','definition':'Captured aggregate stage total nanoseconds divided by accepted output count and one million. Includes captured rejected-attempt work; concurrent worker time is not wall-clock latency.','componentIds':['stage-work']}]},'methods':[{'language':'text','code':'For each repetition divide the selected stage total_ns by accepted count and 1,000,000. Report medians by resolution, variant and stage.'}]},'rates2dcontrol':{'rows':control_rates,'source':{'label':'Separate 2D omitted-effect control','files':['two-d-control/'+f['path'] for f in (two_control or {}).get('sources',[])], 'metricDefinitions':[{'label':'Median generation throughput','definition':'Median across repetitions of accepted images divided by generation wall seconds in the separate control study.','componentIds':['two-d-control-rates']}]},'methods':[{'language':'text','code':'Read recorded per-resolution and variant medians from the separate control study summary.'}]},'rates3d':{'rows':perf_rates,'source':{'label':'T4 measured command medians','files':['performance/'+f['path'] for f in (performance or {}).get('sources',[])], 'metricDefinitions':[{'label':'Median measured throughput','definition':'Median across repetitions of accepted outputs divided by measured render-command wall seconds. Warmup and probe commands are separate.','componentIds':['three-d-rates']}]},'methods':[{'language':'text','code':'For each completed record divide accepted by measured command wall seconds; take the median within resolution and variant.'}]},'rates2d':{'rows':rates,'source':{'label':'2D measured generation medians','files':['two-d/'+f['path'] for f in (two or {}).get('sources',[])], 'metricDefinitions':[{'label':'Median generation throughput','definition':'Median across repetitions of accepted images divided by generation wall seconds; preparation is excluded.','componentIds':['two-d-rates']}]},'methods':[{'language':'text','code':'Read recorded per-resolution and variant medians from the 2D study summary.'}]}}}
    snapshot['queries']['figure2d']={'rows':[{'study':name,'resolution':r['resolution'],'variant':r['variant'],'repeat':r['repeat'],'accepted':r['accepted'],'generation_seconds':r['generation_seconds']} for name,study in (('original',two),('omitted-control',two_control)) if study for r in study['records'] if r.get('variant')!='stress'], 'source':{'label':'2D per-repetition generation records','files':['two-d/summary.json','two-d-control/summary.json']},'methods':[{'language':'text','code':'Plot accepted divided by generation_seconds for each repetition; median within each resolution, study and variant.'}]}
    snapshot['queries']['figuret4']={'rows':(performance or {}).get('records',[]),'source':{'label':'Isolated T4 per-repetition commands','files':['performance/summary.json']},'methods':[{'language':'text','code':'Plot accepted divided by measured command wall seconds for each repetition; median within each resolution and variant.'}]}
    snapshot=sanitize(snapshot)
    compact=None
    if args.compact_output or args.artifact_dir:
        compact=json.loads(json.dumps(snapshot))
        compact.pop('queries',None)
        compact_evidence=compact['surfaceEvidence']
        for cell in compact_evidence['cells']:
            for scene in cell['scenes']: scene.pop('image',None); scene.pop('crop',None)
            for pair in cell['pairs']: pair.pop('left_crop',None); pair.pop('right_crop',None)
        if compact_evidence.get('twoD'):
            compact_evidence['twoD'].pop('pictures',None)
            compact_evidence['twoD'].pop('provenance',None)
            for record in compact_evidence['twoD']['records']:
                record['stage_work']={k:v for k,v in (record.get('stage_work') or {}).items() if k in ('background_synthesis','render.foreground_effects','render.foreground_rotation','render.foreground_resize','render.foreground_warp','render.scene_lighting','image_encode_write','mask_encode')}
            check=compact_evidence['twoD'].get('reference_pair_check')
            if check: compact_evidence['twoD']['reference_pair_check']={k:check.get(k) for k in ('status','comparison_count','all_geometry_equal','all_annotations_equal','all_full_visible_masks_equal')}
        if compact_evidence.get('twoDControl'):
            compact_evidence['twoDControl'].pop('pictures',None)
            compact_evidence['twoDControl'].pop('provenance',None)
            for record in compact_evidence['twoDControl']['records']:
                record['stage_work']={k:v for k,v in (record.get('stage_work') or {}).items() if k in ('background_synthesis','render.foreground_effects','render.foreground_rotation','render.foreground_resize','render.foreground_warp','render.scene_lighting','image_encode_write','mask_encode')}
            check=compact_evidence['twoDControl'].get('omitted_check')
            if check: compact_evidence['twoDControl']['omitted_check']={k:check.get(k) for k in ('status','paired_comparisons','all_png_bytes_equal','all_full_visible_masks_equal','all_geometry_annotations_equal','median_paired_gains','scope')}
        if compact_evidence.get('performance'): compact_evidence['performance'].pop('provenance',None)
        compact_evidence['reviews']=[{'source':r['source'],'sha256':r['sha256'],'sheet_source':r.get('sheet_source'),'sheet_sha256':r.get('sheet_sha256'),'review_images':[{k:im[k] for k in ('name','sha256')} for im in r.get('review_images',[])], 'verdicts':(r.get('content') or {}).get('verdicts'), 'retrieval':({k:(r.get('content') or {}).get(k) for k in ('status','qualification','isolated_timing','missing','budget','performance_exclusion','limits')} if r['source']=='retrieval.json' else None), 'findings':[f if isinstance(f,str) else {k:f.get(k) for k in ('priority','title','status')} for f in (r.get('content') or {}).get('findings',[])], 'decision':(r.get('content') or {}).get('decision'), 'decisions':[{k:d.get(k) for k in ('pair','decision')} for d in (r.get('content') or {}).get('decisions',[])]} for r in compact_evidence['reviews']]
        compact_evidence['threeD']=[{k:v for k,v in item.items() if k != 'design'} for item in compact_evidence['threeD']]
        if args.compact_output:
            args.compact_output.parent.mkdir(parents=True,exist_ok=True)
            args.compact_output.write_text(json.dumps(compact,indent=2,allow_nan=False)+'\n')
    if args.artifact_dir:
        generated=write_artifacts(args.artifact_dir,args.reviews,args.asset_root,compact)
        snapshot['surfaceEvidence']['reportFigures']={path.name:'data:image/png;base64,'+base64.b64encode(path.read_bytes()).decode() for path in generated}
    if not out.exists():
        out.parent.mkdir(parents=True,exist_ok=True); tmp=out.parent/(out.name+'-snapshot.json'); tmp.write_text(json.dumps(snapshot,allow_nan=False)); subprocess.run([NODE,str(PLUGIN/'scripts/prepare-data-app.mjs'),'--surface','report','--output',str(out),'--snapshot',str(tmp)],check=True); tmp.unlink()
    else:
        existing=read(out/'src/data.json',{}); snapshot['id']=existing.get('id'); (out/'src/data.json').write_text(json.dumps(snapshot,indent=2,allow_nan=False)+'\n')
    (out/'src/content/report/ReportContent.jsx').write_text(JS+'\n'); (out/'src/content/report/report.css').write_text(CSS+'\n')
    subprocess.run([NODE,str(PLUGIN/'scripts/data-app.mjs'),'build','--project-dir',str(out),'--separate-data'],check=True)
    export=out/'.data-app-offline/exports/surface-integration.html'; subprocess.run([NODE,str(PLUGIN/'scripts/data-app.mjs'),'export-offline','--project-dir',str(out),'--output',str(export)],check=True)
    shutil.copyfile(export,out/'dist/surface-integration.html')
    print('Portable report:',export)
    print('Preview offline copy:',out/'dist/surface-integration.html')
if __name__=='__main__': main()
