"""Isolated v1 candidate contract; no production adapter or file IO."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True)


class Evidence(Strict):
    archive: str = Field(min_length=1)
    archive_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    key: str = Field(min_length=1)
    encoding: Literal['cropped-alpha-u8', 'binary-array']
    origin_xy: tuple[int, int] | None
    shape_hw: tuple[int, int]
    threshold: int | None = Field(ge=0, le=255)

    @model_validator(mode='after')
    def encoding_contract(self):
        if min(self.shape_hw) < 1:
            raise ValueError('Evidence shape must be positive')
        if self.encoding == 'cropped-alpha-u8':
            if self.origin_xy is None or min(self.origin_xy) < 0 or self.threshold is None:
                raise ValueError('Alpha crop requires origin and threshold')
        elif self.origin_xy is not None or self.threshold is not None:
            raise ValueError('Binary array has no crop origin or alpha threshold')
        return self


class Annotation(Strict):
    instance_id: str = Field(min_length=1)
    source_instance_id: str | None
    class_id: int = Field(ge=0)
    class_name: str = Field(min_length=1)
    bbox_xyxy: tuple[int, int, int, int] | None
    full: Evidence | None
    visible: Evidence | None


class Sample(Strict):
    version: Literal['cross-engine-sample-v1']
    engine: Literal['planar-2d', 'blenderproc-3d']
    sample_id: str = Field(min_length=1)
    source_identity: str = Field(min_length=1)
    image_uri: str = Field(min_length=1)
    image_sha256: str | None = Field(pattern=r'^[0-9a-f]{64}$')
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    intentional_negative: bool | None
    source_revision: str | None
    annotations: tuple[Annotation, ...]

    @model_validator(mode='after')
    def invariants(self):
        ids = [a.instance_id for a in self.annotations]
        if len(ids) != len(set(ids)):
            raise ValueError('Duplicate instance ID')
        classes = {}
        for a in self.annotations:
            if a.class_id in classes and classes[a.class_id] != a.class_name:
                raise ValueError('Class ID maps to inconsistent names')
            classes[a.class_id] = a.class_name
            if a.bbox_xyxy is not None:
                x1,y1,x2,y2 = a.bbox_xyxy
                if not (0 <= x1 < x2 <= self.width and 0 <= y1 < y2 <= self.height):
                    raise ValueError('Bounding box outside image')
            for e in (a.full,a.visible):
                if e is None:
                    continue
                expected = 'cropped-alpha-u8' if self.engine == 'planar-2d' else 'binary-array'
                if e.encoding != expected:
                    raise ValueError('Evidence encoding does not match engine')
                h,w = e.shape_hw
                if e.origin_xy is None:
                    if (h,w) != (self.height,self.width):
                        raise ValueError('Binary mask must cover image')
                else:
                    x,y = e.origin_xy
                    if x+w > self.width or y+h > self.height:
                        raise ValueError('Alpha crop outside image')
        if self.intentional_negative is True and self.annotations:
            raise ValueError('Intentional negative cannot contain annotations')
        return self
