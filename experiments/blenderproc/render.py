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

sys.path.insert(0,str(Path(__file__).resolve().parent))
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))
from dataset_generator_m1.blender_camera import rotation_matrix, ground_geometry, environment_bounds
from runtime import configure as configure_execution, evidence as execution_evidence
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


def panel(name,artwork,width,thickness,location,angle,roughness,normal_strength,bump_distance,wear=None):
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
    texture=image_node(mat,wear['maps']['albedo']['path'] if wear else artwork['path'])
    mat.node_tree.links.new(texture.outputs['Color'],shader.inputs['Base Color'])
    # Fine surface normals alter reflection, never the rigid support geometry.
    if wear:
        noise=image_node(mat,wear['maps']['height']['path'],True)
        rough=image_node(mat,wear['maps']['roughness']['path'],True)
        mat.node_tree.links.new(rough.outputs['Color'],shader.inputs['Roughness'])
    else:
        noise=mat.node_tree.nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=350
    bump=mat.node_tree.nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=normal_strength
    bump.inputs['Distance'].default_value=bump_distance
    mat.node_tree.links.new(noise.outputs['Color'] if wear else noise.outputs['Fac'],bump.inputs['Height']);mat.node_tree.links.new(bump.outputs['Normal'],shader.inputs['Normal'])
    obj.data.materials.append(mat);obj.rotation_euler[2]=math.radians(angle)
    return obj


def light(name,kind,location,power,color,size,target=(0,0,0)):
    data=bpy.data.lights.new(name,kind);data.energy=power;data.color=color
    if kind=='AREA':data.shape='DISK';data.size=size
    if kind=='SUN':data.angle=size
    obj=bpy.data.objects.new(name,data);bpy.context.collection.objects.link(obj);obj.location=location
    obj.rotation_euler=(Vector(target)-obj.location).to_track_quat('-Z','Y').to_euler()
    return obj


def ground_material(ground,treatment,extent=40,tile_override=None):
    mat,shader=material('ground',roughness=.8)
    nodes=mat.node_tree.nodes;links=mat.node_tree.links
    coord=nodes.new('ShaderNodeTexCoord');mapping=nodes.new('ShaderNodeMapping')
    tile=tile_override if tile_override is not None else treatment['uv_scale_m']
    mapping.inputs['Scale'].default_value=(extent/tile,extent/tile,1)
    mapping.inputs['Rotation'].default_value[2]=math.radians(treatment['uv_rotation_degrees'])
    mapping.inputs['Location'].default_value=(*treatment.get('ground_uv_offset',(0,0)),0)
    links.new(coord.outputs['UV'],mapping.inputs['Vector'])
    for role,socket in (('color','Base Color'),('roughness','Roughness')):
        if role not in ground['maps']:continue
        texture=image_node(mat,ground['maps'][role],role!='color')
        links.new(mapping.outputs['Vector'],texture.inputs['Vector']);links.new(texture.outputs['Color'],shader.inputs[socket])
    if 'normal' in ground['maps']:
        texture=image_node(mat,ground['maps']['normal'],True);links.new(mapping.outputs['Vector'],texture.inputs['Vector'])
        normal=nodes.new('ShaderNodeNormalMap');normal.inputs['Strength'].default_value=treatment.get('ground_normal_strength') if treatment.get('ground_normal_strength') is not None else treatment['normal_strength']
        links.new(texture.outputs['Color'],normal.inputs['Color']);links.new(normal.outputs['Normal'],shader.inputs['Normal'])
    return mat


