---
title: Python API
---

This reference describes the public Python contracts. Expand Python API in the
left navigation for each exported object, configuration model and modifier.
Member links open exact fields and methods. On smaller screens, open the Menu
button to access the same tree. Generated pages link to the source revision used
for the build and distinguish declared fields from inherited contracts.

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

Source: [parser](https://github.com/NatLabRockies/r2x-reeds/blob/86db7099fd409cff64f96e51b09a32a010b13cf5/src/r2x_reeds/parser.py),
[config](https://github.com/NatLabRockies/r2x-reeds/blob/86db7099fd409cff64f96e51b09a32a010b13cf5/src/r2x_reeds/plugin_config.py).

## Components and enumerations

The package exports `ReEDSRegion`, `ReEDSGenerator`, thermal, variable, hydro and
storage subclasses, demand and consuming-technology classes, transmission lines
and interfaces, reserves, emissions and resource supply-curve classes.
Use `system.get_components(ComponentType)` to inspect a type.
Enums include `EmissionType`, `ReserveType` and `ReserveDirection`.

The [public export list](https://github.com/NatLabRockies/r2x-reeds/blob/86db7099fd409cff64f96e51b09a32a010b13cf5/src/r2x_reeds/__init__.py)
is authoritative for root imports. See [component definitions](https://github.com/NatLabRockies/r2x-reeds/blob/86db7099fd409cff64f96e51b09a32a010b13cf5/src/r2x_reeds/models/components.py)
for constructor fields, units and validation; this page does not claim to generate
all inherited model signatures.

## Transforms

Each modifier takes `(system, config)` and returns `Result[System, str]`.
Use the [transform reference](/r2x-reeds/reference/transforms/) for module imports.
Check `is_err()` and report `unwrap_err()` before calling `unwrap()`.

Source: [sysmod modules](https://github.com/NatLabRockies/r2x-reeds/tree/86db7099fd409cff64f96e51b09a32a010b13cf5/src/r2x_reeds/sysmod).

## Upgrader

`ReEDSUpgrader(path: Path | str)` is exported from the package root.
`ReEDSVersionDetector` and `run_reeds_upgrades(*, store, ctx)` are available from
`r2x_reeds.upgrader`. The helper returns `Result[None, str]` and is intended for
parser-context integration. See [upgrader](/r2x-reeds/reference/upgrader/) before
using it because upgrade steps can change run files.

## Saving and inspection contracts

`System.to_json(fname, overwrite=False, indent=None, data=None)` writes an
Infrasys component graph and companion time-series storage when a path is given.
Existing files raise `FileExistsError` unless overwrite is enabled.
`System.from_json(path)` reconstructs the graph; recorded model classes must be
importable and companion storage must remain available.
`system.get_components(ComponentType)` iterates components of that type;
`system.get_time_series(component, name="...")` selects an attached series.
An absent profile or incompatible serialization is a loading/query error, not a
signal to fabricate replacement data.

Use the [saved-system guide](/r2x-reeds/how-to/inspect-system/) for executed Python
and CLI queries, and [Infrasys source/API](https://github.com/NatLabRockies/infrasys/blob/main/src/infrasys/system.py)
for additional storage options. The examples use a path and make no claims about
stdout-only serialization or loading native target-format JSON.

## Public member catalog

Start with [ReEDSConfig](/r2x-reeds/reference/api/reedsconfig/) and
[ReEDSParser](/r2x-reeds/reference/api/reedsparser/). Inspect
[ReEDSGenerator](/r2x-reeds/reference/api/reedsgenerator/),
[ReEDSDemand](/r2x-reeds/reference/api/reedsdemand/) and
[ReEDSRegion](/r2x-reeds/reference/api/reedsregion/) for source-system fields.
The navigation also includes all eight modifier functions and their config models,
[ReEDSUpgrader](/r2x-reeds/reference/api/reedsupgrader/) and public enums/types.

Use [Getting Started](/r2x-reeds/getting-started/system-modifiers/) to choose a
modifier. The [transform reference](/r2x-reeds/reference/transforms/) defines its
configuration contract, while [PCM handoff](/r2x-reeds/how-to/pcm-handoff/) explains
how to apply and check it.
