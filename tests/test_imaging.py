import numpy as np

from dataset_generator_m1.imaging import clip_bbox, rects_intersect, rotate_rgba, visible_bbox


def test_visible_bbox_uses_alpha_threshold():
    image = np.zeros((8, 8, 4), dtype=np.uint8)
    image[2:5, 3:7, 3] = 255

    assert visible_bbox(image) == (3, 2, 7, 5)


def test_circle_rotation_tight_crops_visible_alpha():
    image = np.zeros((20, 20, 4), dtype=np.uint8)
    image[5:15, 8:12] = [255, 255, 255, 255]

    rotated = rotate_rgba(image, 45, "circle")

    assert visible_bbox(rotated) is not None
    assert rotated.shape[0] < 30
    assert rotated.shape[1] < 30


def test_rect_and_clip_helpers():
    assert rects_intersect((0, 0, 10, 10), (9, 9, 20, 20))
    assert not rects_intersect((0, 0, 10, 10), (10, 10, 20, 20))
    assert clip_bbox((-5, 2, 12, 15), 10, 10) == (0, 2, 10, 10)
    assert clip_bbox((-5, -5, -1, -1), 10, 10) is None

