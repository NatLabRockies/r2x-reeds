---
title: Troubleshooting
---

Start from the first exception in the parser or modifier, not a later missing-component error.
Keep original ReEDS files and reproduce on a working copy: upgrades can modify input CSVs.
The [fixture tutorial](/r2x-reeds/tutorials/parse-run/) is the tested baseline; its counts
and calendar are not acceptance criteria for every ReEDS run.

## Python imports work, but the CLI cannot find `reeds-parser`

Check the two environments separately:

```bash
python -m pip show r2x-reeds r2x-core infrasys
r2x python show
r2x list r2x-reeds
r2x run reeds-parser --help
```

If Python finds the distribution but the CLI inventory lacks `reeds-parser`, it is
usually installed only in the project environment. Install it in the CLI runtime
with `r2x install r2x-reeds`, then repeat the last two commands. Expect the parser
and eight transforms. If Python itself cannot import the package, use the supported
Python 3.11–3.13 environment in [installation](/r2x-reeds/getting-started/installation/)
and run the [import check](/r2x-reeds/getting-started/verify/) there. Record all three
package versions before investigating API drift; upgrading one dependency blindly
can make a saved artifact harder to reproduce.

## A configured output file or HDF5 group is missing

The packaged `file_mapping.json` explicitly reads output groups from
`outputs/outputs.h5`; parser reads do not fall back to `outputs/<dataset>.csv`.
Core selects the reader from the configured file extension, but that does not
select an alternate source. A pipeline dry run cannot establish file or group
availability. From the run root, inspect the mapped file and its configured
reader keys:

```python
from pathlib import Path
root = Path("tutorial-inputs/test_Pacific")  # replace for your run
print(root.resolve())
for name in ("meta.csv", "inputs_case", "outputs"):
    print(name, (root / name).exists())
print(sorted(path.name for path in (root / "outputs").glob("*")))
```

Pass the root containing `meta.csv`, `inputs_case/` and `outputs/` to
`DataStore.from_plugin_config`. Then compare the file mapping's path and HDF5
`group_key`, `data_key` or `columns_key` with the run's actual report. Restore or
regenerate the mapped report from that completed ReEDS run if it is absent or
incomplete. Renaming an unrelated CSV or creating an empty placeholder does not
supply the required schema.

If the run provides CSV outputs, select them with a complete `file_mapping`
asset override. The
[configuration reference](/r2x-reeds/reference/configuration/) shows how to
modify the packaged mapping explicitly. Adjust those paths and reader settings
for the CSV files present in your run. The configured extension selects the
reader, while the mapping selects the source. Rerun the parser alone and inspect
regions, generators and demand before adding modifiers.

Choose the capacity series in the effective `file_mapping`: set the
`generator_inputs` table's `source` to `online_capacity_degraded` (HDF5 group
`cap_deg_ivrt`) or `online_capacity` (`cap_ivrt`). Verify the selected file and
group exist. A missing selected source is an input error, not a request to use the
other capacity series. The two series need not have the same MW values.

## `invalid HDF5 signature` or `file signature not found`

The mapped reader rejects an unreadable HDF5 binary, commonly an incomplete
copy or mislabeled file. Check the actual mapped file, not only its extension:

```python
from pathlib import Path
import h5py
path = Path("tutorial-inputs/test_Pacific/outputs/outputs.h5")
print(path.exists(), path.stat().st_size if path.exists() else None)
print(h5py.is_hdf5(path))
```

`False` means the HDF5 signature is absent. Re-copy or regenerate the binary from
the source run, then require `h5py.is_hdf5(path)` to return `True` and rerun parsing.
A valid signature alone does not prove the required groups exist. A permission
error is a different failure: verify read access to the reported path rather than
replacing good data. Source paths and input constraints are declared in
[file_mapping](/r2x-reeds/reference/configuration/).

## A requested year is absent

The solve year selects capacity. The profile calendar uses
`config.primary_weather_year`, the first configured weather year. After the same
`config` and `store` setup as the tutorial, inspect the mapped modeled years:

```python
print(store.read_data("modeled_years").collect())
print(config.solve_year, config.primary_weather_year)
```

Choose a solve year shown in that data. The configured `modeled_years` constraint
checks solve-year coverage. Verify that the selected load and renewable sources
contain the requested solve and weather years. Changing the solve year does not
supply missing weather data.

