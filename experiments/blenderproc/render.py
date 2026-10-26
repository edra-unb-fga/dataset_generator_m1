import blenderproc as bproc
# This script runs only inside the pinned Blender runtime (Python3.11).
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile
from time import perf_counter

import bpy
from blenderproc.python.utility.GlobalStorage import GlobalStorage
import numpy as np
from PIL import Image
from mathutils import Vector


def atomic_json(path,value):
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(value,indent=2));os.replace(temporary,path)


def image_node(material,path,noncolor=False):
    node=material.node_tree.nodes.new('ShaderNodeTexImage')
    node.image=bpy.data.images.load(str(path),check_existing=True)
    if noncolor:node.image.colorspace_settings.name='Non-Color'
    return node


def material(name,color=(.2,.2,.2,1),roughness=.5):
    result=bpy.data.materials.new(name);result.use_nodes=True
    shader=result.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value=color
    shader.inputs['Roughness'].default_value=roughness
    shader.inputs['Metallic'].default_value=0
    shader.inputs['IOR'].default_value=1.46
    return result,shader


def panel(name,artwork,width,thickness,location,angle,roughness,normal_strength):
    height=width*artwork['aspect']
    bpy.ops.mesh.primitive_cube_add(size=1,location=location)
    obj=bpy.context.object;obj.name=name
    obj.scale=(width,height,thickness)
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    uv=obj.data.uv_layers.active
    for face in obj.data.polygons:
        for loop_index in face.loop_indices:
            vertex=obj.data.vertices[obj.data.loops[loop_index].vertex_index].co
            uv.data[loop_index].uv=(vertex.x/width+.5,vertex.y/height+.5)
    mat,shader=material(name+'-plastic',roughness=roughness)
    texture=image_node(mat,artwork['path'])
    mat.node_tree.links.new(texture.outputs['Color'],shader.inputs['Base Color'])
    # Fine surface normals alter reflection, never the rigid support geometry.
    noise=mat.node_tree.nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=350
    bump=mat.node_tree.nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=normal_strength
    bump.inputs['Distance'].default_value=.00015
    mat.node_tree.links.new(noise.outputs['Fac'],bump.inputs['Height']);mat.node_tree.links.new(bump.outputs['Normal'],shader.inputs['Normal'])
    obj.data.materials.append(mat);obj.rotation_euler[2]=math.radians(angle)
    return obj


def light(name,kind,location,power,color,size,target=(0,0,0)):
    data=bpy.data.lights.new(name,kind);data.energy=power;data.color=color
    if kind=='AREA':data.shape='DISK';data.size=size
    if kind=='SUN':data.angle=size
    obj=bpy.data.objects.new(name,data);bpy.context.collection.objects.link(obj);obj.location=location
    obj.rotation_euler=(Vector(target)-obj.location).to_track_quat('-Z','Y').to_euler()
    return obj


def ground_material(ground,treatment):
    mat,shader=material('ground',roughness=.8)
    nodes=mat.node_tree.nodes;links=mat.node_tree.links
    coord=nodes.new('ShaderNodeTexCoord');mapping=nodes.new('ShaderNodeMapping')
    tile=treatment['uv_scale_m']
    mapping.inputs['Scale'].default_value=(40/tile,40/tile,1)
    mapping.inputs['Rotation'].default_value[2]=math.radians(treatment['uv_rotation_degrees'])
    links.new(coord.outputs['UV'],mapping.inputs['Vector'])
    for role,socket in (('color','Base Color'),('roughness','Roughness')):
        if role not in ground['maps']:continue
        texture=image_node(mat,ground['maps'][role],role!='color')
        links.new(mapping.outputs['Vector'],texture.inputs['Vector']);links.new(texture.outputs['Color'],shader.inputs[socket])
    if 'normal' in ground['maps']:
        texture=image_node(mat,ground['maps']['normal'],True);links.new(mapping.outputs['Vector'],texture.inputs['Vector'])
        normal=nodes.new('ShaderNodeNormalMap');normal.inputs['Strength'].default_value=treatment['normal_strength']
        links.new(texture.outputs['Color'],normal.inputs['Color']);links.new(normal.outputs['Normal'],shader.inputs['Normal'])
    return mat


