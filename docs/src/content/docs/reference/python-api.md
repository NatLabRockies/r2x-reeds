---
title: Python API
---

This reference describes the public surface at main revision
[ebb6953](https://github.com/NatLabRockies/r2x-reeds/tree/ebb69534188c7b94933c36a534d84a651114e2f9).

## Parser and configuration

Import `ReEDSConfig` and `ReEDSParser` from `r2x_reeds`.
`ReEDSConfig` requires `solve_year: int | list[int]` and
`weather_year: int | list[int]`. Optional package fields are `case_name`, `scenario`,
`excluded_techs` and `use_degraded_capacity`. See [configuration](/r2x-reeds/reference/configuration/).

Construct `PluginContext(config=config, store=DataStore.from_plugin_config(config, path=run_path))`
from `r2x_core`, then call `ReEDSParser.from_context(context).run()`.
`run(*, ctx=None)` returns the updated context; inspect `context.system` and check
for `None`. A failing lifecycle hook stops the run through the core plugin error
mechanism. The hooks themselves return `rust_ok.Result`, not the context.

Source: [parser](https://github.com/NatLabRockies/r2x-reeds/blob/ebb69534188c7b94933c36a534d84a651114e2f9/src/r2x_reeds/parser.py),
[config](https://github.com/NatLabRockies/r2x-reeds/blob/ebb69534188c7b94933c36a534d84a651114e2f9/src/r2x_reeds/plugin_config.py).

## Components and enumerations

The package exports `ReEDSRegion`, `ReEDSGenerator`, thermal, variable, hydro and
storage subclasses, demand and consuming-technology classes, transmission lines
and interfaces, reserves, emissions and resource supply-curve classes.
Use `system.get_components(ComponentType)` to inspect a type.
Enums include `EmissionType`, `ReserveType` and `ReserveDirection`.

The [public export list](https://github.com/NatLabRockies/r2x-reeds/blob/ebb69534188c7b94933c36a534d84a651114e2f9/src/r2x_reeds/__init__.py)
is authoritative for root imports. See [component definitions](https://github.com/NatLabRockies/r2x-reeds/blob/ebb69534188c7b94933c36a534d84a651114e2f9/src/r2x_reeds/models/components.py)
for constructor fields, units and validation; this page does not claim to generate
all inherited model signatures.

## Transforms

Each modifier takes `(system, config)` and returns `Result[System, str]`.
Use the [transform reference](/r2x-reeds/reference/transforms/) for module imports.
Check `is_err()` and report `unwrap_err()` before calling `unwrap()`.

Source: [sysmod modules](https://github.com/NatLabRockies/r2x-reeds/tree/ebb69534188c7b94933c36a534d84a651114e2f9/src/r2x_reeds/sysmod).

## Upgrader

`ReEDSUpgrader(path: Path | str)` is exported from the package root.
`ReEDSVersionDetector` and `run_reeds_upgrades(*, store, ctx)` are available from
`r2x_reeds.upgrader`. The helper returns `Result[None, str]` and is intended for
parser-context integration. See [upgrader](/r2x-reeds/reference/upgrader/) before
using it because upgrade steps can change run files.
