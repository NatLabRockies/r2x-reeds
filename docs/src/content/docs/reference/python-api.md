---
title: Python API
---

## Parser and configuration

Import `ReEDSConfig` and `ReEDSParser` from `r2x_reeds`. The configuration
requires `solve_year: int | list[int]` and `weather_year: int | list[int]`.
Optional fields are `case_name`, `scenario`, `excluded_techs` and
`config_path_override`. See the [configuration reference](/r2x-reeds/reference/configuration/)
for year and asset semantics.

Create a `DataStore` rooted at the ReEDS run directory and pass it to the plugin
context. The parser loads its packaged `file_mapping.json`, validates
`parser_rules.json`, reads declared sources, and asks core to construct the typed
outputs. No Python getter or mapping registration is needed.

```python
from pathlib import Path

from r2x_core import DataStore, PluginContext
from r2x_reeds import ReEDSConfig, ReEDSParser

run_path = Path("path/to/reeds-run")
config = ReEDSConfig(solve_year=2030, weather_year=2012)
context = PluginContext(config=config, store=DataStore(path=run_path))
result = ReEDSParser.from_context(context).run()
if result.system is None:
    raise RuntimeError("Parser returned no system")
system = result.system
```

The lifecycle raises `PluginError` when a hook returns an error. Its underlying
exception is chained as the cause. Missing required inputs, malformed tables,
invalid references, and unavailable requested years remain input failures.

The core guides describe [ordered data-file processing](https://natlabrockies.github.io/r2x-core/how-tos/configure-data-files/)
and [typed parser construction](https://natlabrockies.github.io/r2x-core/how-tos/build-parsers/).
The ReEDS [parser implementation](https://github.com/NatLabRockies/r2x-reeds/blob/main/src/r2x_reeds/parser.py)
and [configuration assets](https://github.com/NatLabRockies/r2x-reeds/tree/main/src/r2x_reeds/config)
show the current package declarations.

## Components and enumerations

The package exports `ReEDSRegion`, `ReEDSGenerator`, thermal, variable, hydro and
storage subclasses, demand and consuming-technology classes, transmission
lines and interfaces, reserves, emissions, and resource supply-curve classes.
Use `system.get_components(ComponentType)` to inspect a type. Enums include
`EmissionType`, `ReserveType` and `ReserveDirection`.

The [public export list](https://github.com/NatLabRockies/r2x-reeds/blob/main/src/r2x_reeds/__init__.py)
is authoritative for root imports. See [component definitions](https://github.com/NatLabRockies/r2x-reeds/blob/main/src/r2x_reeds/models/components.py)
for fields, units and validation.

## Post-parse modifiers

Modifiers intentionally operate on an already-built `System`. Their functions
return `Result[System, Exception]`; expected failures retain their exception
values.

```python
from rust_ok import Err
from r2x_reeds.sysmod.break_gens import BreakGensConfig, break_generators

result = break_generators(system, BreakGensConfig(drop_capacity_threshold=5))
if isinstance(result, Err):
    raise result.error
system = result.value
```

See the [transform reference](/r2x-reeds/reference/transforms/) and
[sysmod modules](https://github.com/NatLabRockies/r2x-reeds/tree/main/src/r2x_reeds/sysmod)
for supported modifiers.

## Upgrader

`ReEDSUpgrader(path: Path | str)` is exported from the package root. Its
`upgrade(...)` method returns `Result[Path, Exception]`. The parser uses the
upgrader during its lifecycle; upgrades can change run files, so work on a copy
of the run. See the [upgrader reference](/r2x-reeds/reference/upgrader/) for
version detection and step behavior.

## Saving and inspection

`System.to_json(path, overwrite=False, ...)` writes a component graph and its
time-series storage. Keep the JSON and companion time-series directory
 together. `System.from_json(path)` reconstructs the graph when its model classes
and companion storage are available. Use the [saved-system guide](/r2x-reeds/how-to/inspect-system/)
for inspection examples.
