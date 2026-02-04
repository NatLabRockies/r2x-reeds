(installation)=

# Installation

The only pre-requisite to install r2x-reeds is [Python 3.11](https://www.python.org/downloads/release/python-3110/) or greater.

## Python version support

Python 3.11, 3.12, 3.13.

## Installation options

R2X ReEDS is available to install on [PyPI](https://pypi.org/project/r2x-reeds/) and can be installed using any python package manager of your preference, but we recommend using [uv](https://docs.astral.sh/uv/getting-started/installation/).

### Installation with uv

```console
# Install as a tool
uv tool install r2x-reeds

# Or add to a project
uv add r2x-reeds
```

### Installation with pip

```console
# Install system-wide
pip install r2x-reeds

# Or in a virtual environment
python -m pip install r2x-reeds
```

## Upgrading options

### Upgrading with uv

```console
uv pip install --upgrade r2x-reeds
```

### Upgrading with pip

```console
python -m pip install --upgrade r2x-reeds
```

## Verify installation

Check that R2X ReEDS is installed correctly:

```python
import r2x_reeds
print(f"R2X ReEDS version: {r2x_reeds.__version__}")
```

## Next steps

See the [how-to guides](how-tos/index.md) for practical usage examples or check out the [API documentation](references/index.md) for detailed reference information.
