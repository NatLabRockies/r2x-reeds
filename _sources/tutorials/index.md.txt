# Tutorials

This tutorial walks through a practical end-to-end workflow:

1. Parse a ReEDS run into an `infrasys.System`
2. Understand parser capabilities and outputs
3. Apply post-parse system modifiers (`sysmod`) in a recommended order

## 1. Parse A ReEDS Run

```python
from pathlib import Path

from r2x_core import DataStore, PluginContext
from r2x_reeds import ReEDSConfig, ReEDSParser

run_path = Path("/path/to/reeds_run")

config = ReEDSConfig(
	solve_year=2032,
	weather_year=2012,
	case_name="example",
	scenario="base",
)

ctx = PluginContext(
	config=config,
	store=DataStore.from_plugin_config(config, path=run_path),
)

result_ctx = ReEDSParser.from_context(ctx).run(ctx=ctx)
system = result_ctx.system
if system is None:
	raise RuntimeError("Parser returned no system")
```

## 2. What The Parser Already Builds

By default, the parser handles core ReEDS-to-R2X conversion:

- Region and transmission components
- Generator fleets (thermal, variable renewable, hydro, storage)
- Load components (`ReEDSDemand`) and base load time series
- Reserve components and reserve profiles
- Emission supplemental attributes
- Upgrade-aware preprocessing of run files before validation/build

Important modeling note:

- `electrolyzer` is excluded from the default generator pipeline (`defaults.json`), so electrolyzer/data-center purchaser loads are expected to be added via optional transforms.

## 3. Apply System Modifiers

The package exposes these transforms:

- `add-pcm-defaults`
- `add-emission-cap`
- `add-electrolyzer-load`
- `add-purchaser-load`
- `add-ccs-credit`
- `break-gens`
- `add-imports`
- `add-optimal-siting`

Recommended order for common workflows:

1. `add-pcm-defaults`
2. `break-gens` (if used)
3. `add-imports` and/or `add-electrolyzer-load` or `add-purchaser-load`
4. `add-optimal-siting`
5. `add-ccs-credit`
6. `add-emission-cap`

## 4. Purchaser-Load Tutorial (Electrolyzer + Data Center)

```python
from r2x_reeds.sysmod.purchaser_load import PurchaserLoadConfig, add_purchaser_load

res = add_purchaser_load(
	system,
	PurchaserLoadConfig(
		solve_year=2032,
		weather_year=2012,
		hour_map_myr_fpath=run_path / "inputs_case/rep/hmap_myr.csv",
		hydrogen_production_capacity_fpath=run_path / "outputs/cap.csv",
		consume_characteristics_fpath=run_path / "inputs_case/consume_char.csv",
		hydrogen_production_load_fpath=run_path / "outputs/prod_load.csv",
		hydrogen_production_annual_load_fpath=run_path / "outputs/prod_load_ann.csv",
		loadsite_op_fpath=run_path / "rep" / "outputs/loadsite_op.csv",
	),
)
if res.is_err():
	raise RuntimeError(res.unwrap_err())
system = res.unwrap()
```

## 5. Minimal Examples For Every System Modifier

### add-pcm-defaults

```python
from r2x_reeds.sysmod.pcm_defaults import PCMDefaultsConfig, add_pcm_defaults

res = add_pcm_defaults(
	system,
	PCMDefaultsConfig(
		pcm_defaults_fpath=run_path / "inputs_case/pcm_defaults.json",
		pcm_defaults_override=False,
	),
)
system = res.unwrap() if res.is_ok() else system
```

### break-gens

```python
from r2x_reeds.sysmod.break_gens import BreakGensConfig, break_generators

res = break_generators(
	system,
	BreakGensConfig(
		reference_units=None,
		drop_capacity_threshold=5,
		skip_categories=["wind", "solar"],
		break_category="category",
		# Optional targeting controls (omit to preserve default all-eligible behavior).
		# If multiple include_* lists are provided, they are combined with OR behavior.
		include_regions=["p1", "p2"],
		include_generators=["new-battery_2035"],
		include_technologies=["gas-cc"],
	),
)
system = res.unwrap() if res.is_ok() else system
```

### add-imports

