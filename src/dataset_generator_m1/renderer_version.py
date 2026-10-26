"""Rendering/annotation upgrade boundary; old pools remain readable, never mixed by resume."""
RENDERER_SEMANTICS = 'planar-surface-v3.1'


def contract_profile(profile) -> dict:
    """Keep omitted legacy resampling byte-compatible with pre-option contracts.

    Only this newly introduced default is elided. Other defaults and explicit
    source-file hashes keep their historical strict-resume meaning.
    """
    payload = profile.model_dump(mode="json")
    if payload["scene"].get("foreground_resampling") == "legacy":
        payload["scene"].pop("foreground_resampling")
    return payload
