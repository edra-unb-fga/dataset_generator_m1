"""Rendering/annotation upgrade boundary; old pools remain readable, never mixed by resume."""
RENDERER_SEMANTICS = 'planar-surface-v3.1'


def contract_profile(profile) -> dict:
    """Keep omitted legacy resampling byte-compatible with pre-option contracts.

    Legacy-equivalent default options are elided. Other defaults and explicit
    source-file hashes keep their historical strict-resume meaning.
    """
    payload = profile.model_dump(mode="json")
    if payload["scene"].get("foreground_resampling") == "legacy":
        payload["scene"].pop("foreground_resampling")
    if payload["scene"].get("compositing") == "legacy":
        payload["scene"].pop("compositing")
    return payload


def derived_profile_payload(payload: dict) -> dict:
    """Keep legacy derived workflow hashes compatible with their historical payload.

    Those workflows historically included foreground_resampling even in legacy mode;
    only the newly added default compositing field is omitted here.
    """
    result = {**payload, "scene": dict(payload["scene"])}
    if result["scene"].get("compositing") == "legacy":
        result["scene"].pop("compositing")
    return result
