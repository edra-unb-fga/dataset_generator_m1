"""Shared, explicitly saved guard settings for local study supervisors."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from dataset_generator_m1.models import ExecutionConfig


class GuardSettings(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, allow_inf_nan=False)
    host_available_fraction_for_rss: float = Field(gt=0, lt=1)
    host_total_fraction_reserved: float = Field(gt=0, lt=1)
    host_minimum_reserve_gib: float = Field(gt=0)
    max_swap_out_mib: float = Field(gt=0)
    swap_out_action: Literal['warn', 'abort'] | None = None
    timeout_seconds: float = Field(gt=0)


class Policy(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, allow_inf_nan=False)
    schema_version: int = Field(ge=1, le=1)
    execution: ExecutionConfig
    guards: GuardSettings


def resolve_guards(settings, total, available):
    if not 0 < available <= total:
        raise ValueError('Invalid host memory measurements')
    reserve = max(settings.host_minimum_reserve_gib, total / 2**30 * settings.host_total_fraction_reserved)
    rss = min(available / 2**30 * settings.host_available_fraction_for_rss, available / 2**30 - reserve)
    if rss <= 0:
        raise ValueError('Insufficient available memory for the requested reserve')
    result = {'min_available_gib': reserve, 'rss_limit_gib': rss, 'max_swap_out_mib': settings.max_swap_out_mib}
    if settings.swap_out_action is not None:
        result['swap_out_action'] = settings.swap_out_action
    return result
