"""BlenderProc entry for isolated context prototypes; no normal pipeline changes."""
import blenderproc as bproc
import argparse
import hashlib
import json
import math
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--renderer', required=True)
parser.add_argument('--study', required=True)
parser.add_argument('--execution', required=True)
parser.add_argument('--prototype-manifest', required=True)
parser.add_argument('--jobs', nargs='+', required=True)
args = parser.parse_args()
renderer = Path(args.renderer).resolve()
source = renderer.read_text()
namespace = {'__file__': str(renderer), '__name__': 'prototype_renderer'}
exec(compile(source.split('parser=argparse.ArgumentParser()')[0], str(renderer), 'exec'), namespace)
from bpy_extras.object_utils import world_to_camera_view
import bpy
from mathutils import Vector


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

study_path = Path(args.study).resolve()
study = json.loads(study_path.read_text())
manifest = json.loads(Path(args.prototype_manifest).read_text())
contract = study['contract']; sealed = contract['prototype']
runtime = {key: study[key] for key in ('config', 'artwork', 'grounds', 'environments', 'execution_catalog')}
if digest(contract) != study['identity'] or digest(study['jobs']) != contract['jobs_sha256'] or digest(runtime) != contract['runtime_sha256']:
    raise RuntimeError('Study seal invalid')
if digest(manifest) != sealed['manifest_sha256'] or sha(__file__) != sealed['entry_sha256'] or sha(__file__) != manifest['entry_sha256'] or sha(renderer) != contract['renderer_script_sha256']:
    raise RuntimeError('Prototype or renderer seal invalid')
for asset in manifest['assets']:
    provenance=json.loads(Path(asset['provenance_manifest']).read_text())
    if sha(asset['path']) != asset['sha256'] or digest(provenance) != asset['provenance_sha256'] or provenance['license'] != 'CC0-1.0' or provenance['derived_glb']['sha256'] != asset['sha256']:
        raise RuntimeError('Asset seal invalid')
execution = json.loads(Path(args.execution).read_text())
if execution['study_identity'] != study['identity'] or digest({k:v for k,v in execution['selection'].items() if k != 'identity'}) != execution['selection']['identity']:
    raise RuntimeError('Execution seal invalid')
namespace['EXECUTION'] = execution['selection']
if bproc.__version__ != '2.8.0' or bpy.app.version != (4,2,1): raise RuntimeError('Pinned BlenderProc 2.8.0 / Blender 4.2.1 required')
if not 1 <= len(args.jobs) <= 4 or len(set(args.jobs)) != len(args.jobs) or not set(args.jobs) <= {j['id'] for j in study['jobs']}:
    raise RuntimeError('Select one to four unique prepared jobs')


def bounds(obj):
    points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    return [[min(v[i] for v in points) for i in range(3)], [max(v[i] for v in points) for i in range(3)]]


def intersect_xy(a,b,margin=.02):
    return all(a[0][i] < b[1][i]+margin and a[1][i] > b[0][i]-margin for i in (0,1))


def add_context(study, job, attempt):
    result = original(study, job, attempt)
    pads = [bpy.data.objects[name] for name in result[0]]
    bpy.context.view_layer.update()
    pad_bounds = [bounds(o) for o in pads]
    anchor = pads[0].location.copy() if pads else Vector((0,0,0))
    width = study['config']['width_metres']
    objects=[]
    for i in range(2):
        if manifest['kind'] == 'relief':
            bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, location=(0,0,0))
            obj=bpy.context.object; obj.name=f'context-relief-{i}'
            obj.scale=(width*.20,width*.13,width*.035)
            obj.data.materials.append(bpy.data.objects['ground'].data.materials[0]); group=[obj]; roots=[obj]
        elif manifest['kind'] == 'imported':
            before = set(bpy.data.objects)
            result_import = bpy.ops.import_scene.gltf(filepath=manifest['assets'][i]['path'])
            if 'FINISHED' not in result_import: raise RuntimeError('GLB import failed')
            imported = set(bpy.data.objects) - before
            group = [o for o in imported if o.type == 'MESH']
            roots = [o for o in imported if o.parent not in imported]
            if not group or not roots: raise RuntimeError('Imported asset contains no mesh or root')
            for obj in group: obj.name='context-'+obj.name
        else: raise RuntimeError('Unknown context kind')
        bpy.context.view_layer.update()
        # Arrange each group as a rigid collection and place its lowest bound at ground.
        bb=[bounds(o) for o in group]
        lo=[min(b[0][j] for b in bb) for j in range(3)]; hi=[max(b[1][j] for b in bb) for j in range(3)]
        # Use the union of all pad footprints, then add clearance for context extent.
        maxx=max([b[1][0] for b in pad_bounds] or [anchor.x + width/2])
        minx=min([b[0][0] for b in pad_bounds] or [anchor.x - width/2])
        targetx = maxx + .08 + (hi[0]-lo[0])/2 if i==0 else minx - .08 - (hi[0]-lo[0])/2
        targety = anchor.y + (i-.5)*width*.45
        delta=Vector((targetx-(hi[0]+lo[0])/2,targety-(hi[1]+lo[1])/2,-lo[2]))
        for obj in roots: obj.location += delta
        bpy.context.view_layer.update()
        if any(intersect_xy(bounds(o),p,margin=.01) for o in group for p in pad_bounds):
            raise RuntimeError('Context intersects pad footprint')
        objects.extend(group)
    scene=bpy.context.scene; rows=[]
    for obj in objects:
        bb=bounds(obj); center=Vector([(bb[0][i]+bb[1][i])/2 for i in range(3)])
        projected=world_to_camera_view(scene,scene.camera,center)
        rows.append({'name':obj.name,'triangles':sum(max(0,len(p.vertices)-2) for p in obj.data.polygons),'world_bounds_m':bb,'minimum_z_m':bb[0][2], 'pad_xy_intersection':any(intersect_xy(bb,p,margin=0) for p in pad_bounds),'center_camera_normalized':[projected.x,projected.y,projected.z],'center_in_frame':0<=projected.x<=1 and 0<=projected.y<=1 and projected.z>0,'matrix_world':[list(row) for row in obj.matrix_world]})
    output=study_path.parent/'prototype-context'/job['id']; output.mkdir(parents=True,exist_ok=True)
    namespace['atomic_json'](output/f'attempt-{attempt}.json',{'kind':manifest['kind'],'study_identity':study['identity'],'job_id':job['id'],'attempt':attempt,'objects':rows,'pad_world_bounds_m':pad_bounds,'visibility':'context is visible to camera and participates in visible and isolated full mask passes'})
    return result

original=namespace['build_scene']; namespace['build_scene']=add_context
bproc.init()
for job in study['jobs']:
    if job['id'] in args.jobs: namespace['run_job'](study,job,study_path.parent)
