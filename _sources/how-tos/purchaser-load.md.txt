# Add Purchaser Load Transform

Use the `add-purchaser-load` transform to attach purchaser-load consuming technologies after parsing a base ReEDS system.

This transform adds and/or updates:

- `ReEDSElectrolyzerDemand` components and hourly profiles
- `ReEDSSteamMethaneReformingDemand` components and hourly profiles
- `ReEDSDataCenterDemand` components and hourly profiles

## Why This Is A Transform

Purchaser load is intentionally handled outside the parser build flow so it can be enabled only when needed.

For the ReEDS electricity-consuming technologies handled here (`electrolyzer`, `smr` for steam methane reforming and `smr_ccs` for steam methane reforming with CCS), this transform also avoids duplicate creation by skipping `cap.csv`-based component creation when the corresponding demand component already exists in the system.

## Required Inputs

- `hour_map_myr_fpath`: path to `hmap_myr.csv`

## Optional Inputs

- `hydrogen_production_capacity_fpath`: path to `cap.csv` with hydrogen-production capacity
- `consume_characteristics_fpath`: path to `consume_char.csv` with electricity-consuming technology characteristics
- `hydrogen_production_load_fpath`: path to `prod_load.csv` with hydrogen-production demand profiles
- `hydrogen_production_annual_load_fpath`: path to `prod_load_ann.csv` with annual hydrogen-production demand
- `loadsite_op_fpath`: path to `loadsite_op.csv`
- `solve_year`
- `weather_year`

## Example

```python
from pathlib import Path

from r2x_core import DataStore, PluginContext
from r2x_reeds import ReEDSConfig, ReEDSParser
from r2x_reeds.sysmod.purchaser_load import PurchaserLoadConfig, add_purchaser_load

run_path = Path("path/to/reeds_run")

config = ReEDSConfig(
    solve_year=2032,
    weather_year=2012,
    case_name="test",
    scenario="base",
)
ctx = PluginContext(
    config=config,
    store=DataStore.from_plugin_config(config, path=run_path),
)

system = ReEDSParser.from_context(ctx).run().system

purchaser_cfg = PurchaserLoadConfig(
    solve_year=2032,
    weather_year=2012,
    hour_map_myr_fpath=run_path / "inputs_case/rep/hmap_myr.csv",
    hydrogen_production_capacity_fpath=run_path / "outputs/cap.csv",
    consume_characteristics_fpath=run_path / "inputs_case/consume_char.csv",
    hydrogen_production_load_fpath=run_path / "outputs/prod_load.csv",
    hydrogen_production_annual_load_fpath=run_path / "outputs/prod_load_ann.csv",
    loadsite_op_fpath=run_path / "outputs/loadsite_op.csv",
)

result = add_purchaser_load(system, purchaser_cfg)
if result.is_err():
    raise RuntimeError(result.unwrap_err())

system = result.unwrap()
```
