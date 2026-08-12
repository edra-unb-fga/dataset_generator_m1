# User Composers

The guided `start` and `configure` workflows write durable, user-owned composers here. Review these
YAML files like source code: resolve and validate them, inspect their diff, and commit configurations
that should reproduce future runs.

Use `configs/local/` for disposable experiments or machine-local paths. That directory is ignored.
Promote reusable, reviewed subject configuration through `catalog promote` rather than duplicating it
across many composers.

Before committing a composer:

```powershell
uv run python -m dataset_generator_m1 resolve --config configs/my-run.yaml
uv run python -m dataset_generator_m1 validate --config configs/my-run.yaml
```
