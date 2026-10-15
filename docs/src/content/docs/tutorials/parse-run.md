---
title: Parse, modify and reload a ReEDS fixture
---

Turn the repository's Pacific test run into a saved, inspectable system. You will
read ReEDS data, inspect an hourly demand profile, split aggregated generators
into reference-sized units, and reload the result with Infrasys-compatible APIs.
No licensed target-model software or external ReEDS run is needed for this fixture.

## What you will build

```mermaid
flowchart TD
  A["Pacific fixture copy<br/>2032 capacity, 2012 weather"] --> B["ReEDSParser<br/>regions, generators, demand"]
  B --> C["Inspect hourly demand"]
  C --> D["break_generators<br/>reference-sized units"]
  D --> E["Infrasys JSON<br/>and time-series directory"]
  E --> F["Reload and compare counts"]
```

The saved artifact contains ReEDS components, not a PLEXOS or Sienna export.
Target conversion is a later step performed by [R2X translation plugins](https://github.com/NatLabRockies/R2X).

## Prepare a source checkout

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), Git and Python
3.11–3.13. The package depends on [r2x-core](https://github.com/NatLabRockies/r2x-core),
which supplies contexts and data stores, and [Infrasys](https://github.com/NatLabRockies/infrasys),
which manages components and time-series storage. `uv sync` installs those dependencies.

Clone a disposable checkout so the public fixture and installed source agree:

```bash
git clone https://github.com/NatLabRockies/r2x-reeds.git
```

Enter it and install the locked environment:

```bash
cd r2x-reeds
uv sync --locked --no-dev
```

Extract the fixture into a working directory. The parser can upgrade run files,
so keep the archive unchanged. The extracted run uses roughly 62 MB:

```bash
uv run python -m zipfile -e tests/data/test_Pacific.zip tutorial-inputs
```

Check the run root before proceeding:

```bash
ls tutorial-inputs/test_Pacific
```

Expect `meta.csv`, `inputs_case/` and `outputs/`. Run the remaining commands from
the repository root; `path` must point to this run root, not just `outputs/`.

## Parse the selected solve and weather years

Save this as `parse_reeds.py`:

```python
from pathlib import Path
from r2x_core import DataStore, PluginContext
from r2x_reeds import ReEDSConfig, ReEDSParser, ReEDSRegion, ReEDSGenerator

run_path = Path("tutorial-inputs/test_Pacific")
config = ReEDSConfig(
    solve_year=2032,
    weather_year=2012,
    case_name="Pacific-2032",
)
store = DataStore.from_plugin_config(config, path=run_path)
context = PluginContext(config=config, store=store)
system = ReEDSParser.from_context(context).run().system
if system is None:
    raise RuntimeError("Parser returned no system")
print("Regions:", len(list(system.get_components(ReEDSRegion))))
print("Generators before:", len(list(system.get_components(ReEDSGenerator))))
```

`solve_year` selects the investment/capacity snapshot; `weather_year` selects
profile data. These are different choices. The context ties configuration and
its mapped input datasets together; `run()` executes the lifecycle and returns
that context. See [the API contract](/r2x-reeds/reference/python-api/).

Run the script:

```bash
uv run python parse_reeds.py
# Regions: 11
# Generators before: 292
```

These counts describe the checked-in fixture, not an arbitrary ReEDS case.
For a real run, choose years present in that run and compare its region names
and capacities before translation. [Troubleshooting](/r2x-reeds/troubleshooting/)
explains missing-data and year errors.

## Inspect a demand profile

Append this to the script:

```python
from r2x_reeds import ReEDSDemand

load = next(system.get_components(ReEDSDemand))
profile = system.list_time_series(load)[0]
print("Demand:", load.name)
print("Series:", profile.name)
print("Hours:", len(profile.data))
print("Start:", profile.initial_timestamp)
print("Resolution:", profile.resolution)
print("First values:", profile.data[:3])
assert len(profile.data) == 8760
```

Run the same command again. Expect demand `p1_load`, series `max_active_power`,
8,760 values, a start of `2012-01-01 00:00:00`, and one-hour resolution.
The first three values are approximately `7662.1055`, `7358.9473`, `7142.1055`.
A correct component count alone would not catch a wrong weather year or profile
resolution; inspect both the graph and the attached time series.

## Apply an explicit modifier

ReEDS investment blocks are aggregated units. `break_generators` can split them
using the package's reference sizes. Append:

```python
from r2x_reeds.sysmod.break_gens import BreakGensConfig, break_generators

result = break_generators(system, BreakGensConfig(drop_capacity_threshold=5))
if result.is_err():
    raise RuntimeError(result.unwrap_err())
system = result.unwrap()
print("Generators after:", len(list(system.get_components(ReEDSGenerator))))
```

Re-run the script. The fixture now has **673 generators**, while its regions stay
at 11. `drop_capacity_threshold` controls small remainders in MW; splitting is a
modeling choice, not a requirement for every target. The function mutates the
system and returns a `Result`; check failure before continuing. For targeted
splitting and reference-unit overrides, see [Python composition](/r2x-reeds/how-to/reeds-to-x-script/)
and [transform configuration](/r2x-reeds/reference/transforms/).

## Save and reload the modified system

Append this final block:

```python
from r2x_core import System

output = Path("outputs/pacific-system.json")
output.parent.mkdir(parents=True, exist_ok=True)
system.to_json(output, overwrite=True)
restored = System.from_json(output)
print("Reloaded regions:", len(list(restored.get_components(ReEDSRegion))))
print("Reloaded generators:", len(list(restored.get_components(ReEDSGenerator))))
assert len(list(restored.get_components(ReEDSGenerator))) == 673
```

`overwrite=True` deliberately replaces this tutorial output when you rerun the
script. Use a fresh path or leave overwrite disabled for production snapshots.
Expect `Reloaded regions: 11` and `Reloaded generators: 673`.

```bash
ls outputs
```

Keep `pacific-system.json` and its sibling `pacific-system_time_series/` directory
together. The JSON stores component relationships; the directory holds the attached
series. Moving only the JSON is not a complete transfer.

## Inspect from the CLI or continue to a target

The [saved-system guide](/r2x-reeds/how-to/inspect-system/) shows `r2x read` and
repeatable inspection scripts. It uses the CLI's own environment; the source
checkout's `uv` environment is separate.

For a native target export, continue with [ReEDS to PLEXOS](https://natlabrockies.github.io/R2X/how-to/reeds-to-plexos/)
or [ReEDS to Sienna](https://natlabrockies.github.io/R2X/how-to/reeds-to-sienna/).
Those workflows add a translator and target exporter after the parser; the
serialized ReEDS JSON above is not either target's native format.

This tutorial was executed with the package's locked r2x-core 0.9.0 environment.
The count/profile/reload checks apply to this fixture revision and selected years.
