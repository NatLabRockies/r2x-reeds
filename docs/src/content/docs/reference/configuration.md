---
title: Configuration Reference
---

## ReEDSConfig

| Package field           | Type                  | Default  | Interpretation                                                 |
| ----------------------- | --------------------- | -------- | -------------------------------------------------------------- |
| `solve_year`            | `int` or `list[int]`  | required | Capacity/investment selection                                  |
| `weather_year`          | `int` or `list[int]`  | required | Profile input selection                                        |
| `case_name`             | `str` or `None`       | `None`   | Optional case label                                            |
| `scenario`              | `str`                 | `"base"` | Scenario label                                                 |
| `excluded_techs`        | `list[str]` or `None` | `None`   | `None` uses package exclusions; an explicit list replaces them |
| `use_degraded_capacity` | `bool`                | `False`  | Select degradation-adjusted online capacity                    |

`primary_solve_year` and `primary_weather_year` return the first value when a list
is supplied. The CLI tutorial uses scalar years so downstream plugins receive one
selection. Config validation is not proof that the input run contains that year;
the parser validates mapped data during its lifecycle.

The CLI's `path` locates the data store. It is **not** a `ReEDSConfig` field in
Python: pass it to `DataStore.from_plugin_config(config, path=run_path)` instead.
See the [tested parsing tutorial](/r2x-reeds/tutorials/parse-run/) for the complete
context construction and [public config source](https://github.com/NatLabRockies/r2x-reeds/blob/ebb69534188c7b94933c36a534d84a651114e2f9/src/r2x_reeds/plugin_config.py).

`ReEDSConfig` is the parser configuration model.

Key fields:

- `solve_year`: int or list of int
- `weather_year`: int or list of int
- `case_name`: optional string
- `scenario`: optional string, default `base`
- `use_degraded_capacity`: bool, default `False`; choose degradation-adjusted `cap_deg_ivrt` instead of `cap_ivrt` for online capacity.
- `excluded_techs`: optional list of technologies to exclude. When omitted, the list from `defaults.json` is used.

Convenience properties:

- `primary_solve_year`
- `primary_weather_year`

## Parser Configuration Assets

The parser loads and applies these JSON assets from `src/r2x_reeds/config/`.

## defaults.json

Defines package-level parser defaults including:

- `excluded_techs`
- `tech_categories`
- reserve defaults (`default_reserve_types`, `reserve_duration`, `reserve_time_frame`, etc.)
- unit conversion constants

Notable default behavior:

- `electrolyzer` is excluded from general generator parsing (`excluded_techs`) to keep purchaser-load modeling explicit.
- `can-imports` is excluded by default. To include it for a run, provide an `excluded_techs` list that omits `can-imports`.

## file_mapping.json

Defines physical files and prepared tables in a `{"files": [...], "tables": [...]}`
envelope. Each physical file entry names a dataset and configures its path,
optional metadata, reader settings, and `proc_spec`. Reader settings select the
format-specific behavior, including HDF5 group or dataset keys. Prepared tables
name a physical base source, explicit left many-to-one joins, and required result
columns. Table joins do not read other prepared tables.

The packaged mapping reads ReEDS output groups from `outputs/outputs.h5` using
core's configured HDF5 reader. Core selects the CSV or HDF5 reader from the
configured file extension. Each read follows the mapping; the parser does not
keep a run-wide HDF5 handle or dataset cache. Extension-based reader selection
does not select an alternate source or fall back from HDF5 to CSV. CSV outputs
must be selected by an explicit complete `file_mapping` asset override.

For runs whose CSV filenames match the HDF5 group names, start from the complete
packaged mapping, replace each HDF5 output path, and remove its HDF5-only reader
settings before constructing the store. This example uses the whole-asset
`asset_overrides` API from the coordinated r2x-core source. The installed
r2x-core 0.9.0 package does not provide this API, so ReEDS and r2x-core must be
released together before using the example with published packages:

```python
import json
from importlib.resources import files
from pathlib import Path

from r2x_core import DataStore
from r2x_reeds import ReEDSConfig

mapping = json.loads(
    files("r2x_reeds").joinpath("config", "file_mapping.json").read_text()
)
for entry in mapping["files"]:
    if entry["fpath"] == "outputs/outputs.h5":
        hdf5_reader = entry.pop("reader")
        entry["fpath"] = f"outputs/{hdf5_reader['kwargs']['group_key']}.csv"

config = ReEDSConfig(
    solve_year=2030,
    weather_year=2012,
    asset_overrides={"file_mapping": mapping},
)
store = DataStore.from_plugin_config(config, path=Path("path/to/reeds-run"))
```

This example assumes one CSV named for each configured HDF5 group. Adjust paths
and reader settings to match the files actually present. Asset overrides replace
the full mapping, so retain the complete `files` and `tables` envelope.

Examples of purchaser-load related datasets:

- `hydrogen_production_capacity`
- `hydrogen_production_load`
- `hydrogen_production_annual_load`
- `loadsite_op`
- `hour_map_myr`

## parser_rules.json

Uses the core `RulePlan` envelope. `mappings` define reusable field mappings
for policy-prepared records. `rules` add an explicit typed source and target.
`execution` names ordered Rule stages, such as `regions` before
`transmission`. The core validates names, references, datasets, target models,
and mapped fields before the parser mutates a `System`.

A dataset-backed Rule has an explicit source and target:

```json
{
  "name": "region",
  "source": {"kind": "dataset", "dataset": "hierarchy"},
  "target": {
    "kind": "component",
    "component_types": ["ReEDSRegion"]
  },
  "field_map": {"state": "state"},
  "getters": {"name": "build_region_name"}
}
```

The root object contains `mappings`, `mapping_selections`, `rules`, `execution`,
and optional `required_stages`, `required_rules`, and `required_datasets`. A
mapping selection declares an explicit priority and maps each category key to a
named mapping. The core validates the selection before execution. A required
dataset must be registered and must not be marked optional in `file_mapping.json`.
There is no list-root compatibility form.

Rule mappings use `field_map`, `getters`, `defaults`, and `filter`. Dataset
sources name either a physical file or a prepared table from `file_mapping.json`.
The current ReEDS plan declares region, transmission, and emission stages; other
policy-prepared families continue to use named mappings until their migration.

## Runtime Placeholder Substitution

When reading mapped data, parser placeholders are commonly resolved from `ReEDSConfig`:

- `{solve_year}`
- `{weather_year}`

This allows one mapping specification to work across multiple scenarios and years.
