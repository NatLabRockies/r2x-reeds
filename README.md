# r2x-reeds

ReEDS parser and transforms for the R2X plugin framework. Read ReEDS inputs and
outputs into an R2X system, then apply optional modifiers before translation by
separate target packages.

[Documentation](docs/README.md) · [PyPI](https://pypi.org/project/r2x-reeds/) · [Changelog](CHANGELOG.md)

## Quick start

Use Python 3.11–3.13 in a uv project:

```bash
uv add r2x-reeds
uv run python -c "from r2x_reeds import ReEDSConfig; print(ReEDSConfig(solve_year=2030, weather_year=2012).primary_solve_year)"
# 2030
```

Follow [parse a ReEDS run](docs/src/content/docs/tutorials/parse-run.md) to build
and inspect a system from your own data. Use a working copy of the run because
parser upgrade steps can modify input files.

For r2x-cli users, install into its managed environment:

```bash
r2x install r2x-reeds
r2x list r2x-reeds
```

See the [CLI parser pipeline](docs/src/content/docs/how-to/reeds-to-x-cli.md) for
configuration and artifact verification.

## Documentation

- [Tutorials](docs/src/content/docs/tutorials/parse-run.md): parse and inspect a run.
- [How-to guides](docs/src/content/docs/how-to/reeds-to-x-cli.md): CLI and Python workflows.
- [Reference/API](docs/src/content/docs/reference/python-api.md): public imports and source links.
- [Configuration](docs/src/content/docs/reference/configuration.md) and [transforms](docs/src/content/docs/reference/transforms.md): settings and optional modifiers.
- [Explanation](docs/src/content/docs/explanation/architecture.md): parser, transform and target boundaries.
- [Troubleshooting](docs/src/content/docs/troubleshooting.md): common input and pipeline failures.
- [Changelog](CHANGELOG.md): canonical release history.

## Development

```bash
uv sync --locked --all-groups
uv run prek run --all-files --hook-stage pre-push
```

See [contributors](docs/src/content/docs/contributors.md) for targeted checks and
[documentation build instructions](docs/README.md) for the Astro/Starlight site.

## License

BSD-3-Clause. See [LICENSE.txt](LICENSE.txt).
