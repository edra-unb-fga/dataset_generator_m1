import math
import numpy as np
from dataset_generator_m1.blender_camera import sample_pose, rotation_matrix, ground_geometry, environment_bounds
from dataset_generator_m1.blender_pilot import CameraStudy, EnvironmentGeometrySettings


def test_pose_distribution_determinism_and_rotation():
    settings=CameraStudy().model_dump(mode='json')
    poses=[sample_pose(i,settings) for i in range(10000)]
    assert poses[42]==sample_pose(42,settings)
    assert .83 < np.mean([p['tilt_degrees'] < 30 for p in poses]) < .87
    assert .57 < np.mean([p['tilt_degrees'] < 15 for p in poses]) < .61
    assert all(0 <= p['tilt_degrees'] <= 55 and 0 <= p['yaw_degrees'] < 360 and .5 <= p['ground_spans'] <= 1.5 for p in poses)
    w,x,y,z=poses[0]['quaternion_wxyz']
    quaternion_rotation=np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
                                  [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
                                  [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])
    assert np.allclose(quaternion_rotation,rotation_matrix(poses[0]))
    for p in (poses[0], {'yaw_degrees':42,'tilt_degrees':0,'tilt_direction_degrees':180}):
        r=rotation_matrix(p)
        assert np.allclose(r.T@r,np.eye(3))
        assert math.isclose(np.linalg.det(r),1)
        assert np.allclose((r @ np.array([0,0,-1]))[2],-math.cos(math.radians(p['tilt_degrees'])))


def test_footprint_spans_and_bounded_horizon_fallback():
    settings=CameraStudy().model_dump(mode='json')
    K=np.array([[500,0,256],[0,500,256],[0,0,1]])
    pose={'yaw_degrees':0,'tilt_degrees':0,'tilt_direction_degrees':0}
    r=rotation_matrix(pose)
    result=ground_geometry(np.array([0.,0.,10.]),r,K,(512,512),settings,2,1.25)
    assert math.isclose(result['achieved_spans'],1.25)
    assert result['extent_m']>=40
    pose['tilt_degrees']=65
    result=ground_geometry(rotation_matrix(pose)[:,2]*10,rotation_matrix(pose),K,(512,512),settings,2,1)
    assert result['near_horizon_fallback']
    assert result['extent_m']==settings['extent_bounds_m'][1]


def test_motion_and_distortion_bounds_expand_ground_and_report_clamps():
    settings=CameraStudy().model_dump(mode='json')
    settings['extent_bounds_m']=[1,100]
    K=np.array([[500,0,256],[0,500,256],[0,0,1]])
    r=rotation_matrix({'yaw_degrees':0,'tilt_degrees':0,'tilt_direction_degrees':0})
    position=np.array([0.,0.,10.])
    base=ground_geometry(position,r,K,(512,512),settings,2,1)
    enlarged=ground_geometry(position,r,K,(512,512),settings,2,1,pixel_bounds=(-200,-200,712,712),motion_m=8,distorted=True)
    assert enlarged['required_extent_m']>base['required_extent_m']
    assert enlarged['motion_margin_m']==8 and enlarged['distortion_bounds_used']
    assert enlarged['coverage_guaranteed']
    settings['extent_bounds_m']=[1,10]
    clipped=ground_geometry(position,r,K,(512,512),settings,2,1,motion_m=8)
    assert clipped['extent_clamped'] and not clipped['coverage_guaranteed']


def test_renderer_does_not_overwrite_scene_pose_with_frame_matrix():
    import ast
    from pathlib import Path
    tree=ast.parse(Path('experiments/blenderproc/render.py').read_text())
    build=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='build_scene')
    frame_loop=next(node for node in ast.walk(build) if isinstance(node,ast.For) and isinstance(node.target,ast.Name) and node.target.id=='frame')
    assigned={target.id for node in ast.walk(frame_loop) if isinstance(node,ast.Assign) for target in node.targets if isinstance(target,ast.Name)}
    assert 'pose' not in assigned


def test_environment_bounds_cover_shutter_trajectory_and_surface_clearance():
    settings=EnvironmentGeometrySettings().model_dump(mode='json')
    position=np.array([4.,-3.,5.])
    for speed, shutter in ((0,1), (20,1), (12,.001)):
        bounds=environment_bounds(position,settings,speed,shutter)
        travel=speed*max(1/24,shutter) if speed else 0
        inner_wall=bounds['half_width_m']-settings['wall_thickness_m']/2
        assert inner_wall >= abs(position[0])+travel+settings['camera_horizontal_margin_m']
        assert inner_wall >= abs(position[1])+settings['camera_horizontal_margin_m']
        assert bounds['ceiling_height_m']-settings['wall_thickness_m']/2 >= position[2]+settings['camera_ceiling_margin_m']
        assert bounds['camera_motion_margin_m']==travel


def test_environment_bounds_enclose_target_footprints_as_well_as_camera():
    settings=EnvironmentGeometrySettings().model_dump(mode='json')
    corners=[(10.0,-8.0),(-12.0,3.0)]
    bounds=environment_bounds(np.array([1.,2.,4.]),settings,0,1/60,corners)
    interior=bounds['half_width_m']-settings['wall_thickness_m']/2
    assert bounds['target_extent_m']==12.0
    assert all(interior >= max(abs(x),abs(y))+settings['camera_horizontal_margin_m'] for x,y in corners)


def test_rotated_panel_footprints_detect_real_intersection_not_bounding_box():
    from dataset_generator_m1.blender_camera import panel_footprint, footprints_overlap
    a=panel_footprint((0,0),2,.1,45)
    b=panel_footprint((0,1),2,.1,45)
    assert not footprints_overlap(a,b)  # bounding boxes overlap but rectangles do not
    assert footprints_overlap(a,panel_footprint((.1,.1),2,.1,45))
    assert not footprints_overlap(panel_footprint((0,0),1,1,0),panel_footprint((1,0),1,1,0))
    assert footprints_overlap(panel_footprint((0,0),1,1,0),panel_footprint((.99,0),1,1,0))
