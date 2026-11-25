---
title: Configuration Reference
---

## ReEDSConfig

| Package field                  | Type                  | Default  | Interpretation                                                 |
| ------------------------------ | --------------------- | -------- | -------------------------------------------------------------- |
| `solve_year`                   | `int` or `list[int]`  | required | Capacity/investment selection                                  |
| `weather_year`                  | `int` or `list[int]`  | required | Profile input selection                                        |
| `case_name`                    | `str` or `None`       | `None`   | Optional case label                                            |
| `scenario`                     | `str`                 | `"base"` | Scenario label                                                 |
| `excluded_techs`               | `list[str]` or `None` | `None`   | `None` uses package exclusions; an explicit list replaces them |
| `use_degraded_capacity`        | `bool`                | `False`  | Select degradation-adjusted online capacity                    |
| `use_psh_energy_capacity_duration` | `bool`             | `False`  | Derive PSH hours from reported energy and power capacity        |
| `drop_gen_capacity_threshold`  | `float`               | `0.0`    | Drop generators below this installed capacity in MW            |
| `apply_cf_adjustment`          | `bool`                | `False`  | Apply renewable capacity-factor adjustment to hourly profiles  |
| `apply_ilr_adjustment`         | `bool`                | `False`  | Scale PV hourly profiles by their inverter loading ratio       |

`primary_solve_year` and `primary_weather_year` return the first value when a list
is supplied. The CLI tutorial uses scalar years so downstream plugins receive one
selection. Config validation is not proof that the input run contains that year;
the parser validates mapped data during its lifecycle.

