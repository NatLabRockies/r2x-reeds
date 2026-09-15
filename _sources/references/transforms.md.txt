# Transforms Reference

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

Each transform accepts a plugin-specific configuration model. The complete CLI
configuration examples and field descriptions are in the [ReEDS to PLEXOS CLI
guide](../how-tos/reeds-to-x-cli.md).

| Transform | Configuration model | Main purpose |
| --- | --- | --- |
| `break-gens` | `BreakGensConfig` | Split oversized generators into reference units |
| `add-pcm-defaults` | `PCMDefaultsConfig` | Fill or override generator attributes |
| `add-emission-cap` | `EmissionCapConfig` | Add an annual CO2 constraint |
| `add-electrolyzer-load` | `ElectrolyzerConfig` | Add legacy electrolyzer and hydrogen-price data |
| `add-purchaser-load` | `PurchaserLoadConfig` | Add hydrogen-production and data-center demand |
| `add-ccs-credit` | `CCSCreditConfig` | Apply CCS incentives |
| `add-imports` | `ImportsConfig` | Add Canadian import time series |
| `add-optimal-siting` | `OptimalSitingConfig` | Apply loadsite increments to demand profiles |

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
