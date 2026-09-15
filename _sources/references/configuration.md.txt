# Configuration Reference

## ReEDSConfig

`ReEDSConfig` is the parser configuration model.

Key fields:

- `solve_year`: int or list of int
- `weather_year`: int or list of int
- `case_name`: optional string
- `scenario`: optional string, default `base`
- `excluded_techs`: optional list of technologies to exclude. When omitted, the list from `defaults.json` is used.

Convenience properties:

- `primary_solve_year`
- `primary_weather_year`

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
