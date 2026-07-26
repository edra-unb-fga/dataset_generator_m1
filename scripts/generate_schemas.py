from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dataset_generator_m1.config import generated_json_schemas  # noqa: E402


def main() -> None:
    output = ROOT / "docs" / "schema"
    output.mkdir(parents=True, exist_ok=True)
    for name, schema in generated_json_schemas().items():
        (output / f"{name}.schema.json").write_text(
            json.dumps(schema, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