def environment_geometry(kind, position, settings, grounds, camera_speed_mps, shutter_seconds):
    """Build enclosing surfaces using saved dimensions and material choices."""
    if kind == 'open':
        return None
    bounds=environment_bounds(position,settings,camera_speed_mps,shutter_seconds)
    half=bounds['half_width_m'];height=bounds['ceiling_height_m']
    wall_height=height if kind == 'indoor' else settings['outdoor_wall_height_m']
    wall_mat,shader=material('environment-wall',(*settings['wall_color'],1),settings['wall_roughness'])
    index=settings['wall_ground_index']
    if index is not None:
        texture=image_node(wall_mat,grounds[index]['maps']['color'])
        coord=wall_mat.node_tree.nodes.new('ShaderNodeTexCoord')
        mapping=wall_mat.node_tree.nodes.new('ShaderNodeMapping')
        repeats=settings['wall_texture_repeats']
        mapping.inputs['Scale'].default_value=(repeats,repeats,1)
        links=wall_mat.node_tree.links
        links.new(coord.outputs['UV'],mapping.inputs['Vector'])
        links.new(mapping.outputs['Vector'],texture.inputs['Vector'])
        links.new(texture.outputs['Color'],shader.inputs['Base Color'])
    def box(name, location, scale):
        bpy.ops.mesh.primitive_cube_add(size=1,location=location)
        obj=bpy.context.object;obj.name=name;obj.scale=scale;obj.data.materials.append(wall_mat)
    thickness=settings['wall_thickness_m']
    for axis in (-1,1):
        box(f'environment-wall-x-{axis}',(axis*half,0,wall_height/2),(thickness,2*half,wall_height))
        box(f'environment-wall-y-{axis}',(0,axis*half,wall_height/2),(2*half,thickness,wall_height))
    if kind == 'indoor':
        box('environment-ceiling',(0,0,height),(2*half,2*half,thickness))
        light('environment-ceiling-light','AREA',(0,0,height-settings['indoor_light_ceiling_offset_m']),
              settings['indoor_light_power_w'],settings['indoor_light_color'],settings['indoor_light_size_m'])
    return {'kind':kind,'half_width_m':half,'wall_height_m':wall_height,
            'ceiling_height_m':height if kind == 'indoor' else None,
            'camera_motion_margin_m':bounds['camera_motion_margin_m'],'settings':settings}


