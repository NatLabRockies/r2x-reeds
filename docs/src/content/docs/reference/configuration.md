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

## Configuration assets

The package configuration is in `src/r2x_reeds/config/`. `defaults.json` holds
policy data, `file_mapping.json` describes input sources and table processing,
and `parser_rules.json` declares output construction. Translation, export and
modifier assets are separate concerns.

### `defaults.json`

This file provides typed domain values consumed by configuration placeholders,
including default thermal values, resource source names, reserve products and
reserve-provider exclusions. Generator classifications derive from the ReEDS
technology-subset input. `ReEDSConfig.generator_classification_overrides`
provides optional exact exceptions. An explicit `excluded_techs` list in
`ReEDSConfig` overrides the package list, even when it is empty.

### `file_mapping.json`

This asset is a JSON list of core `DataFile` declarations. A declaration can
name a physical input, typed inline table, ordered source selection, or prepared
table with an ordered `proc_spec`. Processing includes filtering, joins,
aggregations, projections, weather-axis derivation and validation. Typed ReEDS
functions handle domain policies such as generator preparation, FOM precedence,
classification and resource-source enrichment. Core executes these through its
existing mapping-step extension point.

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
`generator_capacity_source` selects `online_capacity` (`"standard"`) or
`online_capacity_degraded` (`"degraded"`). The chosen source never silently
falls back when missing. The resource supply-curve declarations select a source
per technology before joining candidate enrichments, so candidate-only sites do
not become new resource sites when a primary source is populated.

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

Set `generator_capacity_source` on `ReEDSConfig` to choose standard or degraded
capacity. Edit the copied `file_mapping.json` only when changing input layouts or
source recipes, and edit `defaults.json` for packaged policy values. Keep all
required assets in the directory. Core's
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
