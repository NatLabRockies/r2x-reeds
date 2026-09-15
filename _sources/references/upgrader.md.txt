# Upgrader Reference

r2x-reeds includes a ReEDS data upgrader to normalize input runs before parsing.

## Core Types

- `ReEDSVersionDetector`
- `ReEDSUpgrader`
- `run_reeds_upgrades(...)`

## Version Detection

`ReEDSVersionDetector` reads `meta.csv` and uses the `tag` column when available.

Fallback behavior:

- If the `tag` column is missing or empty, a legacy version marker is used.

## Upgrade Execution

`ReEDSUpgrader.upgrade(...)` executes upgrade steps from `upgrader/upgrade_steps.py` using `r2x-core` upgrade abstractions.

Common triggers include:

- missing or renamed input files
- schema normalization required by current parser mappings

## Parser Integration

`ReEDSParser` calls upgrade logic during lifecycle before validation:

1. config validation and rule loading
2. file upgrade pass
3. input validation and build

This guarantees parser assumptions match the effective run-file schema.
