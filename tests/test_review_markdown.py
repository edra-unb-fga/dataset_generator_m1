import importlib.util
from pathlib import Path


def test_review_markdown_renders_tables_code_links_and_escapes_html():
    path = Path(__file__).resolve().parents[1] / "scripts" / "review_markdown.py"
    spec = importlib.util.spec_from_file_location("review_markdown", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    page = module.render_review_markdown(
        '# Review\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n'
        '[Image](images/example.png)\n\n```python\nx = 1\n```\n\n<script>alert(1)</script>',
        'Review & results',
    ).decode()
    assert '<h1>Review</h1>' in page
    assert '<table>' in page and '<td>2</td>' in page
    assert 'href="images/example.png"' in page
    assert '<code class="language-python">' in page
    assert '<script>' not in page and '&lt;script&gt;' in page
    assert '<title>Review &amp; results</title>' in page
