from dataset_generator_m1.config import load_config


def test_load_minimal_config_with_overrides():
    config = load_config(
        "examples/configs/manometro_minimal.yaml",
        {"num_images": 2, "output_dir": "outputs/test-run", "debug": 0},
    )

    assert config.dataset_type == "manometro"
    assert config.num_images == 2
    assert config.data["output"]["image_size"] == [1280, 1280]
    assert config.data["paths"]["foregrounds_dir"] == "foregrounds/manometro_foregrounds"


def test_landing_defaults_to_circle_rotation():
    config = load_config("examples/configs/landing_minimal.yaml")

    rotation = config.data["foreground_affine_transformations"]["rotation"]
    assert rotation["mode"] == "circle"
    assert rotation["angle_range"] == [-180, 180]


def test_foreground_group_weights_cli_override():
    config = load_config(
        "examples/configs/landing_minimal.yaml",
        {"foreground_group_weights": {"numeros": 1.0, "gabaritos": 0.0}},
    )

    assert config.data["sampling"]["foreground_group_weights"] == {"numeros": 1.0, "gabaritos": 0.0}
