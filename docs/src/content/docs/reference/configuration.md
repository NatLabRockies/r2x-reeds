---
title: Configuration Reference
---

## ReEDSConfig

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `solve_year` | `int \| list[int]` | required | Capacity and investment years to parse |
| `weather_year` | `int \| list[int]` | required | Weather years used for profiles |
| `case_name` | `str \| None` | `None` | Optional case label |
| `scenario` | `str` | `"base"` | Scenario label |
| `generator_capacity_source` | `Literal["standard", "degraded"]` | `"standard"` | Selects `online_capacity` or `online_capacity_degraded`; the chosen source does not fall back if missing |
| `generator_classification_overrides` | `list[GeneratorClassificationOverride]` | `[]` | Optional exact technology-specific classification exceptions |
| `excluded_techs` | `list[str] \| None` | `None` | `None` uses package exclusions; an explicit list, including `[]`, replaces them |
| `config_path_override` | `Path \| None` | `None` | Complete configuration directory override |

A parsed `System` retains each configured solve year as a separate state.
Year-qualified component identities and `solve_year` fields let consumers select
one state with `System.get_components(..., filter_func=...)`. The parser
validates requested years against mapped data. Load profiles must cover every
requested solve/weather-year pair. The weather calendar uses the first
configured weather year and its first 8,760 hourly timestamps.

