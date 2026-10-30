import importlib.util
from pathlib import Path
from dataset_generator_m1.blender_pilot import load_config

HELPER = Path(__file__).parent / 'retry_config.py'
spec = importlib.util.spec_from_file_location('retry_config', HELPER)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def test_relative_bundle_assets_resolve_inside_workspace(tmp_path):
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    payload = {'reference_pool':'inputs/reference', 'artwork':['inputs/a.png','inputs/b.png'],
               'grounds':[{'material_file':'inputs/ground.json'}],
               'environments':['inputs/environment.json'], 'treatments':[{'id':'core'}]}
    config_path = module.write_run_config(workspace, payload)
    parsed = load_config(config_path)
    assert config_path.parent == workspace
    assert parsed.reference_pool == workspace / 'inputs/reference'
    assert parsed.artwork == (workspace/'inputs/a.png', workspace/'inputs/b.png')
    assert parsed.grounds[0].material_file == workspace/'inputs/ground.json'
    assert parsed.environments == (workspace/'inputs/environment.json',)