def build_scene(study,job,attempt):
    bproc.clean_up(clean_up_camera=True)
    scene=bpy.context.scene;t=job['treatment'];config=study['config']
    scene.render.use_motion_blur=False
    bproc.renderer.set_render_devices(use_only_cpu=True)
    bproc.renderer.set_max_amount_of_samples(job['samples']);bproc.renderer.set_denoiser('INTEL')
    bproc.renderer.set_light_bounces(diffuse_bounces=2,glossy_bounces=2,max_bounces=4,transparent_max_bounces=4)
    scene.render.threads_mode='FIXED';scene.render.threads=config['threads']
    scene.cycles.seed=job['seed'];scene.cycles.use_adaptive_sampling=False
    scene.view_settings.view_transform=t['tone'];scene.view_settings.exposure=t['exposure_ev']
    scene.render.fps=24
    width,height=config['resolution'];focal=width*config['focal_length_mm']/config['sensor_width_mm']
    K=np.array([[focal,0,(width-1)*config['principal_point_fraction'][0]],[0,focal,(height-1)*config['principal_point_fraction'][1]],[0,0,1.]])
    bproc.camera.set_intrinsics_from_K_matrix(K,width,height,clip_start=.03,clip_end=200)
    fractions=[obj['fraction'] for obj in job['scene']['objects']] or [.18]
    extents=[abs(math.cos(math.radians(o['angle'])))+study['artwork'][o['artwork_index']]['aspect']*abs(math.sin(math.radians(o['angle']))) for o in job['scene']['objects']] or [1.]
    distance=config['width_metres']*float(np.median(extents))*(config['focal_length_mm']/config['sensor_width_mm'])/max(.04,float(np.median(fractions)))*t['camera_distance_scale']
    if job['case']=='closeup':distance*=.45
    angle=math.radians(t['view_degrees'])
    azimuth=math.radians(t['camera_azimuth_degrees'])
    position=np.array([distance*math.sin(angle)*math.sin(azimuth),-distance*math.sin(angle)*math.cos(azimuth),distance*math.cos(angle)])
    rotation=bproc.camera.rotation_from_forward_vec(-position,inplane_rot=math.radians(t['camera_roll_degrees']))
    matrix=bproc.math.build_transformation_mat(position,rotation)
    # A continuous translating camera, stationary targets. Pose0 is label reference.
    for frame in (-1,0,1):
        pose=matrix.copy();pose[0,3]+=frame*t['camera_speed_mps']/24
        bproc.camera.add_camera_pose(pose,frame=frame)
    scene.frame_start=0;scene.frame_end=1;scene.frame_set(0)
    camera=scene.camera
    if t['depth_of_field']:
        bproc.camera.add_depth_of_field(None,
            fstop_value=t['aperture_fstop'],focal_distance=t['focus_distance_m'] or distance*.92)
    if t['camera_speed_mps']:
        bproc.renderer.enable_motion_blur(motion_blur_length=t['shutter_seconds']*24)
    mapping=None
    if any(t['distortion']):mapping=bproc.camera.set_lens_distortion(*t['distortion'])
    bpy.ops.mesh.primitive_plane_add(size=40)
    ground=bpy.context.object;ground.name='ground';ground.data.materials.append(ground_material(study['grounds'][job['ground_index']],t))
    world=scene.world;world.use_nodes=True
    background=world.node_tree.nodes.get('Background')
    tex=world.node_tree.nodes.new('ShaderNodeTexEnvironment')
    envindex=0 if t['lighting']=='environment' else 1
    tex.image=bpy.data.images.load(study['environments'][envindex],check_existing=True)
    world.node_tree.links.new(tex.outputs['Color'],background.inputs['Color'])
    background.inputs['Strength'].default_value=.015 if t['lighting'].startswith('night') else (.7 if t['lighting']=='overcast' else .08 if t['lighting']=='shade' else .25)
    if t['lighting']=='sun':
        elev=math.radians(t['sun_elevation_degrees'])
        light('sun','SUN',(-5,-5,7*math.tan(elev)),2.0,(1,.94,.85),.025)
    if t['lighting'].startswith('night'):
        light('lamp','AREA',(-2,-2,3),t['light_power_w'],(1,.78,.52),t['light_size_m'])
        if t['lighting']=='night-mixed':light('lamp-blue','AREA',(3,1,2),t['light_power_w']*.6,(.55,.7,1),t['light_size_m']*1.5)
    pads=[]
    rng=np.random.default_rng(job['seed']+attempt*100003)
    for index,planned in enumerate(job['scene']['objects']):
        u,v=planned['center']
        if attempt:u+=rng.uniform(-.025,.025);v+=rng.uniform(-.025,.025)
        ray=rotation@np.array([(u*width-K[0,2])/focal,-(v*height-K[1,2])/focal,-1.])
        at=position+ray*((config['thickness_metres']/2-position[2])/ray[2])
        at[2]=config['thickness_metres']/2
        if job['case']=='clipped' and index==0:at[0]+=distance*.4
        if job['case']=='overlap' and index==1:
            at=np.array(pads[0].location)+np.array([.04,.03,config['thickness_metres']])
        pads.append(panel(f'pad-{index}',study['artwork'][planned['artwork_index']],config['width_metres'],config['thickness_metres'],at,planned['angle'],t['roughness'],t['normal_strength']))
    if t['shadows']:
        # Nearby geometry casts coherent shadows; placement may also occlude a pad.
        for index in range(3):
            bpy.ops.mesh.primitive_cube_add(size=1,location=(-2+index*.6,-1,1.6))
            obj=bpy.context.object;obj.name=f'ambient-caster-{index}';obj.scale=(.07,.08,3.2)
    if (t['occluder'] or job['case'] in ('occluded','fully-hidden')) and pads:
        at=np.array(pads[0].location)
        if job['case']=='fully-hidden':scale=(2.,2.,.1)
        else:scale=(.23,1.5,.04)
        offset=np.array([0.,0.,.075]) if job['case']=='fully-hidden' else np.array([.1,0,.05])
        bpy.ops.mesh.primitive_cube_add(size=1,location=at+offset)
        bpy.context.object.name='occluder';bpy.context.object.scale=scale
    volume=None
    if t['haze_density']:
        bpy.ops.mesh.primitive_cube_add(size=1,location=(0,0,8));volume=bpy.context.object;volume.name='haze';volume.scale=(30,30,16)
        mat=bpy.data.materials.new('haze');mat.use_nodes=True;nodes=mat.node_tree.nodes;nodes.clear()
        shader=nodes.new('ShaderNodeVolumePrincipled');shader.inputs['Density'].default_value=t['haze_density']
        output=nodes.new('ShaderNodeOutputMaterial');mat.node_tree.links.new(shader.outputs['Volume'],output.inputs['Volume'])
        volume.data.materials.append(mat)
    return [obj.name for obj in pads],volume.name if volume else None,mapping,K,distance


