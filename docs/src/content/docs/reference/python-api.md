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
`generator_capacity_source`, `generator_classification_overrides`,
`drop_gen_capacity_threshold`, `apply_cf_adjustment`, `apply_ilr_adjustment`
and `config_path_override`. Both profile-adjustment flags default to `False`.
See the [configuration reference](/r2x-reeds/reference/configuration/) for
year, capacity-source and profile-adjustment semantics.

Create a `DataStore` rooted at the ReEDS run directory and pass it to the plugin
context. The parser loads `file_mapping.json`, assembles tables using
`table_mapping.json`, validates `parser_rules.json`, and asks core to construct
the typed outputs. No Python getter or reader registration is needed.

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

## County membership and region alignment

Import `load_county_membership`, `CountyMembership` and `align_regions` from
`r2x_reeds`. The loader accepts ReEDS `county2zone.csv` files with `FIPS` and
`ba` columns (and optional `county_name`), zone-definition files with `FIPS` and
`r` columns, and `r_county.csv` files with `r` and `county` columns. When a file
has both `r` and `ba`, `r` is used because the same county can belong to
different modeled regions across zone definitions. County identifiers are
normalized to five-digit FIPS keys;
region labels and available county display labels remain available on the
membership as `region_to_counties`, `county_to_region` and `county_labels`.

`align_regions(left, right)` matches counties by normalized FIPS and returns
region-pair matches with contributing counties, unmatched region labels, and
per-run county coverage fractions. A balancing area can therefore match
multiple county-level regions without choosing a direction-dependent hierarchy.
Partial coverage is reported by default. Pass `require_complete=True` to raise
`RegionAlignmentError` when either membership contains a county absent from the
other. Duplicate assignments and counties assigned to multiple regions raise
`CountyMembershipError` with the affected FIPS and source row.

### Example

Run this from a ReEDS run directory, or set `run_a` and `run_b` to the actual
run-root paths. The example compares `county2zone.csv` from the left run with
`r_county.csv` from the right run. Set `run_b = run_a` to inspect two mapping
files in one run.

```python doctest
>>> from pathlib import Path
>>> from tempfile import TemporaryDirectory
>>> from r2x_reeds import RegionAlignmentPolicy, align_regions, load_county_membership
>>> scratch = TemporaryDirectory()
>>> run_a = Path(scratch.name) / "run_a"
>>> run_b = Path(scratch.name) / "run_b"
>>> (run_a / "inputs_case").mkdir(parents=True)
>>> (run_b / "inputs_case").mkdir(parents=True)
>>> _ = (run_a / "inputs_case/county2zone.csv").write_text(
...     "FIPS,ba,county_name,state\n53007,p1,chelan,WA\n53029,p1,island,WA\n"
... )
>>> _ = (run_b / "inputs_case/r_county.csv").write_text(
...     "r,county\np53007,p53007\np53029,p53029\n"
... )
>>> left = load_county_membership(run_a / "inputs_case/county2zone.csv")
>>> right = load_county_membership(run_b / "inputs_case/r_county.csv")
>>> alignment = align_regions(
...     left,
...     right,
...     policy=RegionAlignmentPolicy.NESTED,
...     require_complete=True,
...     county_universe=left.county_to_region,
... )
>>> (alignment.left_coverage, alignment.right_coverage, alignment.resolution.value)
(1.0, 1.0, 'left_coarser')
>>> [(match.left_region, match.right_region, match.counties) for match in alignment.matched_regions]
[('p1', 'p53007', ('53007',)), ('p1', 'p53029', ('53029',))]
>>> left.county_labels['53007']
'chelan'
```

This is useful before comparing or translating region-indexed inputs: it shows
whether the county sets have complete coverage and whether region partitions
are identical, nested, or crossing. The matched county lists make aggregation
paths explicit. It does not aggregate load profiles or other numerical data;
use the crosswalk to guide that separate operation.

The `policy` argument makes the allowed relationship explicit: `"crosswalk"`
allows any county-based overlap, `"nested"` allows aggregation in either
direction but rejects crossing region boundaries, and `"same_partition"`
requires identical county groupings (region labels may differ). The result's
`resolution` reports `same_partition`, `left_coarser`, `right_coarser` or
`crossing`; it is `None` when county coverage is incomplete. Strict policies
require complete coverage. To check completeness against geography omitted from
both inputs, pass `county_universe=` with FIPS keys from a trusted complete
reference mapping; each input must match that expected set exactly.

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
