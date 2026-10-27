import json
import os
from pathlib import Path
import subprocess
import sys


def test_small_study_reports_matched_geometry_and_source_evidence(tmp_path):
    matrix = json.loads(Path('experiments/planar/linear-compositing-study.json').read_text())
    matrix.update(image_size=[96, 96], subjects=['generic-rgba'])
    matrix_path = tmp_path / 'matrix.json'
    matrix_path.write_text(json.dumps(matrix))
    output = tmp_path / 'study'
    env = dict(os.environ, PYTHONPATH='src')
    subprocess.run([sys.executable, 'scripts/study_linear_compositing.py', '--matrix', str(matrix_path), '--output', str(output)],
                   check=True, env=env, capture_output=True, text=True)
    summary = json.loads((output / 'summary.json').read_text())
    assert summary['fixture_count'] == 2 and summary['rendered_images'] == 6
    for fixture in summary['fixtures']:
        assert fixture['foreground_source']['logical_path'] == 'study/generic-rgba.png'
        assert fixture['background_source_assets'] and fixture['background_graph_hash']
        assert fixture['treatments']['linear-shade']['comparison_baseline'] == 'linear'
        for result in fixture['treatments'].values():
            assert result['annotation_equal'] and result['masks_equal']
            assert (output / result['image']).is_file() and (output / result['crop']).is_file()
    assert (output / 'index.html').is_file()