def distorted(value,mapping,size,interpolate):
    if mapping is None:return value
    return bproc.postprocessing.apply_lens_distortion(value,mapping_coords=mapping,orig_res_x=size[0],orig_res_y=size[1],use_interpolation=interpolate)


def segmentation(pads,temp,mapping,size):
    # Pinned BlenderProc keeps output registrations beyond scene clean_up/undo.
    GlobalStorage.set('output',[])
    data=bproc.renderer.render_segmap(output_dir=str(temp),temp_dir=str(temp),map_by=['instance','name'])
    indices={row['name']:row['idx'] for row in data['instance_attribute_maps'][0]}
    ids=distorted(data['instance_segmaps'][0],mapping,size,False)
    if ids.ndim==3:ids=ids[:,:,0]
    return np.stack([ids==indices.get(name,-1) for name in pads]) if pads else np.zeros((0,size[1],size[0]),bool)


def run_job(study,job,root):
    started=perf_counter();destination=root/'scenes'/job['id']
    if (destination/'result.json').exists():return
    config=study['config'];attempts=[]
    for attempt in range(8):
        setup_started=perf_counter();pads,volume,mapping,K,distance=build_scene(study,job,attempt)
        setup_seconds=perf_counter()-setup_started
        # Labels use sharp geometry at pose0, independent of beauty DOF/blur.
        scene=bpy.context.scene;dof=scene.camera.data.dof.use_dof;motion=scene.render.use_motion_blur
        scene.camera.data.dof.use_dof=False;scene.render.use_motion_blur=False
        if volume:bpy.data.objects[volume].hide_render=True
        label_started=perf_counter()
        with tempfile.TemporaryDirectory(dir=root) as temporary:
            temp=Path(temporary)
            visible=segmentation(pads,temp,mapping,config['resolution'])
            full=[];meshes=[o.name for o in bpy.context.scene.objects if o.type=='MESH']
            for pad in pads:
                hidden={name:bpy.data.objects[name].hide_render for name in meshes}
                for name in meshes:bpy.data.objects[name].hide_render=name!=pad
                masks=segmentation([pad],temp,mapping,config['resolution']);full.append(masks[0])
                for name,flag in hidden.items():bpy.data.objects[name].hide_render=flag
            full=np.stack(full) if full else np.zeros_like(visible)
            # The same single-ray geometric rasterization must give subset masks.
            if np.any(visible&~full):raise RuntimeError('Visible reference exceeds isolated full support')
            support=[float(v.sum()/f.sum()) if f.any() else 0 for v,f in zip(visible,full)]
            rejection='below-visible-support-floor' if any(0<v<.25 for v in support) else None
            if not visible.any() and not job['scene']['negative']:rejection='accidental-empty-positive'
            annotation_seconds=perf_counter()-label_started
            attempts.append({'attempt':attempt,'setup_seconds':setup_seconds,'annotation_seconds':annotation_seconds,'support':support,'rejection':rejection})
            if rejection:continue
            scene=bpy.context.scene
            scene.camera.data.dof.use_dof=dof;scene.render.use_motion_blur=motion
            if volume:bpy.data.objects[volume].hide_render=False
            render_started=perf_counter()
            GlobalStorage.set('output',[])
            data=bproc.renderer.render(output_dir=str(temp),load_keys={'colors'},verbose=False)
            cold_render=perf_counter()-render_started
            warm=[]
            if job.get('benchmark'):
                for repeat in range(2):
                    stamp=perf_counter();data=bproc.renderer.render(output_dir=str(temp),output_key=None,load_keys={'colors'},verbose=False);warm.append(perf_counter()-stamp)
            rgb=distorted(data['colors'][0],mapping,config['resolution'],True)[:,:,:3]
            if job['treatment']['noise_std']:
                rng=np.random.default_rng(job['seed']+991)
                rgb=np.clip(rgb.astype(float)+rng.normal(0,job['treatment']['noise_std']*255,rgb.shape),0,255).astype(np.uint8)
            destination.parent.mkdir(parents=True,exist_ok=True)
            with tempfile.TemporaryDirectory(dir=destination.parent) as staging:
                staging=Path(staging);encode_started=perf_counter()
                Image.fromarray(rgb.astype(np.uint8)).save(staging/'rgb.png')
                np.savez_compressed(staging/'masks.npz',visible=visible,full=full)
                record={'identity':study['identity'],'job':job,'status':'accepted','attempts':attempts,
                        'rgb_render_seconds':cold_render,'warm_same_scene_render_seconds':warm,
                        'encode_seconds':perf_counter()-encode_started,'total_seconds':perf_counter()-started,
                        'accepted_output_seconds':perf_counter()-started-sum(warm),
                        'blender':bpy.app.version_string,'blenderproc':bproc.__version__,'device':'CPU',
                        'renderer_settings':{'engine':scene.render.engine,'samples':scene.cycles.samples,
                            'denoiser':'OpenImageDenoise','max_bounces':scene.cycles.max_bounces,
                            'diffuse_bounces':scene.cycles.diffuse_bounces,'glossy_bounces':scene.cycles.glossy_bounces,
                            'internal_resolution':[scene.render.resolution_x,scene.render.resolution_y],
                            'output_resolution':config['resolution'],'numpy':np.__version__,
                            'camera_to_world_opengl':np.asarray(scene.camera.matrix_world).tolist(),
                            'motion_blur':motion,'depth_of_field':dof},'intrinsics_K_before_distortion':K.tolist(),
                        'camera_distance_metres':distance,'reference_masks':'single-ray sharp geometry at frame0',
                        'noise_model':'post-display RGB Gaussian approximation, not calibrated sensor simulation',
                        'files':{name:hashlib.sha256((staging/name).read_bytes()).hexdigest() for name in ('rgb.png','masks.npz')}}
                atomic_json(staging/'result.json',record)
                if destination.exists():raise RuntimeError('Refuse to replace incomplete output directory')
                os.rename(staging,destination)
            print('PILOT_ACCEPTED',job['id'],record['total_seconds'],flush=True)
            return
    destination.mkdir(parents=True,exist_ok=True)
    atomic_json(destination/'result.json',{'identity':study['identity'],'job':job,'status':'rejected','attempts':attempts,'files':{},'total_seconds':perf_counter()-started})


parser=argparse.ArgumentParser();parser.add_argument('study');parser.add_argument('--jobs',nargs='*')
args=parser.parse_args();path=Path(args.study).resolve();study=json.loads(path.read_text());root=path.parent
if bproc.__version__!='2.8.0' or bpy.app.version!=(4,2,1):
    raise RuntimeError(f'Pinned runtime required: BlenderProc2.8.0 / Blender4.2.1, got {bproc.__version__} / {bpy.app.version_string}')
started=perf_counter();bproc.init();print('PILOT_STARTUP_SECONDS',perf_counter()-started,flush=True)
for job in study['jobs']:
    if args.jobs and job['id'] not in args.jobs:continue
    run_job(study,job,root)
