---
title: Install r2x-reeds
---

Use Python **3.11–3.13** (`>=3.11,<3.14`). Choose the environment that will execute
your parser; project Python and the CLI's managed Python are separate environments.

## Published Python package

Create and activate a virtual environment with a supported Python, then install
from [PyPI](https://pypi.org/project/r2x-reeds/):

```bash
python -m pip install r2x-reeds
python -m pip show r2x-reeds
```

Follow the [pip-based fixture tutorial](/r2x-reeds/tutorials/parse-run/) for complete
environment setup and a separate data download. Fixtures are not installed package
resources. The library has no standalone `r2x-reeds` executable.

For a project already managed with uv, `uv add r2x-reeds` is an alternative.
Source checkouts are a contributor workflow, not the normal package-install path.

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
