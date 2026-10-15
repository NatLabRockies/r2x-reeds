---
title: Parser and transform boundaries
---

The parser uses three packaged JSON assets: `file_mapping.json` defines datasets
and preprocessing, `defaults.json` defines categories and model defaults, and
`parser_rules.json` maps normalized rows into component fields. Configuration
selects solve/weather years and exclusions before the system is built.

Dataset loading supports an output HDF5 bundle with legacy CSV fallbacks. Preparation
normalizes generator and hydro data, reserve inputs and time indices. Construction
creates regions, generators, demand, transmission, reserves and supplemental
emission data, then attaches supported profiles. Input upgrades are part of the
parser integration and can modify run files; preserve original inputs.

Optional transforms live in `sysmod/`. They add scenario-specific behavior such as
purchaser demand, generator splitting, imports or emission caps. Select transforms
based on the modeling task; there is no universal sequence for every target.
For example, optimal siting needs existing demand time series.

`r2x-reeds` retains ReEDS-specific components. Target translators map them to another
model; exporters then write that model's format. A successful parser run is only
one stage of a translation. See [R2X architecture](https://natlabrockies.github.io/R2X/explanation/architecture/)
for those package boundaries and [reference](/r2x-reeds/reference/) for this parser's contracts.
