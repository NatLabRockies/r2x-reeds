---
title: Available system modifiers
---

System modifiers (sysmods) are optional steps that change a parsed ReEDS system
before translation by a separate target package. Start with
[installation](/r2x-reeds/getting-started/installation/) and
[parse a ReEDS run](/r2x-reeds/tutorials/parse-run/), then choose only the modifiers
needed for your case.

## Choose a modifier

These are all nine CLI plugin names registered under `r2x.transforms` in
[the package metadata](https://github.com/NatLabRockies/r2x-reeds/blob/86db7099fd409cff64f96e51b09a32a010b13cf5/pyproject.toml)
and exported by
[`r2x_reeds.plugins`](https://github.com/NatLabRockies/r2x-reeds/blob/86db7099fd409cff64f96e51b09a32a010b13cf5/src/r2x_reeds/plugins.py).
`reeds-parser` builds the initial system. It is not a sysmod.

| CLI plugin name | Purpose | Before using it |
| --- | --- | --- |
| `add-pcm-defaults` | Fill missing generator operating fields, or explicitly override them. | Supply a defaults JSON file or dictionary and review override behavior. |
| `break-gens` | Split aggregated generators into reference-sized units. | Review packaged or custom reference sizes and the threshold that discards small remainders. |
| `add-imports` | Attach daily Canadian import energy budgets (`hydro_budget`, GWh). | Keep import generators during parsing. Provide a weather year, annual imports, seasonal fractions and an hour map. Select the solve year for wide year-column inputs. |
| `add-exports` | Add hourly Canadian exports to existing regional electric-demand profiles (`max_active_power`, MW). | Provide existing regional demand profiles, a weather year, annual exports, representative-hour fractions and an hour map. Select the solve year for wide year-column inputs. |
| `add-purchaser-load` | Add hydrogen-production and/or data-center demand components and profiles. | Provide the multi-year hour map and applicable capacity, efficiency, production-load or loadsite inputs. Select matching solve/weather years. |
| `add-electrolyzer-load` | Add legacy fixed electrolyzer load and/or hydrogen fuel prices. | Provide a weather year, hour map and normalized load and/or price files. Use as an alternative to purchaser load for the same hydrogen demand. |
| `add-optimal-siting` | Add loadsite increments to existing electric-demand profiles. | Existing demand profiles, a loadsite file and multi-year hour map are required. Select the solve year for multi-year inputs. |
| `add-ccs-credit` | Apply capture incentives to eligible generators as negative $/MWh metadata. | Provide incentive, capture-rate and upgrade-link files. Confirm the target translator consumes the credit. |
| `add-emission-cap` | Record an annual CO2 limit, with optional precombustion adjustments. | Existing CO2 attributes and an explicit cap or normalized cap file are needed. Verify selected year, units and target handling. |

Several modifiers can return successfully without changing the system when
inputs or matching components are absent. Check the resulting components,
profiles and policy metadata. See [configuration fields and source](/r2x-reeds/reference/transforms/#configuration-fields-and-source)
for exact fields and defaults, and [prepare a PCM handoff](/r2x-reeds/how-to/pcm-handoff/)
for input schemas and checks for every modifier.

## Plan the sequence

Parse first and keep a parser-only checkpoint. The
[PCM handoff recipe](/r2x-reeds/how-to/pcm-handoff/#choose-a-sequence-and-avoid-double-counting)
applies capacity-dependent defaults before splitting, then adds selected demand,
incentives and constraints after the fleet representation is settled. This is a
starting recipe. Choose the sequence to match your data and target model.

- Use one representation of the same hydrogen demand: purchaser load or legacy electrolyzer load.
- Do not add the same data-center loadsite increments through both purchaser load and optimal siting.
- Retain import generators during parsing: remove `can-imports` from `excluded_techs` while preserving the other exclusions when import budgets are needed.
- `add-exports` increments existing regional demand profiles; it does not require `can-exports` generators to be parsed.
- Preserve startup-cost coefficients in $/MW through defaults and splitting. The target exporter performs the capacity conversion once.

## Discover your installed plugins

With [r2x-cli](https://github.com/NatLabRockies/r2x-cli#install) and `r2x-reeds`
installed in its managed environment, run this read-only command from any directory:

```bash
r2x list r2x-reeds
```

Expect `reeds-parser` and the modifiers installed with your package version,
along with their configuration fields. The CLI environment is separate from a
Python virtual environment.

To inspect one modifier's options without executing it:

```bash
r2x run add-pcm-defaults --help
```

Expect plugin-specific options and input/output flags. Use
[CLI pipelines](/r2x-reeds/how-to/reeds-to-x-cli/) or
[Python modifiers](/r2x-reeds/how-to/reeds-to-x-script/) to compose selected steps.
Continue with [purchaser load](/r2x-reeds/how-to/purchaser-load/) for that demand
workflow and [saved-system inspection](/r2x-reeds/how-to/inspect-system/) to check
the result before handing it to a target translator.
