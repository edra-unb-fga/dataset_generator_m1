"""Collect previously verified 3D evidence for an unmatched mixture review."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'scripts'))
from build_scene_review_gallery import build


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def collect_natural(reviewed,destination,label,rows):
    evidence=json.loads((reviewed/'evidence.json').read_text())
    if not all(evidence.get(k) for k in ('complete','verified','provenance_verified','stop_confirmed')):
        raise ValueError(f'Natural study verification incomplete: {label}')
    gallery=reviewed/'gallery';manifest=json.loads((gallery/'manifest.json').read_text())
    actual_config=reviewed/'recovered/workspace/natural-config.json'
    profile_file=f'profiles/natural-{label}.json';profile=destination/profile_file
    profile.parent.mkdir(exist_ok=True);shutil.copyfile(actual_config,profile)
    for item in manifest['images']:
        source=(gallery/item['path']).resolve()
        if not source.is_relative_to(gallery.resolve()) or sha(source)!=item['metadata']['image_sha256']:
            raise ValueError('Invalid 3D source image or checksum')
        job=item['metadata']['job']['id'];target=destination/'images'/f'{label}-{job}.png'
        target.parent.mkdir(exist_ok=True);shutil.copyfile(source,target)
        rows.append({'path':target.relative_to(destination).as_posix(),'engine':f'3D natural {label}',
          'family':'landing-pad','condition':item['condition'],'label':f'{label} · natural sample · {job} · {item["condition"]}',
          'metadata':{**item['metadata'],'evidence':evidence,'profile_file':profile_file,'profile_source_sha256':sha(actual_config),
                      'review_selection':'complete natural sample; unmatched between mixtures'}})


def collect_matched(reviewed,destination,rows):
    study=reviewed/'recovered/results'; evidence_file=study/'triplet-evidence.json'
    evidence=json.loads(evidence_file.read_text())
    if evidence.get('status')!='complete':raise ValueError('Matched lighting verification is incomplete')
    for condition in ('open','outdoor-night','indoor'):
      group=next(x for x in evidence['groups'] if x['condition']==condition)
      for triplet in group['triplets']:
       if not triplet.get('preselected_review_case'):continue
       job=triplet['job']
       for treatment in ('baseline','broad','soft'):
        directory=study/f'{condition}-{treatment}'/'scenes'/job
        actual_config=reviewed/'recovered/workspace'/f'{condition}-{treatment}-config.json'
        profile_file=f'profiles/matched-{condition}-{treatment}.json';profile=destination/profile_file
        profile.parent.mkdir(exist_ok=True);shutil.copyfile(actual_config,profile)
        result=json.loads((directory/'result.json').read_text());source=directory/'rgb.png'
        declared=result['files']['rgb.png'];expected=declared.get('sha256') if isinstance(declared,dict) else declared
        if result['status']!='accepted' or sha(source)!=expected:raise ValueError('Matched result verification failed')
        target=destination/'images'/f'matched-{condition}-{treatment}-{job}.png'
        target.parent.mkdir(exist_ok=True);shutil.copyfile(source,target)
        rows.append({'path':target.relative_to(destination).as_posix(),'engine':'3D matched component',
         'family':'landing-pad','condition':condition,'label':f'{condition} · {job} · {treatment} · matched component lighting',
         'metadata':{'result':result,'triplet':triplet,'triplet_evidence_sha256':sha(evidence_file),'image_sha256':expected,
          'profile_file':profile_file,'profile_source_sha256':sha(actual_config),
          'review_selection':'selected matched lighting component; not a matched comparison of mixture probabilities'}})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--balanced',required=True,type=Path);parser.add_argument('--broad',required=True,type=Path)
    parser.add_argument('--matched',required=True,type=Path);parser.add_argument('--output',required=True,type=Path)
    a=parser.parse_args();output=a.output.resolve();output.mkdir(parents=True,exist_ok=False);rows=[]
    collect_natural(a.balanced.resolve(),output,'balanced',rows)
    collect_natural(a.broad.resolve(),output,'broad-material',rows)
    collect_matched(a.matched.resolve(),output,rows)
    manifest={'title':'Existing 3D mixture and matched lighting review','images':rows}
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    build(output/'manifest.json',output/'index.html')
    page=output/'index.html';text=page.read_text();needle='<div id="filters"></div>'
    explanation='<p>The natural examples show two separate seeded draws; scenes are not matched between mixtures. The matched component examples compare lighting treatments on the same scene, not mixture frequencies. Assets were reused, and selected difficult examples do not estimate their prevalence. No new renders were made.</p>'
    if text.count(needle)!=1:raise ValueError('Unexpected gallery template')
    page.write_text(text.replace(needle,explanation+needle));print(f'Wrote {len(rows)} reviewed 3D images')

if __name__=='__main__':main()
