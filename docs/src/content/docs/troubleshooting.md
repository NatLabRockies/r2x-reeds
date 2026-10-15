---
title: Troubleshooting
---

## Import or Python compatibility failure

Use Python 3.11–3.13. Verify the environment with
`python -m pip show r2x-reeds` in the activated environment.
A Python project environment and r2x-cli's managed runtime are separate; run
`r2x python show` and `r2x list r2x-reeds` when the CLI cannot discover the plugin.

## Missing files, datasets or version metadata

Pass the run root containing `inputs_case/`, `outputs/` and `meta.csv`, not an
individual output folder. Check the error's dataset against
[configuration mappings](/r2x-reeds/reference/configuration/).
Keep `outputs/outputs.h5` with its inputs or provide the mapped legacy CSV files.
Use a working copy for [input upgrades](/r2x-reeds/reference/upgrader/).

## Solve-year or weather-year validation failure

Choose years present in the run's modeled-year and time-profile inputs.
Start with scalar years as in [the tutorial](/r2x-reeds/tutorials/parse-run/).
The config accepts lists, but that does not imply every downstream transform or
exporter accepts a multi-year system.

## Missing import or purchaser components

The default exclusions include `can-imports`, `electrolyzer`, `smr` and `smr_ccs`.
Set `excluded_techs` explicitly when changing generator exclusions; provide the
appropriate [modifier inputs](/r2x-reeds/reference/transforms/) for import profiles
or purchaser demand. Do not assume omitted optional files create demand components.

## Pipeline dry run succeeds but execution fails

A dry run checks pipeline resolution and configuration without reading the actual
ReEDS data. Run the parser alone, inspect its first reported failure and verify
inputs before adding transforms or target plugins.

## Transform returns an error

Stop the chain and report `result.unwrap_err()` instead of silently continuing with
the old system. Recheck input paths, expected columns and required profiles against
the [transform reference](/r2x-reeds/reference/transforms/).

## Saved system loads but profile queries fail

**Symptom:** component queries work, but the expected hourly series is unavailable.
First check that the JSON's generated time-series directory was copied with it.
Then run the named-load inspection in the [saved-system guide](/r2x-reeds/how-to/inspect-system/).
Compare the profile name, length, timestamp and resolution with the tutorial.
A native target-format JSON is not an Infrasys checkpoint; use that target's parser.

## Wrong counts after changing inputs or options

Tutorial totals are fixture-specific. Recheck the selected solve/weather year,
scenario and enabled modifiers/profile options before treating a different total
as a parser defect. Use a fresh working copy and rerun the documented baseline.
If the baseline differs, record the package revision and the first failing input
or inspection check so the mismatch can be reproduced.
