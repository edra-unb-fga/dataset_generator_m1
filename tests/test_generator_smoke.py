from dataset_generator_m1.config import load_config
from dataset_generator_m1.generator import DatasetGenerator


def test_generator_smoke_writes_expected_files(tmp_path):
    config = load_config(
        "examples/configs/manometro_minimal.yaml",
        {"num_images": 1, "output_dir": str(tmp_path), "debug": 1},
    )

    manifest = DatasetGenerator(config).generate()

    assert len(manifest["samples"]) == 1
    assert (tmp_path / "images" / "image_000000.jpg").exists()
    assert (tmp_path / "labels" / "image_000000.txt").exists()
    assert (tmp_path / "debug" / "image_000000_overlay.jpg").exists()
    assert (tmp_path / "data.yaml").exists()
    assert (tmp_path / "manifest.json").exists()

