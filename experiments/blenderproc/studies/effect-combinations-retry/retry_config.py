"""Write the pilot configuration beside the bundled, relative input paths."""
import json
from pathlib import Path

def write_run_config(workspace: Path, config: dict) -> Path:
    workspace = Path(workspace)
    target = workspace / 'run-config.json'
    target.write_text(json.dumps(config, indent=2))
    return target
