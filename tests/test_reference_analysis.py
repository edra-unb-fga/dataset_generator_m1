import json

import pytest
from PIL import Image

from dataset_generator_m1.reference_analysis import audit_references, check_projection


def projection(tmp_path, **changes):
    value = {"schema_version": 1, "camera_matrix": [[100, 0, 100], [0, 100, 100], [0, 0, 1]],
             "world_to_camera": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 2], [0, 0, 0, 1]],
             "image_size": [200, 200], "target_size_m": [2, 2],
             "observed_corners_px": [[50, 50], [150, 50], [150, 150], [50, 150]], **changes}
    path = tmp_path / "projection.json"
    path.write_text(json.dumps(value))
    return check_projection(path, tmp_path / "output")


def test_known_projection_has_zero_reprojection_residual(tmp_path):
    result = projection(tmp_path)
    assert result["residuals"]["rms_px"] == 0
    assert result["projected_corners_px"] == [[50, 50], [150, 50], [150, 150], [50, 150]]


@pytest.mark.parametrize("changes", [{"target_size_m": [-1, 1]}, {"camera_matrix": [[0]*3]*3},
    {"world_to_camera": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, -2], [0, 0, 0, 1]]},
    {"world_to_camera": [[2, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 2], [0, 0, 0, 1]]}])
def test_invalid_camera_is_rejected_before_output(tmp_path, changes):
    with pytest.raises(ValueError):
        projection(tmp_path, **changes)
    assert not (tmp_path / "output").exists()


def test_reference_audit_reports_observables_duplicates_and_unknowns(tmp_path):
    Image.new("RGB", (80, 40), "#336699").save(tmp_path / "image.png")
    manifest = {"schema_version": 1, "domain": "synthetic", "role": "development", "images": [
        {"id": "a", "path": "image.png", "annotations": [{"class_name": "pad", "bbox": [10, 5, 20, 10]}]},
        {"id": "b", "path": "image.png"}]}
    path = tmp_path / "references.json"
    path.write_text(json.dumps(manifest))
    result = audit_references(path, tmp_path / "report")
    assert result["duplicate_groups"] == [["a", "b"]]
    assert result["images"][0]["capture_session"] == "unknown"
    assert result["images"][0]["targets"][0]["relative_box_area"] == pytest.approx(.0625)
    assert result["images"][0]["observables"]["laplacian_variance_proxy"] == 0
