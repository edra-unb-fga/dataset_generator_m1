"""Exercise the actual renderer UV functions against Blender's computed mesh tangents."""
import ast,hashlib,json,math,sys
from pathlib import Path
import bpy
from mathutils import Vector
args=sys.argv[sys.argv.index('--')+1:];root=Path(args[0]);output=Path(args[1]);namespace={'math':math}
for path,name in [(root/'src/dataset_generator_m1/blender_camera.py','ground_uv'),(root/'experiments/blenderproc/render.py','ground_mesh_uv')]:
 source=path.read_text();tree=ast.parse(source);node=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name==name);module=ast.Module(body=[node],type_ignores=[]);exec(compile(module,str(path),'exec'),namespace)
rows=[]
for angle in (0,90):
 bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False);bpy.ops.mesh.primitive_plane_add(size=8);obj=bpy.context.object
 namespace['ground_mesh_uv'](obj,2,angle,(0,0));obj.data.calc_tangents(uvmap=obj.data.uv_layers.active.name)
 expected_t=Vector((math.cos(math.radians(angle)),-math.sin(math.radians(angle)),0));expected_b=Vector((math.sin(math.radians(angle)),math.cos(math.radians(angle)),0))
 for loop in obj.data.loops:
  tangent=loop.tangent.copy();bitangent=loop.bitangent.copy();assert (tangent-expected_t).length<1e-5 and (bitangent-expected_b).length<1e-5,(angle,tangent,bitangent)
  rows.append({'angle_degrees':angle,'tangent':list(tangent),'bitangent':list(bitangent),'sign':loop.bitangent_sign})
output.write_text(json.dumps({'status':'pass','blender':bpy.app.version_string,'source_sha256':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'src/dataset_generator_m1/blender_camera.py',root/'experiments/blenderproc/render.py')},'loops':rows},indent=2));print('BLENDER_TANGENTS_PASS',output)
