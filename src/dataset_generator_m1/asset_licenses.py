"""Declared license provenance for locally supplied materials and environments.

CC0-1.0 keeps its historical shorthand. Other assets must state a source and license
URL, creator, attribution and restrictions, plus explicit booleans for local
rendering/dataset use and raw asset redistribution. These declarations document
user-supplied rights; they are not independent legal verification.
"""
from urllib.parse import urlparse


def validate_asset_license(record, *, redistribution=False):
    license_name = record.get('license')
    if license_name == 'CC0-1.0':
        return
    if not isinstance(license_name, str) or not license_name.strip():
        raise ValueError('Asset license must be explicitly declared')
    for key in ('author', 'attribution', 'restrictions', 'source_url', 'license_url'):
        if not isinstance(record.get(key), str) or not record[key].strip():
            raise ValueError('Non-CC0 asset requires explicit ' + key)
    for key in ('source_url', 'license_url'):
        parsed = urlparse(record[key])
        if parsed.scheme not in ('http', 'https') or not parsed.netloc:
            raise ValueError('Non-CC0 asset requires an HTTP(S) ' + key)
    for key in ('allow_local_render_and_dataset', 'allow_redistribution'):
        if type(record.get(key)) is not bool:
            raise ValueError('Non-CC0 asset requires explicit boolean ' + key)
    if not record['allow_local_render_and_dataset']:
        raise ValueError('Asset does not permit local rendering and dataset use')
    if redistribution and not record['allow_redistribution']:
        raise ValueError('Asset does not permit raw redistribution in portable bundles')
