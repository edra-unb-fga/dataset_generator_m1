from pathlib import Path
from collections import Counter, defaultdict
from hashlib import sha256
import html
import json
import shutil
import sys
from PIL import Image

root=Path.cwd(); study=root/'outputs/experiments/background-breadth-20261106'
out=root/'outputs/experiments/pr89-profile-review/background-breadth-complete'
sys.path.insert(0,str(root/'scripts'))
from collect_2d_review_gallery import collect
from build_scene_review_gallery import build
from review_markdown import render_review_markdown

manifest=collect(study,out)
assets=sorted((root/'backgrounds').rglob('*.jpg'))
asset_hash={p.relative_to(root/'backgrounds').as_posix():sha256(p.read_bytes()).hexdigest() for p in assets}
by_family=defaultdict(set); union=set(); anchors=set(); recipes=Counter(); groups=Counter(); pair={}
for item in manifest['images']:
 sample=item['metadata']['sample']; background=sample['background']; sources=background['sources']
 variant=item['condition']; family=item['family']; slot=sample['slot']
 pair.setdefault((family,slot),{})[variant]=(sample['geometry_signature'],background['recipe_id'],[s['content_hash'] for s in sources])
 if variant=='candidate':
  recipes[background['recipe_id']]+=1
  groups[sources[0]['group']]+=1
  anchors.add(sources[0]['logical_path'].removeprefix('root0/'))
  for s in sources:
   name=s['logical_path'].removeprefix('root0/'); union.add(name);by_family[family].add(name)
 item['engine']='2D '+variant
 item['condition']=sources[0]['group']
 item['label']=f"{family} · {variant} · {slot:03d} · {sources[0]['group']} / {Path(sources[0]['logical_path']).name} · {background['recipe_id']}"
missing=[str(k) for k,v in pair.items() if set(v)!={'baseline','candidate'} or v['baseline']!=v['candidate']]
found_hashes={asset_hash[name] for name in union if name in asset_hash}
forced_roots=[root/'outputs/experiments/background-breadth-20261106-forced',root/'outputs/experiments/background-breadth-20261106-forced-primary']
forced_records=[(i, directory, record) for i,directory in enumerate(forced_roots)
                for record in (json.loads((directory/'records.json').read_text()) if (directory/'records.json').exists() else [])]
forced_names=set()
for forced_index,forced_root,record in forced_records:
 pool=(forced_root/record['pool']).resolve()
 if not pool.is_relative_to(forced_root.resolve()): raise ValueError('Forced pool escapes study root')
 sample=json.loads((pool/'samples.jsonl').read_text().strip())
 source=(pool/sample['image_path']).resolve()
 if not source.is_relative_to(pool): raise ValueError('Forced image escapes pool')
 name=record['background']; forced_names.add(name)
 target=out/'images'/(f"forced-{forced_index}-"+record['pool']+source.suffix)
 shutil.copyfile(source,target)
 profile_name=f"profiles/forced-{forced_index}-"+record['pool']+'.json'
 (out/profile_name).write_text(json.dumps(record['profile'],indent=2)+'\n')
 manifest['images'].append({'path':target.relative_to(out).as_posix(),'engine':'2D forced-direct',
   'family':record['family'],'condition':sample['background']['sources'][0]['group'],
   'label':f"landing-pad · forced direct · {name}",
   'metadata':{'image_sha256':sha256(target.read_bytes()).hexdigest(),'study_record':{k:v for k,v in record.items() if k!='profile'},
               'profile_file':profile_name,'sample':sample}})
all_seen=union|forced_names
all_primary=anchors|forced_names
coverage={'assets_available_paths':len(assets),'assets_available_unique_hashes':len(set(asset_hash.values())),
 'candidate_images':sum(recipes.values()),'source_paths_seen':len(union),'source_unique_hashes_seen':len(found_hashes),
 'anchor_paths_seen':len(anchors),'source_paths_per_family':{k:len(v) for k,v in sorted(by_family.items())},
 'anchor_group_counts':dict(sorted(groups.items())),'recipe_counts':dict(sorted(recipes.items())),
 'forced_direct_paths':sorted(forced_names),'total_paths_seen_with_forced':len(all_seen),'total_primary_paths_with_forced':len(all_primary),
 'unseen_paths':sorted(set(asset_hash)-all_seen),'mismatched_pairs':missing}
