import pytest
from dataset_generator_m1.blender_guard_policy import adaptive_guards

SETTINGS={'host_available_fraction_for_rss':.8,'host_total_fraction_reserved':.1,'host_minimum_reserve_gib':2,'gpu_total_fraction_reserved':.08,'gpu_minimum_reserve_mib':512,'max_swap_out_mib':16}


def test_guards_scale_with_current_hardware_and_preserve_other_limits():
    limits=adaptive_guards({'probe_timeout_seconds':300},SETTINGS,total_bytes=50*2**30,available_bytes=40*2**30,gpu_total_mib=24000,gpu_free_mib=23000)
    assert limits['min_available_gib']==5 and limits['rss_limit_gib']==32
    assert limits['min_gpu_free_mib']==1920 and limits['probe_timeout_seconds']==300
    smaller=adaptive_guards({},SETTINGS,total_bytes=8*2**30,available_bytes=6*2**30)
    assert smaller['min_available_gib']==2 and smaller['rss_limit_gib']==4


def test_insufficient_headroom_and_invalid_fractions_fail_closed():
    with pytest.raises(ValueError,match='Insufficient host'):adaptive_guards({},SETTINGS,total_bytes=8*2**30,available_bytes=2*2**30)
    with pytest.raises(ValueError,match='Insufficient GPU'):adaptive_guards({},SETTINGS,total_bytes=8*2**30,available_bytes=6*2**30,gpu_total_mib=24000,gpu_free_mib=100)
    with pytest.raises(ValueError,match='fractions'):adaptive_guards({},dict(SETTINGS,host_available_fraction_for_rss=1.5),total_bytes=8*2**30,available_bytes=6*2**30)
