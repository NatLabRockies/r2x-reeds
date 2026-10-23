<img src="./docs/src/assets/r2x-logo-full-square.svg" alt="R2X framework logo" align="left" width="220" height="220" />

# r2x-reeds

ReEDS parser and transforms for the R2X plugin framework. Read ReEDS inputs and
outputs into an R2X system, then apply optional modifiers before translation by
separate target packages.

The [ReEDS model](https://github.com/ReEDS-Model/ReEDS) produces the capacity-expansion runs consumed here. `r2x-reeds` parses those results and applies optional system modifiers; it does not solve the ReEDS model.

[Documentation](docs/README.md) · [PyPI](https://pypi.org/project/r2x-reeds/) · [Changelog](CHANGELOG.md)

<br clear="left">

## Quick start

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

[Prepare a PCM handoff](docs/src/content/docs/how-to/pcm-handoff.md) covers all eight
registered system modifiers, optional profiles, cost-unit checks and inspection.

- [Tutorials](docs/src/content/docs/tutorials/parse-run.md): parse and inspect a run.
- [How-to guides](docs/src/content/docs/how-to/reeds-to-x-cli.md): CLI and Python workflows.
- [Reference/API](docs/src/content/docs/reference/python-api.md): public imports and source links.
- [Configuration](docs/src/content/docs/reference/configuration.md) and [transforms](docs/src/content/docs/reference/transforms.md): settings and optional modifiers.
- [Explanation](docs/src/content/docs/explanation/architecture.md): parser, transform and target boundaries.
- [Troubleshooting](docs/src/content/docs/troubleshooting.md): common input and pipeline failures.
- [Changelog](CHANGELOG.md): project release history.

## Development

```bash
uv sync --locked --all-groups
uv run prek run --all-files --hook-stage pre-push
```

See [contributors](docs/src/content/docs/contributors.md) for targeted checks and
[documentation build instructions](docs/README.md) for the Astro/Starlight site.

## License

BSD-3-Clause. See [LICENSE.txt](LICENSE.txt).
