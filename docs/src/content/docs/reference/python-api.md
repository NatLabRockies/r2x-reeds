---
title: Python API
---

This reference describes the public Python contracts. Expand Python API in the
left navigation for each exported object, configuration model and modifier.
Member links open exact fields and methods. On smaller screens, open the Menu
button to access the same tree. Generated pages link to the source revision used
for the build and distinguish declared fields from inherited contracts.

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

See the [parsing tutorial](/r2x-reeds/tutorials/parse-run/) for a complete,
tested example. The lifecycle raises `PluginError` when a hook returns an error.
Its underlying exception is chained as the cause. Missing required inputs,
malformed tables, invalid references, and unavailable requested years remain
input failures.

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
for additional storage options.

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
