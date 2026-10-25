# Blue and yellow base artwork

These PNGs faithfully render the SVG artwork supplied by the user on 2026-10-24. The unchanged SVG
sources are retained in `sources/`; asset discovery only loads raster images, so the sources do not
create duplicate foregrounds.

- `landing-base.png`: 500×500 square, yellow perimeter, yellow circle outline and yellow cross.
- `takeoff-base.png`: 1000×750 rectangle (4:3), blue outer panel, solid yellow inset, blue center disk
  and yellow cross.

Both use the source colors blue `#25408f` and yellow `#fde900` and label the complete opaque panel as
class `pad`. They replace the earlier repository-authored `synthetic-square.png` and
`synthetic-rectangle.png` substitutes. Historical benchmark galleries still show those substitutes.

Regenerate the PNGs without adding a dataset-generation runtime dependency:

```sh
uv run --no-project --with cairosvg==2.9.1 python scripts/generate_pad_fixtures.py
```

Use other production images through a composer foreground-root override.
