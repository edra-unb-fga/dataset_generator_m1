# PROTOTYPE — nested placement relationships

Question: should nested scenes use parent-local attachment, independently projected containment, or a
family-declared mixture of both?

Run:

```powershell
uv run python prototypes/nested_placement/run.py
```

The prototype keeps state in memory and writes only an ignored contact sheet at
`outputs/prototypes/nested-placement/contact-sheet.png`. It does not load production assets or modify
production scene planning.
