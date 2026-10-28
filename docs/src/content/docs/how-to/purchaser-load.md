---
title: Add Purchaser Load Transform
---

For installation, follow the [published-package tutorial](/r2x-reeds/tutorials/parse-run/).
For the complete modifier sequence and alternative load representations, see
[prepare a PCM handoff](/r2x-reeds/how-to/pcm-handoff/).

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
- `solve_year`: optional scalar year used to select both input rows and the matching owner state
- `weather_year`: profile timestamp year

A yearless load input is associated with an explicitly configured scalar
`solve_year`. Without it, the rows remain unscoped and do not automatically
broadcast to every year-qualified owner. Use year-keyed inputs or configure the
target solve year.

<span id="example"></span>

## Check a small data-center profile

Continue from the fixture tutorial in the same Python session. This three-hour
synthetic example creates a separate data-center component in region `p1`.
It demonstrates the input contract and is not a complete annual demand case.
For hydrogen-production inputs, use the configuration reference and PCM handoff
schemas above.

```python doctest
>>> from pathlib import Path
>>> from tempfile import TemporaryDirectory
>>> import polars as pl
>>> from numpy.testing import assert_allclose
>>> from r2x_reeds import ReEDSDataCenterDemand
>>> from r2x_reeds.sysmod.purchaser_load import PurchaserLoadConfig, add_purchaser_load
>>> with TemporaryDirectory() as folder:
...     policy = Path(folder)
...     pl.DataFrame({"yearhour": [1, 2, 3], "h": ["h1", "h2", "h3"]}).write_csv(policy / "hours.csv")
...     pl.DataFrame({"r": ["p1", "p1", "p1"], "allh": ["h1", "h2", "h3"], "t": [2032, 2032, 2032], "Value": [5.0, 6.0, 7.0]}).write_csv(policy / "sites.csv")
...     purchaser_cfg = PurchaserLoadConfig(solve_year=2032, weather_year=2012, hour_map_myr_fpath=policy / "hours.csv", loadsite_op_fpath=policy / "sites.csv")
...     result = add_purchaser_load(system, purchaser_cfg)
...     assert result.is_ok(), result.unwrap_err()
...     demand = system.get_component(ReEDSDataCenterDemand, "p1_data_center_demand_2032")
...     assert demand.capacity == 7.0
...     series = system.get_time_series(demand, name="max_active_power")
...     assert_allclose(series.data, [5.0, 6.0, 7.0])
...
```

The assertions check both component capacity and actual profile values. The
original electric-demand component remains separate. For a production run,
reconcile its complete year with the selected weather calendar and avoid adding
the same site increments through `add-optimal-siting`.
