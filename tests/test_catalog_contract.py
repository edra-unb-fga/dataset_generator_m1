from dataset_generator_m1.assets import build_asset_catalog
from dataset_generator_m1.config import load_profile


def test_catalog_validates_and_maps_all_landing_assets() -> None:
    resolved = load_profile("examples/configs/landing_minimal.yaml")

    catalog = build_asset_catalog(resolved)

    assert len(catalog.backgrounds) == 82
    assert len(catalog.foregrounds) == 18
    assert len(catalog.fingerprint) == 64
    assert {asset.class_name for asset in catalog.foregrounds} == set(resolved.family.classes)
    assert {asset.group for asset in catalog.foregrounds} == {"numeros", "gabaritos"}


def test_catalog_keeps_stable_manometro_class_ids() -> None:
    resolved = load_profile("examples/configs/manometro_minimal.yaml")

    catalog = build_asset_catalog(resolved)

    by_name = {asset.path.name: asset for asset in catalog.foregrounds}
    assert by_name["manometer_59_5.png"].class_id == 2
    assert by_name["manometer_59_5.png"].class_name == "40-60"