def build_scene(study,job,attempt):
    bproc.clean_up(clean_up_camera=True)
    scene=bpy.context.scene;t=job['treatment'];config=study['config']
    scene.render.use_motion_blur=False
    configure_execution(EXECUTION)
    bproc.renderer.set_max_amount_of_samples(job['samples'])
    scene.cycles.seed=job['seed'];scene.cycles.use_adaptive_sampling=False
    scene.view_settings.view_transform=t['tone'];scene.view_settings.exposure=t['exposure_ev']
    scene.render.fps=24
    width,height=config['resolution'];focal=width*config['focal_length_mm']/config['sensor_width_mm']
    K=np.array([[focal,0,(width-1)*config['principal_point_fraction'][0]],[0,focal,(height-1)*config['principal_point_fraction'][1]],[0,0,1.]])
    bproc.camera.set_intrinsics_from_K_matrix(K,width,height,clip_start=.03,clip_end=1000 if job.get('camera_pose') else 200)
    fractions=[obj['fraction'] for obj in job['scene']['objects']] or [.18]
    extents=[abs(math.cos(math.radians(o['angle'])))+study['artwork'][o['artwork_index']]['aspect']*abs(math.sin(math.radians(o['angle']))) for o in job['scene']['objects']] or [1.]
    distance=config['width_metres']*float(np.median(extents))*(config['focal_length_mm']/config['sensor_width_mm'])/max(.04,float(np.median(fractions)))*t['camera_distance_scale']
    if job['case']=='closeup' and not job.get('camera_pose'):distance*=.45
    pose=job.get('camera_pose')
    camera_evidence=None
    ground_evidence=None
    if pose:
        settings=config['camera_study']
        rotation=rotation_matrix(pose)
        reference_distance=distance/t['camera_distance_scale']
        # Match the median projected panel width to the reference, within saved bounds.
        def projected_fraction(distance_value):
            position_value=rotation[:,2]*distance_value
            values=[]
            for obj in job['scene']['objects']:
                a=math.radians(obj['angle']); aspect=study['artwork'][obj['artwork_index']]['aspect']
                points=[]
                for x,y in ((-.5,-.5),(-.5,.5),(.5,-.5),(.5,.5)):
                    x*=config['width_metres']; y*=config['width_metres']*aspect
                    world=np.array([x*math.cos(a)-y*math.sin(a),x*math.sin(a)+y*math.cos(a),config['thickness_metres']/2])
                    camera=rotation.T@(world-position_value)
                    if camera[2]>=0:return float('inf')
                    points.append(focal*camera[0]/-camera[2])
                values.append((max(points)-min(points))/width)
            return float(np.median(values)) if values else None
        target=float(np.median(fractions))
        lo,hi=[reference_distance*x for x in settings['distance_scale_bounds']]
        if job['scene']['objects']:
            for _ in range(settings['distance_solver_iterations']):
                mid=(lo+hi)/2
                if projected_fraction(mid)>target:lo=mid
                else:hi=mid
            distance=(lo+hi)/2
        else:distance=reference_distance
        if job['case']=='closeup':distance*=.45
        position=rotation[:,2]*distance
        achieved=projected_fraction(distance)
        camera_evidence={'pose':pose,'target_width_fraction':target if achieved is not None else None,
                         'representative_centered_width_fraction':achieved,
                         'distance_bound_reached': bool(job['case']!='closeup' and achieved is not None and abs(achieved-target)>target*settings['distance_relative_tolerance']),
                         'deliberate_closeup_distance_scale':.45 if job['case']=='closeup' else None}
    else:
        angle=math.radians(t['view_degrees'])
        azimuth=math.radians(t['camera_azimuth_degrees'])
        position=np.array([distance*math.sin(angle)*math.sin(azimuth),-distance*math.sin(angle)*math.cos(azimuth),distance*math.cos(angle)])
        rotation=bproc.camera.rotation_from_forward_vec(-position,inplane_rot=math.radians(t['camera_roll_degrees']))
    matrix=bproc.math.build_transformation_mat(position,rotation)
    # A continuous translating camera, stationary targets. Pose0 is label reference.
    for frame in (-1,0,1):
        frame_pose=matrix.copy();frame_pose[0,3]+=frame*t['camera_speed_mps']/24
        bproc.camera.add_camera_pose(frame_pose,frame=frame)
    scene.frame_start=0;scene.frame_end=1;scene.frame_set(0)
    camera=scene.camera
    if t['depth_of_field']:
        bproc.camera.add_depth_of_field(None,
            fstop_value=t['aperture_fstop'],focal_distance=t['focus_distance_m'] or distance*.92)
    if t['camera_speed_mps']:
        bproc.renderer.enable_motion_blur(motion_blur_length=t['shutter_seconds']*24)
    mapping=None
    if any(t['distortion']):mapping=bproc.camera.set_lens_distortion(*t['distortion'])
    if job.get('camera_pose'):
        internal_K=bproc.camera.get_intrinsics_as_K_matrix() if mapping is not None else K
        bounds=None
        if mapping is not None:
            # BlenderProc maps every output pixel to its undistorted internal render.
            bounds=(float(np.min(mapping[1]))-1,float(np.min(mapping[0]))-1,
                    float(np.max(mapping[1]))+1,float(np.max(mapping[0]))+1)
        motion=t['camera_speed_mps']*max(1/24,t['shutter_seconds']/2) if t['camera_speed_mps'] else 0
        ground_evidence=ground_geometry(position,rotation,internal_K,(width,height),settings,t['uv_scale_m'],
                                        job['camera_pose']['ground_spans'],pixel_bounds=bounds,motion_m=motion,
                                        distorted=mapping is not None)
        if settings['material_mode']=='fixed-physical':
            ground_evidence['tile_m']=t['uv_scale_m']
            ground_evidence['achieved_spans']=(ground_evidence['central_view_width_m']/t['uv_scale_m'] if ground_evidence['central_view_width_m'] else None)
        ground_evidence['material_mode']=settings['material_mode']
    extent=ground_evidence['extent_m'] if ground_evidence else 40
    tile=ground_evidence['tile_m'] if ground_evidence else None
    bpy.ops.mesh.primitive_plane_add(size=extent)
    ground=bpy.context.object;ground.name='ground';ground.data.materials.append(ground_material(study['grounds'][job['ground_index']],t,extent,tile))
    geometry=environment_geometry(job.get('environment_geometry','open'),position,config.get('environment_geometry_settings'),study['grounds'],t['camera_speed_mps'],t['shutter_seconds'])
    world=scene.world;world.use_nodes=True
    background=world.node_tree.nodes.get('Background')
    tex=world.node_tree.nodes.new('ShaderNodeTexEnvironment')
    envindex=envindex_for(t,len(study['environments']))
    coords=world.node_tree.nodes.new('ShaderNodeTexCoord');envmap=world.node_tree.nodes.new('ShaderNodeMapping')
    envmap.inputs['Rotation'].default_value[2]=math.radians(t.get('environment_rotation_degrees',0))
    world.node_tree.links.new(coords.outputs['Generated'],envmap.inputs['Vector']);world.node_tree.links.new(envmap.outputs['Vector'],tex.inputs['Vector'])
    tex.image=bpy.data.images.load(study['environments'][envindex],check_existing=True)
    world.node_tree.links.new(tex.outputs['Color'],background.inputs['Color'])
    background.inputs['Strength'].default_value=.015 if t['lighting'].startswith('night') else (.7 if t['lighting']=='overcast' else .08 if t['lighting']=='shade' else .25)
    if t.get('environment_strength') is not None:background.inputs['Strength'].default_value=t['environment_strength']
    if job.get('environment_geometry')=='indoor':background.inputs['Strength'].default_value=0
    if t['lighting']=='sun' and job.get('environment_geometry')!='indoor':
        elev=math.radians(t['sun_elevation_degrees'])
        light('sun','SUN',(-5,-5,7*math.tan(elev)),2.0,(1,.94,.85),.025)
    if t.get('lamps') is not None:
        for index,lamp in enumerate(t['lamps']):
            light(f'lamp-{index}','AREA',lamp['location'],lamp['power_w'],lamp['color'],lamp['size_m'],lamp['target'])
    elif t['lighting'].startswith('night'):
        light('lamp','AREA',(-2,-2,3),t['light_power_w'],(1,.78,.52),t['light_size_m'])
        if t['lighting']=='night-mixed':light('lamp-blue','AREA',(3,1,2),t['light_power_w']*.6,(.55,.7,1),t['light_size_m']*1.5)
    pads=[]
    rng=np.random.default_rng(job['seed']+attempt*100003)
    for index,planned in enumerate(job['scene']['objects']):
        u,v=planned['center']
        if pose and len(job['scene']['objects'])==1 and job['case']!='clipped':u=v=.5
        if attempt and not (pose and len(job['scene']['objects'])==1 and job['case']!='clipped'):
            u+=rng.uniform(-.025,.025);v+=rng.uniform(-.025,.025)
        ray=rotation@np.array([(u*width-K[0,2])/focal,-(v*height-K[1,2])/focal,-1.])
        at=position+ray*((config['thickness_metres']/2-position[2])/ray[2])
        at[2]=config['thickness_metres']/2
        if job['case']=='clipped' and index==0:at[0]+=distance*.4
        if job['case']=='overlap' and index==1:
            at=np.array(pads[0].location)+np.array([.04,.03,config['thickness_metres']])
        pads.append(panel(f'pad-{index}',study['artwork'][planned['artwork_index']],config['width_metres'],config['thickness_metres'],at,planned['angle'],t['roughness'],t.get('pad_bump_strength') if t.get('pad_bump_strength') is not None else t['normal_strength'],t.get('pad_bump_distance_m',.00015),job.get('wear_maps',[None]*len(job['scene']['objects']))[index]))
    if camera_evidence is not None:
        # Measure the final rigid panels at their actual planned positions (before lens distortion).
        actual=[]
        for obj in pads:
            a=obj.rotation_euler[2]; aspect=study['artwork'][job['scene']['objects'][len(actual)]['artwork_index']]['aspect']
            xs=[]
            for x,y in ((-.5,-.5),(-.5,.5),(.5,-.5),(.5,.5)):
                x*=config['width_metres'];y*=config['width_metres']*aspect
                world=np.array([obj.location.x+x*math.cos(a)-y*math.sin(a),obj.location.y+x*math.sin(a)+y*math.cos(a),obj.location.z+config['thickness_metres']/2])
                camera_local=rotation.T@(world-position)
                if camera_local[2]>=0:xs=[];break
                xs.append(focal*camera_local[0]/-camera_local[2])
            actual.append((max(xs)-min(xs))/width if xs else None)
        camera_evidence['actual_projected_width_fractions_before_distortion']=actual
        camera_evidence['actual_widths_include_clipping']=False
    caster_records=[]
    if t['shadows'] and t.get('casters') is None:
        for index in range(3):
            location=(-2+index*.6,-1,1.6);scale=(.07,.08,3.2)
            bpy.ops.mesh.primitive_cube_add(size=1,location=location)
            obj=bpy.context.object;obj.name=f'ambient-caster-{index}';obj.scale=scale
            caster_records.append({'name':obj.name,'location':list(location),'scale':list(scale),'visible_camera':True,'fixture':'legacy-posts'})
    for index,planned in enumerate(job.get('casters',[])):
        bpy.ops.mesh.primitive_cube_add(size=1,location=planned['location'])
        obj=bpy.context.object;obj.name=f'ambient-caster-{index}';obj.scale=planned['scale']
        obj.visible_camera=planned['visible_camera']
        caster_records.append({'name':obj.name,**planned,'fixture':'procedural'})
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
    return [obj.name for obj in pads],volume.name if volume else None,mapping,K,distance,caster_records,camera_evidence,ground_evidence,geometry


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