The CLI's `path` locates the data store. It is not a `ReEDSConfig` field in
Python. Pass it to `DataStore(path=run_path)`. The directory must contain the
ReEDS run inputs, such as `meta.csv`, `inputs_case/` and `outputs/`. The parser
loads its file mapping during preparation. See the
[parsing tutorial](/r2x-reeds/tutorials/parse-run/) for context construction and
the [public config source](https://github.com/NatLabRockies/r2x-reeds/blob/main/src/r2x_reeds/plugin_config.py).
Replace older `DataStore.from_plugin_config(...)` examples with this constructor.
The parser loads its configured readers itself. The removed
`register_modeled_years_reader` function is no longer needed.

## Configuration assets

The package configuration is in `src/r2x_reeds/config/`. `defaults.json` holds
policy data, `file_mapping.json` declares native inputs and source availability,
`table_mapping.json` assembles named tables, and `parser_rules.json` declares
component and time-series construction. Translation, export and modifier assets
are separate concerns.

### `defaults.json`

This file provides typed domain values consumed by configuration placeholders,
including default thermal values, resource source names, reserve products and
reserve-provider exclusions. Generator classifications derive from the ReEDS
technology-subset input. `ReEDSConfig.generator_classification_overrides`
provides optional exact exceptions. An explicit `excluded_techs` list in
`ReEDSConfig` overrides the package list, even when it is empty.

### `file_mapping.json`

This asset is a JSON list of core `DataFile` declarations. A declaration can
name a physical input, typed inline table, ordered source selection, or a
prepared source. Physical declarations own native paths, column types, and
input-boundary renaming or filtering. Prepared-source declarations include
validation of assembled tables. `table_mapping.json` expresses generator
classification, owner naming, and load and reserve assembly with generic
operations and ReEDS policy data.

Physical inputs retain their availability semantics. A missing optional file is
absent; a present empty file is still present; malformed present data is an
error. A source selector can choose the first present input or the first
nonempty input. These differ intentionally for defaults and market data. A
conditional `required_when` rule makes selected optional inputs required when a
previously declared policy table matches. See the core guides for [DataFile and
reader configuration](https://natlabrockies.github.io/r2x-core/how-tos/configure-data-files/)
and [ordered table processing](https://natlabrockies.github.io/r2x-core/references/processors/).

The load table mapping uses the same physical source for peak components and
profile rows. It selects requested solve/weather pairs before unpivoting the
runtime region headers. Peaks include all selected weather years, while profile
rows retain their solve-year and weather-year partitions. The input mapping
derives the weather-year label from native timestamps, and the table mapping
constructs solve-year-qualified load owner names. The parser validates coverage
for every requested pair and rejects all-null region/solve-year peaks.

`generator_capacity_source` selects `online_capacity` (`"standard"`) or
`online_capacity_degraded` (`"degraded"`). Replace the removed
`use_degraded_capacity=True` setting with `generator_capacity_source="degraded"`.
Use `"standard"` for the former `False` setting. The `primary_solve_year` property
was also removed. Use `solve_year` directly and select an element explicitly
when it is a list. The chosen capacity source never silently falls back when
missing. The resource supply-curve declarations select a source
per technology before joining candidate enrichments, so candidate-only sites do
not become new resource sites when a primary source is populated.

To customize a mapping, copy the complete package configuration directory and
set `config_path_override`. The override is a directory, not a partial JSON
fragment:

```python doctest
>>> from pathlib import Path
>>> from shutil import copytree
>>> from tempfile import TemporaryDirectory
>>> from r2x_reeds import ReEDSConfig
>>> with TemporaryDirectory() as folder:
...     config_path = Path(folder) / "reeds-config"
...     _ = copytree(ReEDSConfig.package_config_path(), config_path)
...     config = ReEDSConfig(solve_year=2032, weather_year=2012, config_path_override=config_path)
...     assert config.fmap_path.is_file()
...
```

For a persistent override, use a directory you control instead of the temporary
one. Pass the configured `ReEDSConfig` to the parser as shown in the
[parsing tutorial](/r2x-reeds/tutorials/parse-run/).

Set `generator_capacity_source` on `ReEDSConfig` to choose standard or degraded
capacity. The `generator_rows` table is explicitly materialized after projection
for reuse by its consumers. This retains the table in memory and can surface data
errors during assembly. Edit the copied `file_mapping.json` only when changing
input layouts or source recipes, and edit `defaults.json` for packaged policy
values. Keep all required assets in the directory. Core's
[parser construction guide](https://natlabrockies.github.io/r2x-core/how-tos/build-parsers/)
describes the shared typed output instructions.

### Update a copied configuration

> Warning: A configuration directory copied from an earlier ReEDS version is
> not complete for the current parser. Adding `table_mapping.json` alone is not
> enough. Keep the required validation records in `file_mapping.json`.

1. Keep the existing override unchanged. Copy the current package configuration
   to a new directory as shown above.
2. Reapply input paths and native column declarations in `file_mapping.json`.
   Reapply policy values in `defaults.json`, table transformations in
   `table_mapping.json`, and output mappings in `parser_rules.json`.
3. Replace ReEDS-specific processing handlers with table operations. There is no
   automatic conversion of custom mappings.
4. Run the parser with the new override on a representative case. Compare the
   component counts and time-series values before switching to the new directory.

Physical source names changed for these inputs. Some prior names still identify
assembled tables, so update physical-input references rather than replacing
names indiscriminately:

| Previous physical source | Current physical source |
| --- | --- |
| `hydro_cf` | `hydro_cf_input` |
| `hydro_capacity_adjustment` | `hydro_capacity_adjustment_input` |
| `hydrogen_production_capacity` | `hydrogen_production_capacity_input` |
| `hydrogen_production_annual_load` | `hydrogen_production_annual_load_input` |
| `hydrogen_production_load` | `hydrogen_production_load_input` |

Code that reads prepared rows directly must use
`DataReader.read_and_assemble_sources` with the current file mapping, table
mapping, backend, and required placeholders. `read_data_files` alone does not
produce assembled outputs such as `generator_rows` or `load_peaks`.

### `table_mapping.json`

This JSON list declares ordered, named table operations after input decoding.
Joins, reshaping, grouping, and sorting stay in the mapping; `parser_rules.json`
only maps resulting columns to model fields.
For the dynamic load headers, omitting `unpivot.columns` selects each source
column outside `index` and uses its exact native header as the region label:

```json
{
  "name": "load_profile_values",
  "source": "load_profiles",
  "operations": [
    {
      "operation": "join",
      "source": "requested_solve_weather_year_rows",
      "how": "inner",
      "on": ["solve_year", "weather_year"],
      "columns": []
    },
    {
      "operation": "unpivot",
      "index": ["datetime", "solve_year", "weather_year"],
      "variable_name": "region",
      "value_name": "value"
    },
    {
      "operation": "join",
      "source": "load_owner_names",
      "how": "left",
      "on": ["region", "solve_year"],
      "columns": ["owner_name"]
    }
  ]
}
```

The load mapping derives `load_peaks` with a max over each region and solve
year, and retains one sorted `load_profile_rows` table for time-series
construction. The `load_owner_names` table constructs `owner_name` from the
region and solve year. Copy the complete package configuration
before changing mappings so every referenced source and output instruction is
present.

### `parser_rules.json`

This asset is a JSON list of typed core instructions. Each instruction names a
prepared source and declares one output kind:

- `component` maps source columns to model fields and can resolve references to
  previously constructed components.
- `supplemental_attribute` maps source columns to an attribute model and its
  owner components.
- `time_series` selects values, a regular or column-based time axis, owners,
  and optional literal or row-derived metadata.

For example, the hierarchy instruction maps `region_id` to the component's
`name` field:

```json
{
  "kind": "component",
  "source": "hierarchy",
  "component_type": "ReEDSRegion",
  "fields": {"name": "region_id"}
}
```

An instruction's `fields` map target field names to source column names.
Configuration validation checks instruction kinds and field/reference shapes;
the core builder validates model values, resolves references, and attaches
series. See the core [parser construction guide](https://natlabrockies.github.io/r2x-core/how-tos/build-parsers/)
for the complete instruction contract.

## Placeholder values

The parser substitutes configuration values such as `{solve_year}` and
`{weather_year}` into the declared inputs, inline tables and processing
expressions. Package defaults and domain rows are validated before those values
are used. Keep policy values in the configuration assets rather than adding
ReEDS-specific processing code.