The CLI's `path` locates the data store. It is **not** a `ReEDSConfig` field in
Python: pass it to `DataStore.from_plugin_config(config, path=run_path)` instead.
See the [tested parsing tutorial](/r2x-reeds/tutorials/parse-run/) for the complete
context construction and [public config source](https://github.com/NatLabRockies/r2x-reeds/blob/86db7099fd409cff64f96e51b09a32a010b13cf5/src/r2x_reeds/plugin_config.py).

`ReEDSConfig` is the parser configuration model.

Key fields:

- `solve_year`: int or list of int
- `weather_year`: int or list of int
- `case_name`: optional string
- `scenario`: optional string, default `base`
- `use_degraded_capacity`: bool, default `False`; choose degradation-adjusted `cap_deg_ivrt` instead of `cap_ivrt` for online capacity.
- `use_psh_energy_capacity_duration`: bool, default `False`; opt into reported-energy-based PSH duration with strict source validation.
- `drop_gen_capacity_threshold`: float, default `0.0`; omit generators with installed capacity strictly below this value in MW.
- `apply_cf_adjustment`: bool, default `False`; multiply renewable profiles by generators' `capacity_factor_adjustment` values.
- `apply_ilr_adjustment`: bool, default `False`; multiply PV profiles by generators' `inverter_loading_ratio` values to account for DC-based capacity factors.
- `excluded_techs`: optional list of technologies to exclude. When omitted, the list from `defaults.json` is used.

Convenience properties:

- `primary_solve_year`
- `primary_weather_year`

### Renewable profile adjustments

With both flags disabled, the parser constructs hourly `max_active_power` in MW
as the source capacity-factor profile multiplied by generator capacity.
`apply_cf_adjustment=True` additionally multiplies renewable profiles by the generator's
`capacity_factor_adjustment`, read through the `renewable_cf_adjustment` mapping
from the ReEDS `cf_adj_t` dataset for the selected solve year.
`apply_ilr_adjustment=True` additionally multiplies PV profiles by `inverter_loading_ratio`,
read through the `ilr` mapping from the ReEDS `ilr` dataset. The current PV
selection includes technology names containing `pv`, including `distpv`.
These datasets are read from `outputs/outputs.h5`, with the CSV fallback described below.

Since renewable generators are aggregated into a single, representative generator by
region, renewable profile adjustments use capacity-weighted average values of
`capacity_factor_adjustment` and `inverter_loading_ratio` for each region.

The flags are independent; when both are enabled, both multipliers apply to PV
profiles. Enabling an adjustment requires its corresponding generator values to
be present. Neither flag changes installed generator capacity. Capacity selection
remains controlled separately by `use_degraded_capacity`. The parser warns if an
ILR-adjusted PV profile exceeds generator capacity; it does not clip the profile.
Leave an adjustment disabled if the source profile already includes that factor
to avoid applying it twice.

### Pumped-storage hydro duration

Set `use_psh_energy_capacity_duration: true` in the parser configuration to enable
reported-energy-based PSH duration:

```yaml
use_psh_energy_capacity_duration: true
```

The default is `False`: the parser preserves the original duration workflow,
does not read or require the PSH energy/reference reports for this feature,
and does not perform its power-basis validation or duration override. This
allows runs without `cap_energy_ivrt` to retain their existing duration sources
(which can include a generic 12-hour PSH duration). Existing parser requirements
still apply; disabling the feature does not guarantee compatibility with all
older runs.

When enabled, for included, positive-capacity technologies in the `pumped_storage` category,
the parser derives `storage_duration` in hours from reported
`cap_energy_ivrt` (MWh) divided by matching `cap_ivrt` (MW). Matching requires
technology, vintage, region, and selected solve year; no weather-year alignment
or hourly expansion is involved. The derived duration replaces the
technology-level duration, including a generic 12-hour value. Battery and other
non-PSH storage duration handling is unchanged.

The parser preserves the existing baseline-first, detailed-duration-second
logic, then applies the PSH override after the optional joins using the
configured `pumped_storage` technology category. Moving the PSH dataset within
the optional-data dictionary does not change this precedence. The temporary
`psh_storage_duration` column is removed after resolution. Existing missing-duration
filtering runs afterward so it cannot discard PSH before the override.

The `psh_energy_capacity` and `psh_reference_capacity` mappings read the
`cap_energy_ivrt` and `cap_ivrt` groups in `outputs/outputs.h5`, respectively,
with fallback to `outputs/cap_energy_ivrt.csv` and `outputs/cap_ivrt.csv`.
With the feature enabled, these reports are required when PSH survives technology exclusions and the
configured capacity threshold. Missing reports or matching rows, duplicate
matching keys, and null, nonpositive, or nonfinite values fail explicitly.
There is no automatic technology-duration fallback or reconstruction for older
ReEDS runs when the feature is enabled.
The upgrader does not generate a missing energy-capacity report.

`use_degraded_capacity=True` still selects `cap_deg_ivrt` for generator power.
With the feature enabled, PSH duration uses `cap_ivrt` as its reference denominator. Selected PSH
power must match that reference with `rtol=1e-6` and `atol=1e-6 MW`; otherwise
parsing fails instead of silently mixing power bases. In the inspected ReEDS
report equations, PSH `cap_ivrt` equals `cap_deg_ivrt`. The energy report reflects
the assumptions used by the source run, not necessarily newer detailed PSH data.

The parser leaves optional `energy_capacity` unset and resolves duration before
`break-gens`. Splitting copies duration and changes power, so each child's
implied energy is its own MW times hours. Total implied energy is conserved when
all power is retained; any deliberately discarded remainder also discards its
corresponding energy. Explicit energy capacities supplied by other workflows
are outside this change and are not proportionally allocated by the splitter.

## Parser Configuration Assets

The parser loads and applies these JSON assets from `src/r2x_reeds/config/`.

## defaults.json

Defines package-level parser defaults including:

- `excluded_techs`
- `tech_categories`
- `category_class_mapping`
- reserve defaults (`default_reserve_types`, `reserve_duration`, `reserve_time_frame`, etc.)
- unit conversion constants

Notable default behavior:

- `electrolyzer` is excluded from general generator parsing (`excluded_techs`) to keep purchaser-load modeling explicit.
- `can-imports` is excluded by default. To include it for a run, provide an `excluded_techs` list that omits `can-imports`.
- `can-exports` is excluded by default from generator parsing. This does not affect `add-exports`, which adds export energy to existing regional demand profiles.

## file_mapping.json

Defines named datasets and how each is read and normalized.

Each entry includes:

- `name`: logical dataset name
- `fpath`: relative file path in the ReEDS run
- `info`: metadata (`is_input`, `is_optional`, `units`, etc.)
- optional `reader` settings
- `proc_spec`: column mapping, filtering, schema, and pivot rules

Output bundle behavior:

- Output datasets that previously pointed to `outputs/*.csv` now point to `outputs/outputs.h5`
- The parser reads `outputs.h5` once per run and caches dataset groups for reuse
- For backward compatibility, if `outputs.h5` (or a requested group) is missing, parser read paths fall back to legacy `outputs/<dataset>.csv` when available

Examples of purchaser-load related datasets:

- `hydrogen_production_capacity`
- `hydrogen_production_load`
- `hydrogen_production_annual_load`
- `loadsite_op`
- `hour_map_myr`

## parser_rules.json

Maps normalized rows to component constructor fields.

Important sections:

- Generator families (`ReEDSThermalGenerator`, `ReEDSVariableGenerator`, `ReEDSStorage`, `ReEDSHydroGenerator`)
- Load and transmission components
- Reserve and emissions components
- Consuming technology rules (`ReEDSConsumingTechnology`, `ReEDSElectrolyzerDemand`)

Rule fields include:

- `field_map`
- `getters`
- `defaults`

## Runtime Placeholder Substitution

When reading mapped data, parser placeholders are commonly resolved from `ReEDSConfig`:

- `{solve_year}`
- `{weather_year}`

This allows one mapping specification to work across multiple scenarios and years.
