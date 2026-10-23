---
title: Parse ReEDS with r2x-cli
---

Use a parser-only pipeline to check the [Pacific fixture tutorial](/r2x-reeds/tutorials/parse-run/)
run before adding target translation
packages. [Install the CLI plugin](/r2x-reeds/getting-started/installation/#cli-runtime) first.
These commands follow r2x-cli 0.1.15; inspect your installed CLI's help when using
another version.

## Define the pipeline

Use a working copy of the ReEDS run because parser upgrades can modify its files.
After extracting the fixture as shown in the tutorial, save
`reeds-parser-pipeline.yaml` in the tutorial workspace. For your own run, replace the
path and years with selections present in its data:

```yaml
pipelines:
  parse:
    - reeds-parser
config:
  reeds-parser:
    path: tutorial-inputs/test_Pacific
    solve_year: 2032
    weather_year: 2012
    case_name: example
```

`path` supplies the CLI data-store root. In Python, pass the run root to
`DataStore(path=run_path)` and include that store in the `PluginContext`.
Use one solve year and one weather year for this pipeline. The Python config
accepts lists; downstream packages can impose narrower limits.

## Inspect and run

```bash
r2x list r2x-reeds
r2x run reeds-parser-pipeline.yaml --list
r2x run reeds-parser-pipeline.yaml parse --dry-run
```

Expect a `parse` pipeline containing `reeds-parser`. Dry run verifies pipeline
resolution, not the contents of the input data. Create a separate output directory, then execute and save a portable artifact:

```bash
mkdir -p outputs
```

```bash
r2x run reeds-parser-pipeline.yaml parse --zip -o outputs/reeds-system.zip
```

Verify the artifact exists, then inspect it with the CLI:

```bash
ls -lh outputs/reeds-system.zip
r2x read outputs/reeds-system.zip --zip
```

The reader opens a Python session with the system bound to `sys`. For example:

```python
from r2x_reeds import ReEDSRegion
print(len(list(sys.get_components(ReEDSRegion))))
```

Compare the positive count with the input regions. Exit the session when finished.

## Add modifiers or a translation target

Insert a transform after `reeds-parser` and give it a configuration block. For example:

```yaml
pipelines:
  parse-and-split:
    - reeds-parser
    - break-gens
config:
  reeds-parser:
    path: tutorial-inputs/test_Pacific
    solve_year: 2032
    weather_year: 2012
  break-gens:
    drop_capacity_threshold: 5
```

`break-gens` uses packaged reference-unit defaults when `reference_units` is omitted.
See [transforms](/r2x-reeds/reference/transforms/) for the supported entry points and
[Python composition](/r2x-reeds/how-to/reeds-to-x-script/) for explicit error handling.

For complete exports, follow the maintained [ReEDS to PLEXOS](https://natlabrockies.github.io/R2X/how-to/reeds-to-plexos/)
or [ReEDS to Sienna](https://natlabrockies.github.io/R2X/how-to/reeds-to-sienna/) guide.
Install the target packages those guides specify and verify their own configuration
help; the parser package does not supply a target exporter.
