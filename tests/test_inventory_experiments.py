import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('inventory_experiments', Path(__file__).parents[1] / 'scripts' / 'inventory_experiments.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_inventory_is_read_only_and_ignores_symlinks(tmp_path):
    run = tmp_path / 'run'
    run.mkdir()
    (run / 'summary.json').write_text('{}')
    (run / 'report.html').write_text('abc')
    external = tmp_path / 'external'
    external.mkdir()
    (external / 'large.txt').write_text('x' * 100)
    (run / 'link').symlink_to(external, target_is_directory=True)
    before = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob('*'))
    result = module.inventory(tmp_path)
    row = next(r for r in result if r['name'] == 'run')
    assert row['bytes'] == 5 and row['files'] == 2
    assert row['report'] and row['evidence'] and 'metadata present' in row['status']
    assert before == sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob('*'))


def test_inventory_reports_limits(tmp_path):
    run = tmp_path / 'run'
    run.mkdir()
    (run / 'child').mkdir()
    assert module.inventory(tmp_path, max_depth=1)[0]['truncated']
    assert module.inventory(tmp_path, max_entries=1)[0]['truncated']
