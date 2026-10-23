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
| `excluded_techs` | `list[str] \| None` | `None` | `None` uses package exclusions; an explicit list, including `[]`, replaces them |
| `config_path_override` | `Path \| None` | `None` | Complete configuration directory override |

`primary_solve_year` and `primary_weather_year` return the first configured year.
The parser still validates that requested years exist in the mapped data. Load
profiles must cover every requested solve year; weather profiles use the
configured weather-year policy.

The run directory is supplied separately to `DataStore(path=run_path)`. It must
contain the ReEDS run inputs, such as `meta.csv`, `inputs_case/` and `outputs/`.
The parser loads its file mapping during the prepare lifecycle phase.

## Configuration assets

The package configuration is in `src/r2x_reeds/config/`. `defaults.json` holds
policy data, `file_mapping.json` describes input sources and table processing,
and `parser_rules.json` declares output construction. Translation, export and
modifier assets are separate concerns.

### `defaults.json`

This file provides typed domain values consumed by configuration placeholders,
including default thermal values, resource source names, reserve products and
reserve-provider exclusions. Generator category patterns and their priorities
are declared in `file_mapping.json` under
`generator_category_patterns.inline_table.rows`. An explicit `excluded_techs`
list in `ReEDSConfig` overrides the package list, even when it is empty.

### `file_mapping.json`

This asset is a JSON list of core `DataFile` declarations. A declaration can
name a physical input, typed inline table, ordered source selection, or prepared
table with an ordered `proc_spec`. Processing includes filtering, joins,
aggregations, projections, calendar expansion and validation. It is declarative:
ReEDS does not run a separate row-processing or component-construction stage.

Physical inputs retain their availability semantics. A missing optional file is
absent; a present empty file is still present; malformed present data is an
error. A source selector can choose the first present input or the first
nonempty input. These differ intentionally for defaults and market data. A
conditional `required_when` rule makes selected optional inputs required when a
previously declared policy table matches. See the core guides for [DataFile and
reader configuration](https://natlabrockies.github.io/r2x-core/how-tos/configure-data-files/)
and [ordered table processing](https://natlabrockies.github.io/r2x-core/references/processors/).

The packaged load declarations derive peaks and profile rows from the same
physical load source. Requested solve years are validated before construction.
The selected capacity source is explicit in the generator table declarations;
changing it never silently falls back when the chosen source is missing. The
resource supply-curve declarations select a source per technology before
joining candidate enrichments, so candidate-only sites do not become new
resource sites when a primary source is populated.

To customize a mapping, copy the complete package configuration directory and
set `config_path_override`. The override is a directory, not a partial JSON
fragment:

```python
from pathlib import Path
from shutil import copytree

from r2x_core import DataStore, PluginContext
from r2x_reeds import ReEDSConfig, ReEDSParser

run_path = Path("path/to/reeds-run")
config_path = Path("reeds-config")
copytree(ReEDSConfig.package_config_path(), config_path)
config = ReEDSConfig(
    solve_year=2030,
    weather_year=2012,
    config_path_override=config_path,
)
context = PluginContext(config=config, store=DataStore(path=run_path))
system = ReEDSParser.from_context(context).run().system
if system is None:
    raise RuntimeError("Parser returned no system")
```

Edit the copied `file_mapping.json` or `defaults.json` using their declared
schemas. For example, change the generator-capacity source selection to choose a
different configured source. Keep all required assets in the directory. Core's
[parser construction guide](https://natlabrockies.github.io/r2x-core/how-tos/build-parsers/)
describes the shared typed output instructions.

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
