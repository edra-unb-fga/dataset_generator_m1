# Pinned materials and planar mapping

Acquire one reviewed small material bundle, retaining actual maps rather than preview URLs:

```powershell
uv run python -m dataset_generator_m1 materials acquire --asset Ground068 --resolution 1K-JPG --output-dir outputs/materials --manifest-file configs/local/Ground068-material.json --output-format json
uv run python -m dataset_generator_m1 materials fetch --manifest-file configs/local/Ground068-material.json --output-dir outputs/materials --output-format json
```

The acquisition command queries the official [ambientCG API](https://docs.ambientcg.com/api/v3/assets/)
for a specific ID/resolution. [ambientCG licences downloadable assets and previews as CC0](https://docs.ambientcg.com/license/).
The saved selection pins the archive URL/hash, map members/hashes, roles, provider, licence, resolution
and reported dimensions. Zero provider dimensions mean unknown physical scale. Normal maps use OpenGL
conventions. Acquisition is bounded to three requests per download, 64 MiB compressed, 160 MiB expanded
and 8192² pixels per map; choose smaller assets rather than bypassing the budget silently.

Raw bundles live under ignored outputs. `fetch` verifies an existing bundle without network access,
or validates the pinned archive and maps before committing a new bundle. It refuses changed hashes,
unsafe ZIP members and existing material roots with different provenance. Selection manifests may be
reviewed and versioned outside `configs/local`; raw data is not promoted automatically.

Each bundle supplies `background-catalog.yaml`: only `color.jpg` is a photographic background;
normal/roughness/height/AO are data maps excluded from ordinary RGB sampling. They share a material ID
so known derivatives remain together when partitioning sources. Original colour maps are not blended
with normal-map colours.

Use a local composer with background root `outputs/materials/Ground068` and its catalog file. Select
`examples/configs/texture_recipes.yaml` as the recipe catalog and `{planar: 1.0}` as mixing weights.
The `texture_map` node uses periodic UV coordinates with separate repetition, orientation and offsets,
then the ordinary scene homography projects the textured ground and foreground together. Parameters
and source/material identities remain in sample evidence. Repetition is image-relative until physical
dimensions and camera calibration are supplied. Repetition can reveal seams and is not always more
plausible than a crop; review texture scale and aliasing.

Production rendering currently uses colour maps. Normal/roughness lighting is a retained prototype,
pending a reviewed visual/cost decision. It does not change production masks or add displacement.
