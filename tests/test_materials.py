from io import BytesIO
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

import numpy as np
from PIL import Image
import pytest

from dataset_generator_m1.materials import acquire_material, fetch_material
from dataset_generator_m1.backgrounds import map_planar_texture


def _provider():
    image = BytesIO()
    Image.new("RGB", (16, 16), "gray").save(image, format="JPEG")
    bundle = BytesIO()
    with ZipFile(bundle, "w") as archive:
        for name in ("Color", "NormalGL", "Roughness"):
            archive.writestr(f"GroundTest_1K-JPG_{name}.jpg", image.getvalue())
    payload = bundle.getvalue()
    metadata = {"assets": [{"id": "GroundTest", "downloads": [{"attributes": "1K-JPG", "url": "https://example.invalid/ground.zip", "size": len(payload)}]}]}
    return payload, lambda url: json.dumps(metadata).encode() if "/api/" in url else payload


def test_pinned_material_reuse_never_contacts_network(tmp_path: Path):
    _, fetch = _provider()
    selection = tmp_path / "selection.json"
    result = acquire_material("GroundTest", tmp_path / "materials", selection, fetch=fetch)
    assert result["offline_reuse"] is False
    manifest = json.loads(selection.read_text())
    assert set(manifest["maps"]) == {"color", "normal", "roughness"}
    reused = fetch_material(manifest, tmp_path / "materials", fetch=lambda _: pytest.fail("network contacted"))
    assert reused["offline_reuse"] is True
    (tmp_path / "materials" / "GroundTest" / "color.jpg").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="checksum"):
        fetch_material(manifest, tmp_path / "materials", fetch=lambda _: pytest.fail("network contacted"))


def test_unsafe_archive_never_commits_material(tmp_path: Path):
    bundle = BytesIO()
    with ZipFile(bundle, "w") as archive:
        archive.writestr("../escape.jpg", b"bad")
    payload = bundle.getvalue()
    manifest = {"schema_version": 1, "asset_id": "unsafe", "material_id": "test/unsafe", "maps": {"color": {}},
                "archive": {"url": "https://example.invalid/file.zip", "sha256": hashlib.sha256(payload).hexdigest()}}
    with pytest.raises(ValueError, match="Unsafe"):
        fetch_material(manifest, tmp_path / "output", payload=payload)
    assert not (tmp_path / "output").exists()


def test_planar_coordinates_are_repeatable_and_maps_stay_aligned():
    image = np.arange(8*8*3, dtype=np.float32).reshape(8, 8, 3) / 255
    a = map_planar_texture(image, (32, 24), repeats_x=2, repeats_y=3, rotation_degrees=23)
    b = map_planar_texture(image, (32, 24), repeats_x=2, repeats_y=3, rotation_degrees=23)
    assert a.shape == (24, 32, 3)
    assert np.array_equal(a, b)
