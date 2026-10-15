---
title: Parse a ReEDS run
---

Build and inspect a system from your existing ReEDS run. Before starting,
[install the package](/r2x-reeds/how-to/install/) into a Python project.
Choose solve and weather years present in that run. The example years are inputs
to replace, not a guarantee that your data supports those years.

## Prepare inputs

Use a **working copy** of the run directory: the parser invokes file upgrade logic,
which can write or normalize input files. Preserve the original run for comparison.
Keep its `inputs_case/`, `outputs/` and `meta.csv` together. The mapped data may use
`outputs/outputs.h5` or legacy CSV fallbacks; keep time-series inputs with the run.

## Parse and inspect

Save this as `parse_reeds.py` in your Python project. Replace the path and years:

```python
from pathlib import Path
from r2x_core import DataStore, PluginContext
from r2x_reeds import ReEDSConfig, ReEDSParser, ReEDSRegion

run_path = Path("/path/to/reeds_run")
config = ReEDSConfig(solve_year=2030, weather_year=2012, case_name="example")
context = PluginContext(
    config=config,
    store=DataStore.from_plugin_config(config, path=run_path),
)
system = ReEDSParser.from_context(context).run().system
if system is None:
    raise RuntimeError("Parser returned no system")
regions = list(system.get_components(ReEDSRegion))
print(system.name)
print("Regions:", len(regions))
assert regions, "No ReEDS regions were built"

```

Run it in the project environment:

```bash
uv run python parse_reeds.py
```

Expect a system name and a positive region count. Counts depend on the run.
Compare region names with your ReEDS data before applying modifiers; successful
construction alone does not verify the modeling assumptions of a target exporter.

## Continue

Apply only the [transforms](/r2x-reeds/reference/transforms/) required by your
workflow, such as [purchaser load](/r2x-reeds/how-to/purchaser-load/).
Use [CLI pipelines](/r2x-reeds/how-to/reeds-to-x-cli/) for repeatable parser runs.
Target-specific translation recipes live in [R2X](https://natlabrockies.github.io/R2X/).
For missing data or year failures, use [troubleshooting](/r2x-reeds/troubleshooting/).
