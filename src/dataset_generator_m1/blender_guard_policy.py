"""Derive a saved study's resource guards from measured hardware headroom."""
from __future__ import annotations


def adaptive_guards(base, settings, *, total_bytes, available_bytes, gpu_total_mib=None, gpu_free_mib=None):
    """Return explicit limits; memory inputs and fractions are retained by the caller."""
    fractions=('host_available_fraction_for_rss','host_total_fraction_reserved','gpu_total_fraction_reserved')
    if any(not 0 < settings[k] < 1 for k in fractions):
        raise ValueError('Reserve and RSS fractions must be strictly between 0 and 1')
    if total_bytes <= 0 or not 0 < available_bytes <= total_bytes:
        raise ValueError('Invalid host memory measurements')
    minimum=settings['host_minimum_reserve_gib']
    if minimum <= 0 or settings['gpu_minimum_reserve_mib'] < 0 or settings['max_swap_out_mib'] < 0:
        raise ValueError('Invalid resource guard configuration')
    reserve=max(minimum,total_bytes/2**30*settings['host_total_fraction_reserved'])
    rss=min(available_bytes/2**30*settings['host_available_fraction_for_rss'],available_bytes/2**30-reserve)
    if rss <= 0:
        raise ValueError('Insufficient host memory for the requested reserve')
    result={**base,'min_available_gib':reserve,'rss_limit_gib':rss,'max_swap_out_mib':settings['max_swap_out_mib']}
    if gpu_total_mib is not None or gpu_free_mib is not None:
        if gpu_total_mib is None or gpu_free_mib is None or gpu_total_mib <= 0 or not 0 <= gpu_free_mib <= gpu_total_mib:
            raise ValueError('Invalid GPU memory measurements')
        floor=max(settings['gpu_minimum_reserve_mib'],gpu_total_mib*settings['gpu_total_fraction_reserved'])
        if gpu_free_mib <= floor:
            raise ValueError('Insufficient GPU memory for the requested reserve')
        result['min_gpu_free_mib']=floor
    return result
