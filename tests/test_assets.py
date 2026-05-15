from pathlib import Path

from dataset_generator_m1.assets import discover_foregrounds


def test_landing_numbers_keep_numeric_suffix_and_gabaritos_collapse():
    assets, class_names = discover_foregrounds("foregrounds/landing_foregrounds", "landing")
    by_name = {Path(asset.path).name: asset.class_name for asset in assets}

    assert by_name["hexagono_3.png"] == "hexagono_3"
    assert by_name["hexagono_4.png"] == "hexagono_4"
    assert by_name["hexagono_gabarito_3.png"] == "hexagono_gabarito"
    assert by_name["hexagono_gabarito_4.png"] == "hexagono_gabarito"
    assert "hexagono_3" in class_names
    assert "hexagono_4" in class_names
    assert "hexagono_gabarito" in class_names


def test_manometro_uses_range_directory_as_class():
    assets, class_names = discover_foregrounds("foregrounds/manometro_foregrounds", "manometro")
    by_name = {Path(asset.path).name: asset.class_name for asset in assets}

    assert by_name["manometer_59_5.png"] == "40-60"
    assert by_name["manometer_20_0.png"] == "20-40"
    assert class_names[:5] == ["0-20", "20-40", "40-60", "60-80", "80-100"]
