# Dataset Generator M1

Synthetic YOLO dataset generator for the `manometro` and `landing` dataset families.

## Install

```powershell
uv venv .venv
.venv\Scripts\activate
uv pip install -e .[dev]
```

## Generate

```powershell
python -m dataset_generator_m1 generate --config examples/configs/manometro_minimal.yaml
python -m dataset_generator_m1 generate --config examples/configs/landing_minimal.yaml
```

Useful overrides:

```powershell
python -m dataset_generator_m1 generate --config examples/configs/manometro_minimal.yaml --num-images 50 --output-dir outputs/manometro-smoke --debug 10
```

Outputs are written as:

```text
<output_dir>/
  images/
  labels/
  debug/
  data.yaml
  manifest.json
```

The implementation follows the canonical spec in `docs/NEW ARCHITECTURE.md`; config defaults and augmentation details are documented in `docs/CONFIG_SCHEMA.md` and `docs/ARCHITECTURE_VERBOSE.md`.
