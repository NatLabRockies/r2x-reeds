---
title: Inspect a saved system
---

Continue from the [fixture tutorial](/r2x-reeds/tutorials/parse-run/).
Use `outputs/pacific-system.json` and its generated sibling time-series directory.
These are Infrasys serialization, not a native PLEXOS, Sienna or upstream model file.

## Reload in the project environment

Open `python` in the tutorial workspace after completing the tutorial:

```python doctest
>>> from r2x_core import System
>>> from r2x_reeds import ReEDSRegion, ReEDSGenerator, ReEDSDemand
>>> system = System.from_json("outputs/pacific-system.json")
>>> assert len(list(system.get_components(ReEDSRegion))) == 11
>>> assert len(list(system.get_components(ReEDSGenerator))) == 673
>>> load = next(item for item in system.get_components(ReEDSDemand) if item.name == "p1_load")
>>> profile = system.get_time_series(load, name="max_active_power")
>>> assert profile.name == "max_active_power"
>>> assert len(profile.data) == 8760
>>> from datetime import datetime, timedelta
>>> from numpy.testing import assert_allclose
>>> assert profile.initial_timestamp == datetime(2012, 1, 1)
>>> assert profile.resolution == timedelta(hours=1)
>>> assert_allclose(profile.data[:3], [7662.1055, 7358.9473, 7142.1055], rtol=1e-6)
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

Install the published package into that CLI environment:

```bash
r2x install r2x-reeds
```

Installation changes the CLI managed environment. It is separate from the project's
`uv` environment. Serialized objects name their Python module and class, so the
matching package must be importable when loading them. Keep compatible Infrasys
and r2x-core versions with the environment that wrote the artifact.

For a repeatable CLI check, create `inspect_cli.py` in the same Python session.
The script uses `sys`, the system supplied by `r2x read`:

```python doctest
>>> from pathlib import Path
>>> inspection = """from r2x_reeds import ReEDSRegion, ReEDSGenerator, ReEDSDemand
... assert len(list(sys.get_components(ReEDSRegion))) == 11
... assert len(list(sys.get_components(ReEDSGenerator))) == 673
... load = next(item for item in sys.get_components(ReEDSDemand) if item.name == "p1_load")
... profile = sys.get_time_series(load, name="max_active_power")
... assert len(profile.data) == 8760
... print("Verified 11 regions, 673 generators and 8760 demand samples")
... """
>>> _ = Path("inspect_cli.py").write_text(inspection)
>>> exec(inspection, {"sys": system})
Verified 11 regions, 673 generators and 8760 demand samples
```

Run a repeatable inspection, without opening an interactive prompt:

```bash
r2x read outputs/pacific-system.json --exec inspect_cli.py
```

Expect `Verified 11 regions, 673 generators and 8760 demand samples`. Omit `--exec` for
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
