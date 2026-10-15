---
title: Transforms Reference
---

Transforms are optional post-parse system modifiers exposed under the `r2x.transforms` entry point group.

## Available Transforms

- `add-pcm-defaults`
- `add-emission-cap`
- `add-electrolyzer-load`
- `add-purchaser-load`
- `add-ccs-credit`
- `break-gens`
- `add-imports`
- `add-optimal-siting`

## Configuration Summary

Each transform accepts a plugin-specific configuration model. Use [the CLI guide](/r2x-reeds/how-to/reeds-to-x-cli/) to add a modifier step.
Import configuration classes and functions from the modules linked below.
Source definitions give each field type, default and required input.

| Transform               | Configuration model   | Main purpose                                    |
| ----------------------- | --------------------- | ----------------------------------------------- |
| `break-gens`            | `BreakGensConfig`     | Split oversized generators into reference units |
| `add-pcm-defaults`      | `PCMDefaultsConfig`   | Fill or override generator attributes           |
| `add-emission-cap`      | `EmissionCapConfig`   | Add an annual CO2 constraint                    |
| `add-electrolyzer-load` | `ElectrolyzerConfig`  | Add legacy electrolyzer and hydrogen-price data |
| `add-purchaser-load`    | `PurchaserLoadConfig` | Add hydrogen-production and data-center demand  |
| `add-ccs-credit`        | `CCSCreditConfig`     | Apply CCS incentives                            |
| `add-imports`           | `ImportsConfig`       | Add Canadian import time series                 |
| `add-optimal-siting`    | `OptimalSitingConfig` | Apply loadsite increments to demand profiles    |

## Purchaser Load Transform

Transform id: `add-purchaser-load`

Module: `r2x_reeds.sysmod.purchaser_load`

Function: `add_purchaser_load(system, config)`

Purpose:

- Adds/updates electrolyzer, steam methane reforming and data center purchaser-load components
- Attaches hourly load profiles for those components

Important behavior:

- If the demand component for one of the ReEDS electricity-consuming technologies handled here (`electrolyzer`, `smr` or `smr_ccs`) already exists, capacity-based creation of that component is skipped to avoid double counting.

Config model: `PurchaserLoadConfig`

Main fields:

- `solve_year`
- `weather_year`
- `hour_map_myr_fpath`
- `hydrogen_production_capacity_fpath`
- `consume_characteristics_fpath`
- `hydrogen_production_load_fpath`
- `hydrogen_production_annual_load_fpath`
- `loadsite_op_fpath`

## Legacy Electrolyzer Transform

Transform id: `add-electrolyzer-load`

Module: `r2x_reeds.sysmod.electrolyzer`

Purpose:

- Legacy workflow for adding electrolyzer load and hydrogen fuel price time series

## Other Transforms

- `add-pcm-defaults`: apply PCM default attributes to generators
- `add-emission-cap`: add annual emissions constraints and optional precombustion adjustments
- `add-ccs-credit`: apply CCS credit economics
- `break-gens`: split generators into reference units (optionally filtered by region, generator name, or technology)
- `add-imports`: apply import/export handling
- `add-optimal-siting`: add loadsite increments to existing load profiles

### break-gens config highlights

The `BreakGensConfig` model supports targeted disaggregation workflows without changing default behavior:

- `include_regions`: only split generators in these balancing areas
- `include_generators`: only split generators with these names
- `include_technologies`: only split generators with these technologies

When more than one include filter is provided, matching uses OR behavior.
A generator is split if it matches any one of `include_regions`, `include_generators`, or `include_technologies`.

If these fields are omitted, `break-gens` keeps the original workflow and considers all eligible generators.

## Configuration fields and source

### BreakGensConfig

Module: `r2x_reeds.sysmod.break_gens`.

Package fields: `reference_units`, `drop_capacity_threshold`, `skip_categories`, `break_category`, `include_regions`, `include_generators`, `include_technologies`.

[Source and defaults](https://github.com/NatLabRockies/r2x-reeds/blob/ebb69534188c7b94933c36a534d84a651114e2f9/src/r2x_reeds/sysmod/break_gens.py).

### PCMDefaultsConfig

Module: `r2x_reeds.sysmod.pcm_defaults`.

Package fields: `pcm_defaults_fpath`, `pcm_defaults_dict`, `pcm_defaults_override`.

[Source and defaults](https://github.com/NatLabRockies/r2x-reeds/blob/ebb69534188c7b94933c36a534d84a651114e2f9/src/r2x_reeds/sysmod/pcm_defaults.py).

### EmissionCapConfig

Module: `r2x_reeds.sysmod.emission_cap`.

Package fields: `emission_cap`, `switches_fpath`, `emission_rates_fpath`, `co2_cap_fpath`, `default_unit`.

[Source and defaults](https://github.com/NatLabRockies/r2x-reeds/blob/ebb69534188c7b94933c36a534d84a651114e2f9/src/r2x_reeds/sysmod/emission_cap.py).

### ElectrolyzerConfig

Module: `r2x_reeds.sysmod.electrolyzer`.

Package fields: `weather_year`, `electrolyzer_load_fpath`, `h2_fuel_price_fpath`, `hour_map_fpath`.

[Source and defaults](https://github.com/NatLabRockies/r2x-reeds/blob/ebb69534188c7b94933c36a534d84a651114e2f9/src/r2x_reeds/sysmod/electrolyzer.py).

### PurchaserLoadConfig

Module: `r2x_reeds.sysmod.purchaser_load`.

Package fields: `solve_year`, `weather_year`, `hydrogen_production_capacity_fpath`, `consume_characteristics_fpath`, `hydrogen_production_load_fpath`, `hydrogen_production_annual_load_fpath`, `loadsite_op_fpath`, `hour_map_myr_fpath`.

[Source and defaults](https://github.com/NatLabRockies/r2x-reeds/blob/ebb69534188c7b94933c36a534d84a651114e2f9/src/r2x_reeds/sysmod/purchaser_load.py).

### CCSCreditConfig

Module: `r2x_reeds.sysmod.ccs_credit`.

Package fields: `co2_incentive_fpath`, `emission_capture_rate_fpath`, `upgrade_link_fpath`.

[Source and defaults](https://github.com/NatLabRockies/r2x-reeds/blob/ebb69534188c7b94933c36a534d84a651114e2f9/src/r2x_reeds/sysmod/ccs_credit.py).

### ImportsConfig

Module: `r2x_reeds.sysmod.imports`.

Package fields: `weather_year`, `solve_year`, `canada_imports_fpath`, `canada_szn_frac_fpath`, `hour_map_fpath`.

[Source and defaults](https://github.com/NatLabRockies/r2x-reeds/blob/ebb69534188c7b94933c36a534d84a651114e2f9/src/r2x_reeds/sysmod/imports.py).

### OptimalSitingConfig

Module: `r2x_reeds.sysmod.optimal_siting`.

Package fields: `loadsite_op_fpath`, `hour_map_myr_fpath`, `solve_year`.

[Source and defaults](https://github.com/NatLabRockies/r2x-reeds/blob/ebb69534188c7b94933c36a534d84a651114e2f9/src/r2x_reeds/sysmod/optimal_siting.py).
