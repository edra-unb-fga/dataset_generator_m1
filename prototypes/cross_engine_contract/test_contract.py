import json
from pathlib import Path
import pytest
from pydantic import ValidationError
from contract import Sample

HERE = Path(__file__).parent


def fixture(name):
    return json.loads((HERE / 'fixtures' / name).read_text())


def validate(data):
    return Sample.model_validate_json(json.dumps(data))


def test_engine_evidence_and_unknowns_remain_distinct():
    planar, physical = (validate(fixture(name)) for name in ('planar.json', 'blender.json'))
    assert planar.annotations[0].full.threshold == 8
    assert physical.annotations[0].full.threshold is None
    assert physical.intentional_negative is None and physical.annotations[0].source_instance_id == '2'
    assert planar.annotations[0].full.encoding != physical.annotations[0].full.encoding


def test_contract_rejects_outside_crop_duplicate_id_and_encoding_confusion():
    value = fixture('planar.json')
    value['annotations'][0]['full']['origin_xy'] = [3, 0]
    with pytest.raises(ValidationError): validate(value)
    value = fixture('planar.json')
    value['annotations'].append(value['annotations'][0])
    with pytest.raises(ValidationError): validate(value)
    value = fixture('blender.json')
    value['annotations'][0]['full']['encoding'] = 'cropped-alpha-u8'
    with pytest.raises(ValidationError): validate(value)


def test_unknown_evidence_and_negative_are_not_fabricated():
    value = fixture('blender.json')
    value['annotations'][0]['visible'] = None
    assert validate(value).annotations[0].visible is None
    value['intentional_negative'] = True
    with pytest.raises(ValidationError): validate(value)
