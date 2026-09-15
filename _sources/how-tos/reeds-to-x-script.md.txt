# ReEDS to X with Python Scripts

Use a Python runner when a ReEDS translation needs conditional logic, selected generator filters, custom target-system setup, or target-specific time-series attachments. This page documents the pattern used by `_run_r2p_translations.py` and `_run_r2s_translations.py`.

For standard pipeline YAML workflows, see [ReEDS to X with the CLI](reeds-to-x-cli.md). The CLI guide documents parser capabilities and every available ReEDS system modifier.

## Install Plugins

Install the source parser, the target translator, and the target exporter:

```bash
# PLEXOS
r2x install r2x-reeds
r2x install r2x-plexos
r2x install r2x-reeds-to-plexos

# Sienna
r2x install r2x-reeds
r2x install r2x-sienna
r2x install r2x-reeds-to-sienna
```

The runner scripts are application-level code, not package entry points. Keep them in a translation workspace, replace input/output paths and case settings, and run them with the Python environment containing the required R2X packages.

## Common ReEDS Parser Setup

Both script workflows construct a `ReEDSConfig`, `DataStore`, and `PluginContext` before running the parser:

```python
from pathlib import Path
from typing import cast

from r2x_core import DataStore, PluginContext
from r2x_reeds import ReEDSConfig, ReEDSParser

run_path = Path("/path/to/reeds/run")
solve_year = 2050
weather_year = 2012

reeds_config = ReEDSConfig(
    solve_year=solve_year,
    weather_year=weather_year,
    case_name="my_reeds_case",
    scenario="base",
    models=("r2x_reeds.models", "r2x_plexos.models"),
)
store = DataStore.from_plugin_config(reeds_config, path=run_path)
context = PluginContext(config=reeds_config, store=store)
parser = cast(ReEDSParser, ReEDSParser.from_context(context))

result_context = parser.run()
if result_context.system is None:
    raise RuntimeError("ReEDS parser did not produce a system")

reeds_system = result_context.system
context.source_system = reeds_system
```

Use `models=("r2x_reeds.models", "r2x_sienna.models")` in the Sienna script. The models tuple makes target component models available while the source system is built.

## Applying Modifiers

Modifiers are Python functions that return a `rust_ok.Result`. Check each result before continuing:

```python
from r2x_reeds.sysmod.break_gens import BreakGensConfig, break_generators

break_result = break_generators(
    reeds_system,
    BreakGensConfig(
        drop_capacity_threshold=5,
        include_technologies=["coal-new", "coaloldscr"],
    ),
)
if break_result.is_err():
    raise RuntimeError(f"Generator splitting failed: {break_result.unwrap_err()}")
reeds_system = break_result.unwrap()
context.source_system = reeds_system
```

The same pattern applies to `add_pcm_defaults`, `add_emission_cap`, `add_electrolizer_load`, `add_purchaser_load`, `add_ccs_credit`, `add_imports`, and `add_optimal_siting`. Use the config models and input paths described in the [CLI system modifier reference](reeds-to-x-cli.md).

## Shared Translation Setup

The target translators use the source system's time-series storage. Convert it to Arrow storage before creating the target `TimeSeriesManager`:

```python
import json
from importlib.resources import files

from infrasys.time_series_models import TimeSeriesStorageType
from infrasys.time_series_manager import TimeSeriesManager
from infrasys.utils.sqlite import create_in_memory_db
from r2x_core import Rule

time_series_dir = reeds_system.get_time_series_directory()
reeds_system.convert_storage(
    time_series_directory=time_series_dir,
    time_series_storage_type=TimeSeriesStorageType.ARROW,
    permanent=True,
)

rules_path = files("<target_package>.config") / "rules.json"
context.rules = Rule.from_records(json.loads(rules_path.read_text()))

time_series_manager = TimeSeriesManager(
    create_in_memory_db(),
    time_series_directory=time_series_dir,
    time_series_storage_type=TimeSeriesStorageType.ARROW,
    permanent=True,
)
```

Replace `<target_package>` with `r2x_reeds_to_plexos` or `r2x_reeds_to_sienna`. The target system must use the same `time_series_manager` so translated time series remain available to the exporter.

## ReEDS to PLEXOS Script

The PLEXOS runner creates a target system, applies target rules, attaches target-specific time series, and invokes the exporter:

```python
from infrasys import System
from r2x_core import PluginContext, apply_rules_to_context
from r2x_plexos import PLEXOSConfig
from r2x_plexos.exporter import PLEXOSExporter
from r2x_reeds_to_plexos import (
    attach_region_load_time_series,
    attach_reserve_time_series,
    attach_time_series_to_generators,
)
from r2x_reeds_to_plexos.getters_utils import attach_time_series_to_purchasers
from r2x_reeds_to_plexos.plugin_config import ReedsToPlexosConfig

context.config = ReedsToPlexosConfig(hydro_budget_ts="weekly")
plexos_system = System(
    name="PLEXOS",
    auto_add_composed_components=True,
    time_series_manager=time_series_manager,
)
context.target_system = plexos_system

apply_rules_to_context(context)
attach_reserve_time_series(context)
attach_time_series_to_generators(context)
attach_region_load_time_series(context)
attach_time_series_to_purchasers(context)

exporter_context = PluginContext(
    config=PLEXOSConfig(
        model_name="my_reeds_case",
        timeseries_dir="/path/to/output",
        horizon_year=weather_year,
    ),
    system=plexos_system,
)
exporter = PLEXOSExporter.from_context(exporter_context)
exporter.output_path = "/path/to/output"
exporter.solve_year = solve_year
exporter.weather_year = weather_year
exporter.on_export()
```

The local `_run_r2p_translations.py` runner additionally applies purchaser-load and break-generators modifiers before translation. It attaches reserve, generator, regional-load, and purchaser profiles before exporting PLEXOS files.

## ReEDS to Sienna Script

The Sienna runner creates a Sienna target system, applies target rules, attaches generator emissions, and invokes the JSON exporter:

```python
from infrasys import System
from r2x_core import PluginContext, apply_rules_to_context
from r2x_reeds_to_sienna.getter_utils import add_generator_emissions
from r2x_sienna.exporter import SiennaExporter
from r2x_sienna.plugin_config import SiennaConfig

sienna_system = System(
    name="Sienna",
    auto_add_composed_components=True,
    time_series_manager=time_series_manager,
    system_base=100.0,
)
context.target_system = sienna_system

apply_rules_to_context(context)
add_generator_emissions(context)

output_file = "/path/to/output/my_reeds_case_ToSienna.json"
exporter_context = PluginContext(
    config=SiennaConfig(
        model_year=solve_year,
        system_name="my_reeds_case_ToSienna.json",
        output_path=output_file,
        system_base_power=100.0,
        scenario="base",
    ),
    system=sienna_system,
)
SiennaExporter.from_context(exporter_context).on_export()
```

Keep `add_generator_emissions(context)` when the Sienna target requires generator emissions in the exported system.

## Script Execution

Run either script from the environment where the source and target packages are installed:

```bash
python /path/to/_run_r2p_translations.py
python /path/to/_run_r2s_translations.py
```

For repeatable runs, move case names, solve years, weather years, input paths, output paths, and modifier selections into a configuration object or command-line arguments. Remove or disable `breakpoint()` calls in batch scripts, and create the output directory before invoking the exporter.
