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

## `Required dataset '…' not found in outputs.h5 or fallback CSV`

This message means neither the mapped HDF5 group nor its supported CSV fallback
provided the required dataset. A pipeline dry run cannot establish file availability.
From the tutorial workspace, inspect the run root:

```python doctest
>>> from pathlib import Path
>>> root = Path("tutorial-inputs/test_Pacific")  # replace for your run
>>> assert root.is_dir()
>>> assert all((root / name).exists() for name in ("meta.csv", "inputs_case", "outputs"))
>>> assert list((root / "outputs").glob("*"))
```

A failed directory assertion often means the parser was pointed at `outputs/` or an extra enclosing
folder. Pass the root containing all three items to `DataStore.from_plugin_config`.
If the root is correct, compare the named dataset with the
[configuration mappings](/r2x-reeds/reference/configuration/) and restore/regenerate
that actual report from the same completed ReEDS run. Renaming an unrelated CSV
or creating an empty placeholder does not supply its schema. Rerun the parser alone
and inspect regions, generators and demand before adding modifiers.

For `Degraded capacity dataset 'cap_deg_ivrt' was not found`, the request came from
`use_degraded_capacity=True`. Supply degradation-adjusted capacity output, or use
`False` only if undegraded `cap_ivrt` capacity is the intended modeling choice.
Verify capacities after rerunning; the choices need not give the same MW.

## `invalid HDF5 signature` or `file signature not found`

The validation helper identifies an unreadable HDF5 binary, commonly an incomplete
copy or mislabeled file. Check the actual mapped file, not only its extension:

```python doctest
>>> from pathlib import Path
>>> import h5py
>>> path = Path("tutorial-inputs/test_Pacific/inputs_case/load.h5")
>>> assert path.is_file() and path.stat().st_size > 0
>>> assert h5py.is_hdf5(path)
```

This checks the fixture load binary. Replace the path with the reported failing file for your run. A false `h5py.is_hdf5` result means the HDF5 signature is absent. Re-copy or regenerate the binary from
the source run, then require `h5py.is_hdf5(path)` to return `True` and rerun parsing.
A valid signature alone does not prove the required groups exist. A permission
error is a different failure: verify read access to the reported path rather than
replacing good data. See the
[validation implementation and tests](https://github.com/NatLabRockies/r2x-reeds/blob/86db7099fd409cff64f96e51b09a32a010b13cf5/tests/test_parser_checks.py).

## A requested year is absent, or `hour_map` validation fails

The solve year selects capacity; the weather year selects hourly data. After the
same `config` and `store` setup as the tutorial, inspect the mapped modeled years:

```python doctest
>>> modeled = store.read_data("modeled_years").collect()
>>> assert not modeled.is_empty()
>>> assert config.primary_solve_year == 2032
>>> assert config.primary_weather_year == 2012
```

Choose a solve year shown in that data. An error listing available weather years
must be resolved against the run's own hour map and profiles, not by substituting
the solve year. `hour_map file exists but contains no rows` and a missing `year`
column are malformed-input failures. Restore the matching hour map from the run;
do not delete it to force the parser's missing-file fallback. Rerun the parser,
then inspect profile length, initial timestamp and hourly resolution as in
[profile inspection](/r2x-reeds/tutorials/parse-run/#inspect-a-demand-profile).
The Pacific example has 8,760 samples beginning in 2012; do not pad, truncate or
relabel other calendars merely to match that example.

## Modifier succeeds but imports or purchaser loads are absent

Success may be a supported no-op when optional files are omitted. After parsing,
check the actual components rather than relying on the pipeline exit code:

```python doctest
>>> from r2x_reeds import ReEDSGenerator, ReEDSDemand
>>> technologies = {item.technology for item in system.get_components(ReEDSGenerator)}
>>> assert "gas-cc" in technologies
>>> assert any(item.name == "p1_load" for item in system.get_components(ReEDSDemand))
```

Default generator exclusions include `can-imports`, `can-exports`,
`electrolyzer`, `smr` and `smr_ccs`. Import budgets need matching parsed import
generators; Canadian export demand is added to existing regional
`ReEDSDemand` profiles and does not use export generators. Purchaser demand
needs its own production/site inputs. Use the exact configuration
and per-modifier checks in [PCM handoff](/r2x-reeds/how-to/pcm-handoff/), including
its explicit exclusion-list replacement. Never combine modern purchaser hydrogen
and legacy electrolyzer demand for the same load. Verify the added component names,
profile values and MW totals after each selected modifier. Production-only branches
need your real inputs; the public Pacific fixture does not demonstrate every branch.

If a modifier returns `Err`, inspect it immediately:

```python doctest
>>> from r2x_reeds.sysmod.break_gens import BreakGensConfig, break_generators
>>> result = break_generators(system, BreakGensConfig(reference_units="missing-reference.json"))
>>> assert result.is_err()
>>> assert "Reference technologies file not found" in result.unwrap_err()
```

Fix the named file/column/calendar against the [transform contract](/r2x-reeds/reference/transforms/),
then rerun from a clean parser checkpoint. Continuing with the previous system hides
failed modifications and can double-apply later changes.

## Startup costs are inflated, or fixed O&M is missing

Inspect a matched technology before and after your modifiers:

```python doctest
>>> from r2x_reeds import ReEDSGenerator
>>> matched = [g for g in system.get_components(ReEDSGenerator) if g.technology == "gas-cc"]
>>> assert matched
>>> assert all(g.capacity > 0 for g in matched)
>>> assert all(g.fom_cost is not None for g in matched)
```

Startup cost stays a **$/MW coefficient** through defaults and splitting. If a
custom step multiplied it by the original block capacity, remove that conversion
and rerun from the parser checkpoint; the target adapter must convert once using
final unit capacity. Verify the coefficient and reconcile removed MW when splitting
small remainders. The [PCM guide](/r2x-reeds/how-to/pcm-handoff/#1-add-operating-defaults-without-rescaling-startup-coefficients)
explains the unit boundary and override behavior.

Current source reads solve-year fixed O&M from `cost_fom` and the operating-cost
input tables. Missing required data raises a dataset error. Published older
versions can differ, so record the installed package and source revision.
Do not treat a missing `fom_cost` as zero. Check mapped reports, selected year and
[configuration](/r2x-reeds/reference/configuration/) before interpreting retirement rankings.

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
