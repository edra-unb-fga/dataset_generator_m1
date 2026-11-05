"""Render Markdown review documents for the local report preview.

Keep the response at the Markdown file's original URL so relative links and
images continue to resolve. Raw HTML is escaped because review content can
contain externally sourced text.
"""

from html import escape

from markdown_it import MarkdownIt


def render_review_markdown(source: str, title: str) -> bytes:
    content = MarkdownIt("commonmark", {"html": False}).enable("table").render(source)
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title><style>
:root {{ color-scheme: light dark; font-family: system-ui, sans-serif; line-height: 1.6 }}
body {{ margin: 0; background: #f5f4ef; color: #1b2530 }}
main {{ max-width: 76ch; margin: auto; padding: 1.5rem 1.25rem 4rem; overflow-wrap: anywhere }}
a {{ color: #075c83 }} h1,h2,h3 {{ line-height: 1.2; margin-top: 1.6em }}
pre {{ overflow-x: auto; padding: 1rem; background: #e8edee; border-radius: .4rem }}
code {{ font-family: ui-monospace, monospace; font-size: .9em }}
table {{ display: block; overflow-x: auto; border-collapse: collapse; max-width: 100% }}
th,td {{ padding: .5rem .7rem; border: 1px solid #a4b0b5; text-align: left }}
blockquote {{ border-left: .25rem solid #7d9da9; margin-left: 0; padding-left: 1rem }}
img {{ max-width: 100%; height: auto }}
@media (prefers-color-scheme: dark) {{ body {{ background: #111a1d; color: #e4eded }}
a {{ color: #87d6f4 }} pre {{ background: #24353b }} }}
</style></head><body><main>{content}</main></body></html>"""
    return page.encode("utf-8")
