---
title: Troubleshooting
---

## Import or Python compatibility failure

Use Python 3.11–3.13. Verify the environment with
`uv run python -c "import r2x_reeds; print(r2x_reeds.__version__)"`.
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
