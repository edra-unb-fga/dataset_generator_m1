"""Deterministic scene camera and ground geometry, shared with Blender."""
import math
import numpy as np


def sample_pose(seed, settings):
    rng = np.random.default_rng(seed)
    yaw = rng.uniform(0, 360)
    scale = settings["tilt_scale_degrees"]
    maximum = settings["tilt_max_degrees"]
    tilt = -scale * math.log1p(-rng.random() * (1 - math.exp(-maximum / scale)))
    direction = rng.uniform(0, 360)
    spans = rng.uniform(*settings["ground_spans"])
    azimuth = math.radians(yaw + direction)
    half_tilt, half_yaw = math.radians(tilt)/2, math.radians(yaw)/2
    # Quaternion is tilt about a heading-relative horizontal axis, then heading yaw.
    ax, ay = -math.sin(azimuth), math.cos(azimuth)
    st, ct = math.sin(half_tilt), math.cos(half_tilt)
    sy, cy = math.sin(half_yaw), math.cos(half_yaw)
    quaternion = [ct*cy, st*(ax*cy+ay*sy), st*(ay*cy-ax*sy), ct*sy]
    return {"seed": seed, "quaternion_wxyz": quaternion, "yaw_degrees": float(yaw), "tilt_degrees": float(tilt),
            "tilt_direction_degrees": float(direction), "ground_spans": float(spans)}


def rotation_matrix(pose):
    yaw, tilt, direction = (math.radians(pose[k]) for k in
                            ("yaw_degrees", "tilt_degrees", "tilt_direction_degrees"))
    c, s = math.cos(yaw), math.sin(yaw)
    base = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.]])
    # Tilt direction is expressed in heading-relative ground coordinates.
    d = np.array([math.cos(yaw + direction), math.sin(yaw + direction), 0.])
    axis = np.array([-d[1], d[0], 0.])
    skew = np.array([[0., -axis[2], axis[1]], [axis[2], 0., -axis[0]], [-axis[1], axis[0], 0.]])
    return (np.eye(3) + math.sin(tilt)*skew + (1-math.cos(tilt))*(skew@skew)) @ base


def ground_geometry(position, rotation, K, size, settings, nominal_tile, spans,
                    pixel_bounds=None, motion_m=0, distorted=False):
    """Conservatively bound the ground footprint of a translating camera.

    pixel_bounds encloses all undistorted source samples requested by the lens map,
    expressed in the internal render's pixel coordinates and intrinsics.
    """
    width, height = size
    def hit(u, v, offset=0):
        ray = rotation @ np.array([(u-K[0,2])/K[0,0], -(v-K[1,2])/K[1,1], -1.])
        if ray[2] >= -1e-8: return None
        return position + np.array([offset, 0., 0.]) + ray * (-position[2]/ray[2])
    x0,y0,x1,y1 = pixel_bounds if pixel_bounds is not None else (0,0,width,height)
    corners = [hit(u,v,offset) for offset in (-motion_m,motion_m)
               for u,v in ((x0,y0),(x1,y0),(x1,y1),(x0,y1))]
    left, right = hit(x0,(y0+y1)/2), hit(x1,(y0+y1)/2)
    fallback = any(x is None for x in corners) or left is None or right is None
    min_extent, max_extent = settings["extent_bounds_m"]
    required_extent = None if fallback else 2*max(float(np.max(np.abs(x[:2]))) for x in corners)*settings["footprint_margin"]
    extent = max_extent if fallback else min(max_extent, max(min_extent, required_extent))
    clamped = required_extent is not None and required_extent > max_extent
    view_width = float(np.linalg.norm(right-left)) if left is not None and right is not None else None
    desired = view_width/spans if view_width is not None else nominal_tile
    low, high = settings["tile_bounds_m"]
    tile = max(low, min(high, desired))
    return {"extent_m": extent, "required_extent_m": required_extent,
            "tile_m": tile, "nominal_tile_m": nominal_tile,
            "requested_spans": spans, "achieved_spans": view_width/tile if view_width else None,
            "central_view_width_m": view_width, "near_horizon_fallback": fallback,
            "extent_clamped": clamped, "coverage_guaranteed": not (fallback or clamped),
            "distortion_bounds_used": distorted, "motion_margin_m": motion_m,
            "tile_clamped": tile != desired}


def environment_bounds(position, settings, camera_speed_mps, shutter_seconds, target_corners=()):
    """Enclose the animated X trajectory and leave clearance to interior surfaces.

    The symmetric full-shutter travel exceeds either centered or one-sided shutter
    exposure and also includes both keyed camera poses at frames -1 and 1.
    """
    motion = camera_speed_mps * max(1 / 24, shutter_seconds) if camera_speed_mps else 0
    half_thickness = settings['wall_thickness_m'] / 2
    half = max(settings['min_half_width_m'],
               abs(float(position[0])) + motion + settings['camera_horizontal_margin_m'] + half_thickness,
               abs(float(position[1])) + settings['camera_horizontal_margin_m'] + half_thickness)
    target_extent = max((max(abs(float(x)), abs(float(y))) for x, y in target_corners), default=0.)
    if target_extent:
        half = max(half, target_extent + settings['camera_horizontal_margin_m'] + half_thickness)
    height = max(settings['min_room_height_m'],
                 float(position[2]) + settings['camera_ceiling_margin_m'] + half_thickness)
    return {'half_width_m': half, 'ceiling_height_m': height, 'camera_motion_margin_m': motion,
            'target_extent_m': target_extent}


def panel_footprint(center, width, aspect, angle_degrees):
    """Return the four world-plane corners of a rigid rectangular panel."""
    angle = math.radians(angle_degrees)
    c, s = math.cos(angle), math.sin(angle)
    return np.array([(center[0]+x*c-y*s, center[1]+x*s+y*c)
                     for x,y in ((-width/2,-width*aspect/2), (width/2,-width*aspect/2),
                                 (width/2,width*aspect/2), (-width/2,width*aspect/2))])


def footprints_overlap(first, second):
    """Separating-axis test; touching at an edge does not constitute overlap."""
    for poly in (first, second):
        for edge in np.roll(poly,-1,axis=0)-poly:
            axis=np.array([-edge[1],edge[0]])
            left=first@axis;right=second@axis
            if left.max() <= right.min()+1e-12 or right.max() <= left.min()+1e-12:
                return False
    return True


def ground_uv(x, y, tile, angle_degrees, offset):
    """World XY to UV with a rotated tangent frame and UV-space offset."""
    angle=math.radians(angle_degrees);c=math.cos(angle);s=math.sin(angle)
    return ((c*x-s*y)/tile+offset[0],(s*x+c*y)/tile+offset[1])
