# Explanations

This section explains how r2x-reeds is organized and why specific design decisions were made.

## Parser Lifecycle

`ReEDSParser` follows the `r2x-core` plugin lifecycle:

1. `on_validate_config`: loads parser assets (defaults, file mappings, parser rules)
2. `on_upgrade`: applies version-aware run-file upgrades when needed
3. `on_validate`: validates solve/weather years and required datasets
4. `on_prepare`: prepares normalized data frames, time indices, and parser context
5. `on_build`: creates components and attaches time series

## Data Assets

Parser behavior is mostly data-driven through JSON config assets:

- `config/file_mapping.json`: dataset names, file paths, and preprocessing specs
- `config/defaults.json`: tech categories, exclusions, reserve defaults, and class mapping
- `config/parser_rules.json`: rule mappings from normalized rows into component kwargs

## Why Transforms Exist

Transforms in `sysmod/` are intentionally separate from parser build logic. This keeps parser output stable while allowing optional post-processing for scenario-specific workflows.

Examples:

- `add-pcm-defaults`: enriches generator fields from PCM defaults
- `add-emission-cap`: adds annual CO2 constraints
- `add-purchaser-load`: attaches electrolyzer and data center purchaser-load representation

```{toctree}
:maxdepth: 1
:hidden:

../references/transforms
../references/upgrader
```
