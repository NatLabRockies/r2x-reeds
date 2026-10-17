<img src="./docs/src/assets/r2x-logo-full-square.svg" alt="R2X framework logo" align="left" width="220px" height="220px" hspace="10"/>
<img align="left" alt="" width="0" height="220px" hspace="10"/>

#### r2x-reeds
<p><small>ReEDS parser and transforms for model interoperability.</small></p>

[![CI](https://github.com/NatLabRockies/r2x-reeds/actions/workflows/ci.yaml/badge.svg)](https://github.com/NatLabRockies/r2x-reeds/actions/workflows/ci.yaml) [![PyPI](https://img.shields.io/pypi/v/r2x-reeds?label=PyPI&color=0079c2&logo=pypi)](https://pypi.org/project/r2x-reeds/) [![Last commit](https://img.shields.io/github/last-commit/NatLabRockies/r2x-reeds?style=flat-square)](https://github.com/NatLabRockies/r2x-reeds/commits/main) [![Docs](https://img.shields.io/badge/docs-guides-0079c2?style=flat-square)](docs/README.md)
<br/>
[![Python 3.11–3.13](https://img.shields.io/badge/Python-3.11--3.13-3776ab?logo=python&logoColor=white)](docs/src/content/docs/getting-started/installation.md) [![Managed with uv](https://img.shields.io/badge/managed%20with-uv-6f42c1)](https://docs.astral.sh/uv/) [![BSD 3-Clause](https://img.shields.io/badge/license-BSD--3--Clause-blue.svg)](./LICENSE.txt)

<br clear="left">

ReEDS parser and transforms for the R2X plugin framework. Read ReEDS inputs and
outputs into an R2X system, then apply optional modifiers before translation by
separate target packages.

The [ReEDS model](https://github.com/ReEDS-Model/ReEDS) produces the capacity-expansion runs consumed here. `r2x-reeds` parses those results and applies optional system modifiers; it does not solve the ReEDS model.

## Quick Start

### Install

Use Python 3.11–3.13 in an active virtual environment:

```bash
python -m pip install r2x-reeds
```

Follow [parse, modify and reload a ReEDS fixture](docs/src/content/docs/tutorials/parse-run.md)
for environment setup and a separate public Pacific data download, then build a system, inspect an hourly profile,
split generators and reload the saved result. The verified fixture has 11 regions,
292 generators before splitting and 673 afterward.

For CLI workflows, [install the plugin](docs/src/content/docs/getting-started/installation.md)
and use the [parser pipeline](docs/src/content/docs/how-to/reeds-to-x-cli.md).
[Saved-system inspection](docs/src/content/docs/how-to/inspect-system.md) covers
both Python and `r2x read`. Parser upgrades can modify input files; use a working copy.

## Documentation

- [Getting started](docs/src/content/docs/getting-started/installation.md): installation, environment and verification.
- [System modifiers](docs/src/content/docs/getting-started/system-modifiers.md): all available sysmods, prerequisites and next steps.
- [Prepare a PCM handoff](docs/src/content/docs/how-to/pcm-handoff.md): modifier recipes, optional profiles, cost-unit checks and inspection.
- [Tutorials](docs/src/content/docs/tutorials/parse-run.md): parse and inspect a run.
- [How-to guides](docs/src/content/docs/how-to/reeds-to-x-cli.md): CLI and Python workflows.
- [Reference/API](docs/src/content/docs/reference/python-api.md): public imports and source links.
- [Configuration](docs/src/content/docs/reference/configuration.md) and [transforms](docs/src/content/docs/reference/transforms.md): settings and optional modifiers.
- [Explanation](docs/src/content/docs/explanation/architecture.md): parser, transform and target boundaries.
- [Troubleshooting](docs/src/content/docs/troubleshooting.md): common input and pipeline failures.
- [Changelog](CHANGELOG.md): canonical release history.

## Development

From the repository root, install the development dependencies with `uv`:

```bash
uv sync --locked --all-groups
```

Then run the aggregate checks in that environment:

```bash
uv run prek run --all-files --hook-stage pre-push
```

A successful run reports passing checks. Hooks can update formatting.

See [contributors](docs/src/content/docs/contributors.md) for targeted checks and
[documentation build instructions](docs/README.md) for the Astro/Starlight site.

## License

BSD-3-Clause. See [LICENSE.txt](LICENSE.txt).
