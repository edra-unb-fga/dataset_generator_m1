import numpy as np

from dataset_generator_m1.assets import build_asset_catalog
from dataset_generator_m1.backgrounds import BackgroundSynthesizer
from dataset_generator_m1.config import load_profile


def test_named_background_recipe_returns_valid_canvas_and_provenance() -> None:
    resolved = load_profile("examples/configs/landing_minimal.yaml")
    catalog = build_asset_catalog(resolved)
    synthesizer = BackgroundSynthesizer(catalog, resolved.recipes)

    result = synthesizer.synthesize("mask_multiband", (160, 96), np.random.default_rng(11))

    assert result.image.shape == (96, 160, 3)
    assert result.image.dtype == np.uint8
    assert result.recipe_id == "mask_multiband"
    assert result.source_assets
    assert result.recipe_version == 1
    assert len(result.graph_hash) == 64
    assert 0.0 <= result.qa["nearest_source_similarity"] <= 1.0
    assert result.node_timings_ns.keys() == {node.id for node in resolved.recipes.recipes["mask_multiband"].nodes}
    assert result.qa["finite"] is True
    assert result.qa["uncovered_fraction"] == 0.0


def test_displacement_recipe_is_bounded_and_auditable() -> None:
    resolved = load_profile("examples/configs/manometro_minimal.yaml")
    catalog = build_asset_catalog(resolved)
    synthesizer = BackgroundSynthesizer(catalog, resolved.recipes)

    result = synthesizer.synthesize("displaced", (128, 128), np.random.default_rng(3))

    assert result.image.shape == (128, 128, 3)
    assert 0.0 <= result.qa["clipping_fraction"] <= 1.0
    assert "warped" in result.sampled_parameters
