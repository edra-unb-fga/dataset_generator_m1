"""Pinned Blender-side capabilities and execution application (Python3.11)."""
import json
import os
from pathlib import Path
import platform
import subprocess
import sys


def hardware_info(backend_order):
    import bpy
    preferences=bpy.context.preferences.addons['cycles'].preferences
    count=os.cpu_count() or 1
    if hasattr(os,'sched_getaffinity'):count=min(count,len(os.sched_getaffinity(0)))
    memory={}
    try:
        result=subprocess.run(['nvidia-smi','--query-gpu=name,memory.total,driver_version','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=5)
        for line in result.stdout.splitlines():
            name,size,driver=line.rsplit(',',2);memory[name.strip()]={'memory_mib':int(size),'driver_version':driver.strip()}
    except (OSError,ValueError,subprocess.TimeoutExpired):pass
    devices=[]
    for backend in backend_order:
        try:
            preferences.compute_device_type=backend
            for d in preferences.get_device_list(backend):
                if d[1]=='CPU':continue
                devices.append({'id':d[2],'name':d[0],'backend':backend,'oidn_gpu':bool(d[5]),**memory.get(d[0],{'memory_mib':None,'driver_version':None})})
        except (TypeError,RuntimeError,ValueError):continue
    model=platform.processor()
    if Path('/proc/cpuinfo').exists():
        model=next((line.split(':',1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines() if line.startswith('model name')),model)
    import blenderproc as bproc
    import numpy as np
    return {'cpu_count':count,'cpu_model':model,'environment':'colab' if 'COLAB_RELEASE_TAG' in os.environ or 'COLAB_BACKEND_VERSION' in os.environ else 'local',
            'devices':devices,'blenderproc':bproc.__version__,'python':sys.version.split()[0],'numpy':np.__version__,'blender':bpy.app.version_string,'platform':platform.system()}


def guarded_render_init():
    """Avoid resetting an unchanged engine; pinned equivalent RendererUtility settings."""
    import bpy
    scene=bpy.context.scene
    if scene.render.resolution_percentage!=100:scene.render.resolution_percentage=100
    if scene.render.engine!='CYCLES':scene.render.engine='CYCLES'
    if scene.cycles.debug_bvh_type!='STATIC_BVH':scene.cycles.debug_bvh_type='STATIC_BVH'
    if not scene.cycles.debug_use_spatial_splits:scene.cycles.debug_use_spatial_splits=True
    if not scene.render.use_persistent_data:scene.render.use_persistent_data=True


def configure(selection):
    import bpy
    import blenderproc as bproc
    from blenderproc.python.renderer import RendererUtility
    settings=selection['settings'];scene=bpy.context.scene
    if settings['renderer_initialization']=='guarded':RendererUtility.render_init=guarded_render_init
    if settings['device']=='CPU':
        bproc.renderer.set_render_devices(use_only_cpu=True)
    else:
        device=selection['device'];preferences=bpy.context.preferences.addons['cycles'].preferences
        bproc.renderer.set_render_devices(use_only_cpu=False,desired_gpu_device_type=[device['backend']])
        for d in preferences.devices:d.use=d.type!='CPU' and d.id==device['id']
        if scene.cycles.device!='GPU' or not any(d.use and d.type!='CPU' for d in preferences.devices):
            raise RuntimeError('Prepared GPU device unavailable; prepare a fresh execution selection')
    bproc.renderer.set_cpu_threads(settings['threads'])
    mode=settings['denoiser']
    bproc.renderer.set_denoiser('INTEL' if mode.startswith('compositor') else None)
    if mode in ('native-gpu-oidn','native-cpu-oidn'):
        preferences=bpy.context.preferences.addons['cycles'].preferences
        if mode=='native-gpu-oidn' and not preferences.has_oidn_gpu_devices():raise RuntimeError('GPU OIDN capability disappeared; no silent CPU fallback')
        scene.cycles.use_denoising=True;bpy.context.view_layer.cycles.use_denoising=True
        scene.cycles.denoiser='OPENIMAGEDENOISE';scene.cycles.denoising_use_gpu=mode=='native-gpu-oidn'
        scene.cycles.denoising_prefilter=settings['denoiser_prefilter'];scene.cycles.denoising_quality=settings['denoiser_quality']
        scene.cycles.denoising_input_passes=settings['denoiser_input_passes']
    if mode.startswith('compositor'):
        for node in scene.node_tree.nodes:
            if node.type=='DENOISE':node.prefilter=settings['denoiser_prefilter']
    bproc.renderer.set_light_bounces(diffuse_bounces=settings['diffuse_bounces'],glossy_bounces=settings['glossy_bounces'],max_bounces=settings['max_bounces'],transparent_max_bounces=settings['transparent_bounces'])


def evidence(selection):
    import bpy
    from blenderproc.python.renderer import RendererUtility
    scene=bpy.context.scene;prefs=bpy.context.preferences.addons['cycles'].preferences
    return {'selection_identity':selection['identity'],'profile':selection['profile'],'settings':selection['settings'],
            'device':scene.cycles.device,'backend':prefs.compute_device_type,
            'devices':[{'name':d.name,'id':d.id,'type':d.type,'enabled':d.use} for d in prefs.devices],
            'native_denoising':scene.cycles.use_denoising,'native_gpu_denoising':scene.cycles.denoising_use_gpu,
            'native_denoiser':scene.cycles.denoiser,'native_prefilter':scene.cycles.denoising_prefilter,
            'native_quality':scene.cycles.denoising_quality,'native_input_passes':scene.cycles.denoising_input_passes,
            'cycles_seed':scene.cycles.seed,'animated_seed':scene.cycles.use_animated_seed,
            'sample_offset':scene.cycles.sample_offset,
            'guarded_initialization_active':RendererUtility.render_init is guarded_render_init,
            'render_threads':scene.render.threads,'compositor_denoise_nodes':sum(n.type=='DENOISE' for n in scene.node_tree.nodes) if scene.use_nodes else 0}
