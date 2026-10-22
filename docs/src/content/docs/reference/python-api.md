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

## County membership and region alignment

Import `load_county_membership`, `CountyMembership` and `align_regions` from
`r2x_reeds`. The loader accepts ReEDS `county2zone.csv` files with `FIPS` and
`ba` columns (and optional `county_name`) and `r_county.csv` files with `r` and
`county` columns. County identifiers are normalized to five-digit FIPS keys;
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

```python
from pathlib import Path

from r2x_reeds import RegionAlignmentPolicy, align_regions, load_county_membership

run_a = Path.cwd()
run_b = run_a  # Replace with another run root to compare two runs.

left = load_county_membership(run_a / "inputs_case" / "county2zone.csv")
right = load_county_membership(run_b / "inputs_case" / "r_county.csv")

alignment = align_regions(
	left,
	right,
	policy=RegionAlignmentPolicy.NESTED,
	require_complete=True,
	# Treat the left mapping as the expected county set. For independent
	# completeness validation, provide a trusted reference county universe.
	county_universe=left.county_to_region,
)

print(f"Coverage: left={alignment.left_coverage:.1%}, right={alignment.right_coverage:.1%}")
print(f"Region relationship: {alignment.resolution}")
print(f"Unmatched left regions: {alignment.unmatched_left_regions}")
print(f"Unmatched right regions: {alignment.unmatched_right_regions}")

for match in alignment.matched_regions:
	if match.left_region != match.right_region:
		print(f"{match.left_region} -> {match.right_region}: {match.counties}")
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