```python
from r2x_reeds.sysmod.imports import ImportsConfig, add_imports

res = add_imports(
	system,
	ImportsConfig(
		solve_year=2035,
		weather_year=2012,
		canada_imports_fpath=run_path / "inputs_case/can_imports.csv",
		canada_szn_frac_fpath=run_path / "inputs_case/rep/can_imports_szn_frac.csv",
		hour_map_fpath=run_path / "inputs_case/rep/hmap_myr.csv",
	),
)
system = res.unwrap() if res.is_ok() else system
```

### add-electrolyzer-load (legacy path)

```python
from r2x_reeds.sysmod.electrolyzer import ElectrolyzerConfig, add_electrolizer_load

res = add_electrolizer_load(
	system,
	ElectrolyzerConfig(
		weather_year=2012,
		electrolyzer_load_fpath=run_path / "outputs/prod_load.csv",
		h2_fuel_price_fpath=run_path / "outputs/h2_price_month.csv",
		hour_map_fpath=run_path / "inputs_case/rep/hmap_allyrs.csv",
	),
)
system = res.unwrap() if res.is_ok() else system
```

### add-optimal-siting

```python
from r2x_reeds.sysmod.optimal_siting import OptimalSitingConfig, add_optimal_siting

res = add_optimal_siting(
	system,
	OptimalSitingConfig(
		solve_year=2032,
		loadsite_op_fpath=run_path / "outputs/loadsite_op.csv",
		hour_map_myr_fpath=run_path / "inputs_case/rep/hmap_myr.csv",
	),
)
system = res.unwrap() if res.is_ok() else system
```

### add-ccs-credit

```python
from r2x_reeds.sysmod.ccs_credit import CCSCreditConfig, add_ccs_credit

res = add_ccs_credit(
	system,
	CCSCreditConfig(
		co2_incentive_fpath=run_path / "outputs/co2_incentive.csv",
		emission_capture_rate_fpath=run_path / "outputs/emission_capture_rate.csv",
		upgrade_link_fpath=run_path / "outputs/upgrade_link.csv",
	),
)
system = res.unwrap() if res.is_ok() else system
```

### add-emission-cap

```python
from r2x_reeds.sysmod.emission_cap import EmissionCapConfig, add_emission_cap

res = add_emission_cap(
	system,
	EmissionCapConfig(
		emission_cap=None,
		co2_cap_fpath=run_path / "inputs_case/co2_cap.csv",
		switches_fpath=run_path / "inputs_case/switches.csv",
		emission_rates_fpath=run_path / "outputs/emit_rate.csv",
		default_unit="tonne",
	),
)
system = res.unwrap() if res.is_ok() else system
```

## 6. Chain Modifiers Programmatically

If you want a reusable transform pipeline, call each modifier with its own config model in sequence:

```python
from r2x_reeds.sysmod.emission_cap import EmissionCapConfig, add_emission_cap
from r2x_reeds.sysmod.optimal_siting import OptimalSitingConfig, add_optimal_siting
from r2x_reeds.sysmod.pcm_defaults import PCMDefaultsConfig, add_pcm_defaults
from r2x_reeds.sysmod.purchaser_load import PurchaserLoadConfig, add_purchaser_load

pipeline = [
	(add_pcm_defaults, PCMDefaultsConfig(pcm_defaults_fpath=run_path / "inputs_case/pcm_defaults.json")),
	(
		add_purchaser_load,
		PurchaserLoadConfig(
			solve_year=2032,
			weather_year=2012,
			hour_map_myr_fpath=run_path / "inputs_case/rep/hmap_myr.csv",
			loadsite_op_fpath=run_path / "outputs/loadsite_op.csv",
		),
	),
	(
		add_optimal_siting,
		OptimalSitingConfig(
			solve_year=2032,
			loadsite_op_fpath=run_path / "outputs/loadsite_op.csv",
			hour_map_myr_fpath=run_path / "inputs_case/rep/hmap_myr.csv",
		),
	),
	(add_emission_cap, EmissionCapConfig(co2_cap_fpath=run_path / "inputs_case/co2_cap.csv")),
]

for modifier_fn, modifier_cfg in pipeline:
	result = modifier_fn(system, modifier_cfg)
	if result.is_err():
		raise RuntimeError(f"{modifier_fn.__name__} failed: {result.unwrap_err()}")
	system = result.unwrap()
```

Continue with task-focused examples in the [How-To Guides](../how-tos/index.md).
