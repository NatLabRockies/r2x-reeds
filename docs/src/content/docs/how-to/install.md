---
title: Install r2x-reeds
---

Use Python **3.11–3.13** (`>=3.11,<3.14`). Choose the environment that will execute
your parser; project Python and the CLI's managed Python are separate environments.

## Python project

From a project with a `pyproject.toml`:

```bash
uv add r2x-reeds
uv run python -c "from r2x_reeds import ReEDSConfig; print(ReEDSConfig(solve_year=2030, weather_year=2012).primary_solve_year)"
# 2030
```

Alternatively, in an active virtual environment use `python -m pip install r2x-reeds`.
This is a library/plugin package, not a standalone command-line executable.

## CLI runtime

Install [r2x-cli](https://github.com/NatLabRockies/r2x-cli#install) and check its
managed Python before installing the plugin:

```bash
r2x --version
r2x python show
r2x install r2x-reeds
r2x list r2x-reeds
r2x run reeds-parser --help
```

If the CLI reports missing managed Python, use `r2x python install` before installing
plugins. The list should include `reeds-parser` and the transform entry points.
See [CLI pipeline](/r2x-reeds/how-to/reeds-to-x-cli/) for a minimal run.

## Source checkout

```bash
git clone https://github.com/NatLabRockies/r2x-reeds.git
cd r2x-reeds
uv sync --locked --all-groups
```

Verify with `uv run --locked python -c "import r2x_reeds; print(r2x_reeds.__version__)"`.
See [documentation versions](/r2x-reeds/versions/) when comparing older releases.