(out/'coverage.json').write_text(json.dumps(coverage,indent=2)+'\n')
manifest['title']='Background breadth: matched coherent 2D profiles'
(out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
build(out/'manifest.json',out/'index.html')
page=(out/'index.html').read_text(); needle='<div id="filters"></div>'
intro='<p><a href="summary.html">Study findings and coverage</a> · <a href="catalog.html">Browse all source backgrounds</a> · <a href="../index.html">Earlier profile gallery</a>. Engine selects the baseline, candidate or forced-direct follow-up; Condition selects the first background category. Naturally sampled matched pairs are adjacent. Each image records its sources and recipe in its metadata.</p>'
assert page.count(needle)==1
(out/'index.html').write_text(page.replace(needle,intro+needle))

thumbs=out/'background-thumbnails';thumbs.mkdir()
cards=[]
for p in assets:
 name=p.relative_to(root/'backgrounds').as_posix(); thumb=thumbs/(name.replace('/','--')+'.jpg')
 with Image.open(p) as image:
  image=image.convert('RGB'); image.thumbnail((256,256)); image.save(thumb,quality=78)
 used='naturally used as source' if name in union else 'forced direct follow-up' if name in forced_names else 'not sampled'
 if name in forced_names and name in union: used+='; forced direct too'
 anchor='; primary source' if name in anchors else ''
 cards.append(f'<article><img loading="lazy" src="background-thumbnails/{html.escape(thumb.name,quote=True)}" alt="{html.escape(name,quote=True)}"><h2>{html.escape(name)}</h2><p>{used}{anchor}</p><code>{asset_hash[name][:16]}</code></article>')
catalog='''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Background source catalog</title><style>body{font:16px system-ui;margin:1.5rem}main{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:1em}article{border:1px solid #888;border-radius:.4em;padding:.5em}img{width:100%;aspect-ratio:1;object-fit:contain;background:#222}h2{font-size:.9em;overflow-wrap:anywhere}code{font-size:.7em}</style></head><body><h1>Available background images</h1><p>Source thumbnails; these are not generated scenes. Identical Ground068 content appears in dirt_ground and rocky_ground. Seeing a source in a mixture does not mean it is separately visible in the final image.</p><p><a href="index.html">Generated image gallery</a> · <a href="summary.html">Study summary</a></p><main>'''+''.join(cards)+'</main></body></html>'
(out/'catalog.html').write_text(catalog)
summary=f'''# Background breadth study

The test uses the local 2D catalog of {len(assets)} background paths in ten categories, with {len(set(asset_hash.values()))} unique image hashes. Ground068 appears under two groups with the same content. The configured background root was not reduced: normal recipes select from the complete catalog. No new images were downloaded.

The study requested 82 paired slots for each of landing-pad, landing and manometro: {sum(recipes.values())} candidate images and the same number of baseline images at 640×640, using the same seed and geometry within each pair. The baseline is coherent-varied; the candidate is coherent-balanced. The normal direct, palette, multiband and displaced recipes were eligible. This is not a comparison against realistic-heavy or an independently sampled real-world dataset.

Candidate scenes used **{len(union)} distinct asset paths** ({len(found_hashes)} unique file hashes) as some recipe input and **{len(anchors)}** as the first/anchor source. A palette, mask, or displacement source may contribute without its original appearance being visibly identifiable. Distinct paths seen by family: {dict(sorted((k,len(v)) for k,v in by_family.items()))}. Recipe counts: {dict(sorted(recipes.items()))}. Anchor groups: {dict(sorted(groups.items()))}. There were {len(missing)} pairs whose geometry, recipe, or source hashes differed.

An additional **{len(forced_names)} landing-pad images** explicitly force the paths missing from the natural first-source selection to be direct backgrounds. Together, the natural and forced runs exercise **{len(all_seen)} of {len(assets)} paths**, with **{len(all_primary)}** represented as a first/direct source. Forced examples are labelled and are not natural-frequency evidence.

The group counts describe the first source in each candidate scene, not a balanced or representative ground distribution. Same seed and assets are reused across families. Fresh image content does not establish real-image validity or detection performance. Review shadow, color and motion treatments on different textures as well as the texture itself.

[Generated image gallery](index.html) | [Background source catalog](catalog.html)
'''
(out/'summary.html').write_bytes(render_review_markdown(summary,'Background breadth study'))
(out/'summary.md').write_text(summary)
print(json.dumps(coverage,indent=2))