def envindex_for(treatment,environment_count):
    value=treatment.get('environment_index')
    return value if value is not None else (0 if treatment['lighting']=='environment' else min(1,environment_count-1))


def run_job(study,job,root):
    started=perf_counter();destination=root/'scenes'/job['id']
    if (destination/'result.json').exists():return
    config=study['config'];attempts=[]
    for attempt in range(8):
        setup_started=perf_counter();pads,volume,mapping,K,distance,casters,camera_evidence,ground_evidence,geometry=build_scene(study,job,attempt)
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
                        'blender':bpy.app.version_string,'blenderproc':bproc.__version__,'device':scene.cycles.device,'execution':execution_evidence(EXECUTION),
                        'renderer_settings':{'engine':scene.render.engine,'samples':scene.cycles.samples,
                            'denoiser':EXECUTION['settings']['denoiser'],'max_bounces':scene.cycles.max_bounces,
                            'diffuse_bounces':scene.cycles.diffuse_bounces,'glossy_bounces':scene.cycles.glossy_bounces,
                            'internal_resolution':[scene.render.resolution_x,scene.render.resolution_y],
                            'output_resolution':config['resolution'],'numpy':np.__version__,
                            'camera_to_world_opengl':np.asarray(scene.camera.matrix_world).tolist(),
                            'motion_blur':motion,'depth_of_field':dof},'intrinsics_K_before_distortion':K.tolist(),
                        'surface_diagnostics':{'ground_index':job['ground_index'],'environment_index':envindex_for(job['treatment'],len(study['environments'])),
                            'environment_strength':scene.world.node_tree.nodes.get('Background').inputs['Strength'].default_value,
                            'pad_bump_strength':job['treatment'].get('pad_bump_strength') if job['treatment'].get('pad_bump_strength') is not None else job['treatment']['normal_strength'],
                            'ground_normal_strength':job['treatment'].get('ground_normal_strength') if job['treatment'].get('ground_normal_strength') is not None else job['treatment']['normal_strength'],
                            'lamps':[{'name':o.name,'type':o.data.type,'location':list(o.location),'color':list(o.data.color),'power':o.data.energy,'rotation_euler':list(o.rotation_euler)} for o in scene.objects if o.type=='LIGHT'],
                            'treatment':job['treatment'],'wear_maps':job.get('wear_maps',[]),'casters':casters},
                        'environment_geometry_diagnostics':geometry,'camera_distance_metres':distance,'camera_diagnostics':camera_evidence,'ground_diagnostics':ground_evidence,'reference_masks':'single-ray sharp geometry at frame0',
                        'noise_model':'post-display RGB Gaussian approximation, not calibrated sensor simulation',
                        'files':{name:hashlib.sha256((staging/name).read_bytes()).hexdigest() for name in ('rgb.png','masks.npz')}}
                atomic_json(staging/'result.json',record)
                if destination.exists():raise RuntimeError('Refuse to replace incomplete output directory')
                os.rename(staging,destination)
            print('PILOT_ACCEPTED',job['id'],record['total_seconds'],flush=True)
            return
    destination.mkdir(parents=True,exist_ok=True)
    atomic_json(destination/'result.json',{'identity':study['identity'],'job':job,'status':'rejected','attempts':attempts,'files':{},'total_seconds':perf_counter()-started})


parser=argparse.ArgumentParser();parser.add_argument('study');parser.add_argument('--jobs',nargs='*');parser.add_argument('--execution',required=True)
args=parser.parse_args();path=Path(args.study).resolve();study=json.loads(path.read_text());root=path.parent
execution_record=json.loads(Path(args.execution).read_text())
if execution_record['study_identity']!=study['identity']:raise RuntimeError('Execution selection belongs to a different study')
EXECUTION=execution_record['selection']
if bproc.__version__!='2.8.0' or bpy.app.version!=(4,2,1):
    raise RuntimeError(f'Pinned runtime required: BlenderProc2.8.0 / Blender4.2.1, got {bproc.__version__} / {bpy.app.version_string}')
started=perf_counter();bproc.init();print('PILOT_STARTUP_SECONDS',perf_counter()-started,flush=True)
for job in study['jobs']:
    if args.jobs and job['id'] not in args.jobs:continue
    run_job(study,job,root)
