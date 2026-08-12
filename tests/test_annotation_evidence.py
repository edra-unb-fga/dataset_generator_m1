from __future__ import annotations

import io

import numpy as np
import pytest

from dataset_generator_m1.annotation_evidence import (
    decode_mask_evidence,
    encode_mask_evidence,
    visible_coverages,
)


def test_mask_evidence_round_trips_cropped_full_and_visible_coverage() -> None:
    outer = np.zeros((24, 30), dtype=np.uint8)
    outer[3:20, 4:26] = 255
    outer[3, 4:26] = 64
    inner = np.zeros_like(outer)
    inner[8:15, 11:19] = 255
    visible = visible_coverages((outer, inner))

    encoded = encode_mask_evidence(
        (outer, inner),
        visible,
        ("instance-000", "instance-001"),
        image_size=(30, 24),
        alpha_threshold=8,
    )
    decoded = decode_mask_evidence(encoded.archive_bytes, encoded.manifest)

    assert encoded.manifest["format"] == "npz-cropped-alpha-v1"
    assert encoded.manifest["instances"][0]["visible"]["same_as"] is None
    assert encoded.manifest["instances"][1]["visible"]["same_as"] == "full"
    assert np.array_equal(decoded["instance-000"]["full"], outer)
    assert np.array_equal(decoded["instance-000"]["visible"], visible[0])
    assert np.array_equal(decoded["instance-001"]["full"], inner)
    assert np.array_equal(decoded["instance-001"]["visible"], inner)
    assert len(encoded.archive_bytes) < outer.nbytes + inner.nbytes


def test_mask_evidence_rejects_corrupt_or_unsafe_archives() -> None:
    mask = np.full((8, 8), 255, dtype=np.uint8)
    encoded = encode_mask_evidence((mask,), (mask,), ("instance-000",), image_size=(8, 8), alpha_threshold=8)

    with pytest.raises(ValueError, match="hash"):
        decode_mask_evidence(encoded.archive_bytes[:-4] + b"nope", encoded.manifest)

    unsafe = io.BytesIO()
    np.savez_compressed(unsafe, i000_full=np.array([{"unsafe": True}], dtype=object))
    unsafe_manifest = dict(
        encoded.manifest,
        sha256=__import__("hashlib").sha256(unsafe.getvalue()).hexdigest(),
        byte_count=len(unsafe.getvalue()),
    )
    with pytest.raises(ValueError, match="pickle|dtype|object"):
        decode_mask_evidence(unsafe.getvalue(), unsafe_manifest)


def test_mask_evidence_validates_identity_and_shape_contract() -> None:
    mask = np.full((8, 8), 255, dtype=np.uint8)
    with pytest.raises(ValueError, match="instance IDs"):
        encode_mask_evidence((mask,), (mask,), (), image_size=(8, 8), alpha_threshold=8)
    with pytest.raises(ValueError, match="shape"):
        encode_mask_evidence((mask,), (np.ones((9, 8), np.uint8),), ("instance-000",), image_size=(8, 8), alpha_threshold=8)