The generated profile calendar does not replace the `hour_map` or `hour_map_myr`
inputs used by representative-period modifiers. Restore a missing or malformed
mapping when a modifier requires it. No synthetic hour-map fallback is supplied.

Rerun parsing, then inspect profile length, initial timestamp and hourly resolution
as in [profile inspection](/r2x-reeds/tutorials/parse-run/#inspect-a-demand-profile).
The Pacific example has 8,760 samples beginning in 2012. Do not relabel source
calendars merely to match that example.

## Modifier succeeds but imports or purchaser loads are absent

Success may be a supported no-op when optional files are omitted. After parsing,
check the actual components rather than relying on the pipeline exit code:

```python
from r2x_reeds import ReEDSGenerator, ReEDSDemand
print(sorted({item.technology for item in system.get_components(ReEDSGenerator)}))
print([item.name for item in system.get_components(ReEDSDemand)])
```

Default generator exclusions include `can-imports`, `electrolyzer`, `smr` and
`smr_ccs`. Import budgets need parsed import generators and their mapped inputs;
purchaser demand needs its own production/site inputs. Use the exact configuration
and per-modifier checks in [PCM handoff](/r2x-reeds/how-to/pcm-handoff/), including
its explicit exclusion-list replacement. Never combine modern purchaser hydrogen
and legacy electrolyzer demand for the same load. Verify the added component names,
profile values and MW totals after each selected modifier. Production-only branches
need your real inputs; the public Pacific fixture does not demonstrate every branch.

If a modifier returns `Err`, inspect it immediately:

```python
if result.is_err():
    raise RuntimeError(str(result.unwrap_err()))
```

Fix the named file/column/calendar against the [transform contract](/r2x-reeds/reference/transforms/),
then rerun from a clean parser checkpoint. Continuing with the previous system hides
failed modifications and can double-apply later changes.

## Startup costs are inflated, or fixed O&M is missing

Inspect a matched technology before and after your modifiers:

```python
from r2x_reeds import ReEDSGenerator
print([(g.name, g.capacity, g.startup_cost, g.fom_cost)
       for g in system.get_components(ReEDSGenerator) if g.technology == "gas-cc"][:5])
```

Startup cost stays a **$/MW coefficient** through defaults and splitting. If a
custom step multiplied it by the original block capacity, remove that conversion
and rerun from the parser checkpoint; the target adapter must convert once using
final unit capacity. Verify the coefficient and reconcile removed MW when splitting
small remainders. The [PCM guide](/r2x-reeds/how-to/pcm-handoff/#1-add-operating-defaults-without-rescaling-startup-coefficients)
explains the unit boundary and override behavior.

A missing `fom_cost` is a separate known mapping gap tracked in
[issue 118](https://github.com/NatLabRockies/r2x-reeds/issues/118), not evidence that
startup defaults failed. The current mapping does not read `cost_fom`. Do not treat
`None` as zero or assume a downstream placeholder is calibrated; document the target
adapter's treatment and verify it before interpreting retirement rankings.

## Reload fails, or a loaded component has no expected profile

Use the same package versions that wrote the checkpoint first. A module-import
failure means the loading environment lacks a recorded component class; run the
installation verification there. For storage/profile failures, run
[the saved-system inspection](/r2x-reeds/how-to/inspect-system/) on the original
artifact and on its copied location. Preserve JSON together with its generated
sibling time-series directory, or copy the complete CLI ZIP artifact.

If the original works and the copy fails, recopy the complete artifact. If both
load but the named series is absent, compare the selected modifier, component name
and `list_time_series` output before assuming corruption. Verify counts, values,
start time and resolution after recovery. Do not hand-edit serialized class names
or storage paths. An Infrasys checkpoint still requires a separate target translator
and exporter; it is not native PLEXOS or Sienna input.

## Report a reproducible failure

Include the first full traceback or `unwrap_err()` text, exact command, Python/CLI
and package versions, source revision, solve/weather years, sanitized configuration,
input dataset names and schemas, and whether the public tutorial reproduces it.
For profile issues include length, first/last timestamps, resolution and units;
for modifier issues include before/after counts and capacities. State whether you
used original or upgraded inputs and whether the original checkpoint reloads.
Share a small synthetic or permitted input sample, not licensed/private run data.
[Open an issue](https://github.com/NatLabRockies/r2x-reeds/issues) with expected versus
observed behavior and the smallest failing step.
