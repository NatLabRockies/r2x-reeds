---
title: Inspect a saved system
---

Continue from the [fixture tutorial](/r2x-reeds/tutorials/parse-run/).
Use `outputs/pacific-system.json` and its generated sibling time-series directory.
These are Infrasys serialization, not a native PLEXOS, Sienna or upstream model file.

## Reload in the project environment

Save this as `inspect_saved.py` in the checkout:

```python
from r2x_core import System
from r2x_reeds import ReEDSRegion, ReEDSGenerator, ReEDSDemand

system = System.from_json("outputs/pacific-system.json")
for component_type in (ReEDSRegion, ReEDSGenerator):
    print(component_type.__name__, len(list(system.get_components(component_type))))
load = next(item for item in system.get_components(ReEDSDemand) if item.name == "p1_load")
profile = system.get_time_series(load, name="max_active_power")
print(profile.name, len(profile.data))
print(profile.initial_timestamp, profile.resolution)
print(profile.data[:3])
```

```bash
uv run python inspect_saved.py
```

For the completed tutorial, expect ReEDSRegion 11; ReEDSGenerator 673, followed by an 8,760-value
`max_active_power` profile. This checks both component reconstruction and attached storage.
Compare timestamps and first values with the tutorial. For another dataset, replace
the fixture-specific component name rather than silently selecting an unrelated load.

## Inspect with r2x-cli

Install [r2x-cli](https://github.com/NatLabRockies/r2x-cli#install), then inspect its
managed environment:

```bash
r2x python show
```

From this source checkout, install the package into that CLI environment:

```bash
r2x install .
```

Installation changes the CLI managed environment. It is separate from the project's
`uv` environment. Serialized objects name their Python module and class, so the
matching package must be importable when loading them. Keep compatible Infrasys
and r2x-core versions with the environment that wrote the artifact.

Save this as `inspect_cli.py`. `r2x read` supplies the loaded system as `sys`:

```python
from r2x_reeds import ReEDSRegion, ReEDSGenerator, ReEDSDemand

print("ReEDSRegion:", len(list(sys.get_components(ReEDSRegion))))
print("ReEDSGenerator:", len(list(sys.get_components(ReEDSGenerator))))
load = next(item for item in sys.get_components(ReEDSDemand) if item.name == "p1_load")
for profile in sys.list_time_series(load):
    print(profile.name, len(profile.data), profile.data[:3])
```

Run a repeatable inspection, without opening an interactive prompt:

```bash
r2x read outputs/pacific-system.json --exec inspect_cli.py
```

Expect the same counts and profile values as the Python loader. Omit `--exec` for
an interactive session; type `exit()` to leave it. The first read may install
CLI runtime dependencies. The JSON inspection command was executed with r2x-cli
0.1.15 in an isolated Python 3.12 environment containing the package's locked dependencies.

For an archive produced by `r2x run ... --zip -o outputs/system.zip`, pass `--zip`
to `r2x read`. Do not add `--zip` when loading the JSON file above.
See [R2X artifact inspection](https://natlabrockies.github.io/R2X/how-to/inspect-transformed-system/)
for the distinction between a serialized system and a native target export.

## Recover a failed reload

- `ModuleNotFoundError`: install the package owning the recorded class in the **loading** environment.
- Missing time-series storage: restore the sibling directory beside the JSON; copying JSON alone is insufficient.
- Existing output on a rerun: choose a fresh filename or deliberately set `overwrite=True` in your writer.
- Counts differ: confirm that you loaded the modified/tutorial artifact and selected the same scenario/years.

Continue with [troubleshooting](/r2x-reeds/troubleshooting/) rather than renaming an
arbitrary target-format JSON to make it look like Infrasys serialization.
