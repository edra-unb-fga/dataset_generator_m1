import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from study_foreground_context import DEFAULT_MATRIX, load_matrix


def test_matrix_is_explicit_and_hashes_original_bytes():
    matrix, raw, sha = load_matrix(DEFAULT_MATRIX)
    assert sha == hashlib.sha256(raw).hexdigest()
    assert matrix['variants']['baseline'] is None
    assert matrix['seeds']['development'] != matrix['seeds']['reserved']
    assert matrix['variants']['broad']['strength'] == [0.5, 1.5]


@pytest.mark.parametrize('change', ['same-seed', 'missing-parameter', 'unsafe-name'])
def test_invalid_matrix_rejected(tmp_path, change):
    matrix = json.loads(DEFAULT_MATRIX.read_text())
    if change == 'same-seed':
        matrix['seeds']['reserved'] = matrix['seeds']['development']
    elif change == 'missing-parameter':
        del matrix['variants']['restrained']['strength']
    else:
        matrix['variants']['../bad'] = matrix['variants']['restrained']
    path = tmp_path / 'matrix.json'
    path.write_text(json.dumps(matrix))
    with pytest.raises(ValueError):
        load_matrix(path)
