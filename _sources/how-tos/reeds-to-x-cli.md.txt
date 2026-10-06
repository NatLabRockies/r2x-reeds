# ReEDS to X with the CLI

Use the `r2x` CLI for standard ReEDS translations. This page covers pipeline YAML configuration, parser capabilities, system modifiers, and CLI validation. For Python runners with custom logic and target-system setup, see [ReEDS to X with Python scripts](reeds-to-x-script.md).

## Install Plugins

Install the plugins required by the translation target:

```bash
r2x install r2x-reeds
r2x install r2x-plexos
r2x install r2x-reeds-to-plexos
```

For ReEDS to Sienna, install `r2x-sienna` and `r2x-reeds-to-sienna` instead of the PLEXOS plugins.

## ReEDS to PLEXOS Pipeline

Save this as `reeds-to-plexos-pipeline.yaml` and replace the placeholder paths:

```yaml
variables:
  model_name: <reeds_run_name>
  output_dir: <output_path>
  reeds_run: <reeds_run_path>
  plexos_template: PLEXOS12.0
  solve_year: 2050
  weather_year: 2012

pipelines:
  r2p:
    - r2x-reeds.reeds-parser
    - r2x-reeds.break-gens
    - r2x-reeds.add-pcm-defaults
    - r2x-reeds-to-plexos.reeds-to-plexos
    - r2x-plexos.plexos-exporter

config:
  r2x-reeds.reeds-parser:
    path: ${reeds_run}
    solve_year: ${solve_year}
    weather_year: ${weather_year}
    case_name: <optional_case_label>
    scenario: base

  r2x-reeds.break-gens:
    drop_capacity_threshold: 5

  r2x-reeds.add-pcm-defaults:
    pcm_defaults_fpath: <path_to_pcm_defaults.json>
    pcm_defaults_override: true

  r2x-reeds-to-plexos.reeds-to-plexos:
    solve_year: ${solve_year}
    hydro_budget_ts: monthly

  r2x-plexos.plexos-exporter:
    model_name: ${model_name}
    weather_year: ${weather_year}
    horizon_year: ${solve_year}
    template: ${plexos_template}
    output_path: ${output_dir}

output_folder: ${output_dir}
```

`pcm_defaults_fpath` is optional. The parser can build a system without it, and `break-gens` uses package defaults when `reference_units` is omitted.

## Run and Inspect

```bash
r2x run reeds-to-plexos-pipeline.yaml r2p

# List pipeline names and steps
r2x run reeds-to-plexos-pipeline.yaml --list

# Print resolved variables and plugin configuration
r2x run reeds-to-plexos-pipeline.yaml --print r2p

# Preview without executing
r2x run reeds-to-plexos-pipeline.yaml r2p --dry-run
```

Use a scalar `weather_year` in CLI pipeline variables. Although `ReEDSConfig` accepts `int | list[int]`, the CLI pipeline and downstream transforms currently operate on one system per run. Run the pipeline once for each weather year when separate outputs are required.

## ReEDS to Sienna Pipeline

The same parser and modifier steps can feed a Sienna translation:

```yaml
pipelines:
  r2s:
    - r2x-reeds.reeds-parser
    - r2x-reeds.break-gens
    - r2x-reeds.add-pcm-defaults
    - r2x-reeds-to-sienna.reeds-to-sienna
    - r2x-sienna.sienna-exporter

config:
  r2x-reeds-to-sienna.reeds-to-sienna:
    solve_year: ${solve_year}

  r2x-sienna.sienna-exporter:
    model_year: ${solve_year}
    system_name: ${model_name}
    output_path: ${output_dir}/${model_name}.json
    system_base_power: 100.0
    scenario: base
```

Install the Sienna target plugins before running the pipeline:

```bash
r2x install r2x-sienna
r2x install r2x-reeds-to-sienna
r2x run reeds-to-sienna-pipeline.yaml r2s
```

## Parser Capabilities

Plugin id: `r2x-reeds.reeds-parser`

Required fields:

- `path`: ReEDS run folder used as the parser data store root.
- `solve_year`: solve year or list of solve years.
- `weather_year`: weather year or list of weather years.

Optional fields:

- `case_name`: case label stored in the system description.
- `scenario`: scenario label; defaults to `base`.
- `excluded_techs`: optional list of technologies to exclude. When omitted, the list from `defaults.json` is used.

The package defaults still contain `can-imports` in `excluded_techs`. To include it while keeping the other default exclusions,
set `excluded_techs` explicitly (for example, to the default list with `can-imports` removed), then apply `r2x-reeds.add-imports`
after the parser to attach the Canadian import time series.

```yaml
config:
  r2x-reeds.reeds-parser:
    path: /path/to/reeds/run
    solve_year: 2030
    weather_year: 2012
    excluded_techs:
      - electrolyzer
      - smr
      - smr_ccs
```

The parser supports CSV inputs and `outputs/outputs.h5`, with fallback to legacy output CSV files. It can build:

- Regions and transmission-region hierarchies.
- Thermal, variable renewable, storage, hydro, and consuming-technology components.
- Demand components and load profiles.
- Wind and solar capacity-factor profiles.
- Hydro profiles expanded from monthly data.
- Transmission interfaces and bidirectional lines.
- Reserve regions, requirements, and memberships.
- Generator emission supplemental attributes.
- ReEDS resource-supply-curve site components.
- Generator heat rates, outage rates, fuel prices, variable operating costs, storage properties, and startup costs.

Time series are truncated to 8760 values when a source contains more than one calendar year.

## System Modifiers

Insert modifiers after `r2x-reeds.reeds-parser`. Every modifier requires a matching configuration block under `config`. The full field descriptions are also available in the [transforms reference](../references/transforms.md).

### `r2x-reeds.break-gens`

Splits oversized generators into reference-sized units.

```yaml
r2x-reeds.break-gens:
  reference_units: <optional_json_path_or_mapping>
  drop_capacity_threshold: 5
  break_category: category
  skip_categories: [storage]
  include_regions: [p1, p2]
  include_generators: [generator_name]
  include_technologies: [coal-new]
```

`reference_units`, `drop_capacity_threshold`, `break_category`, `skip_categories`, `include_regions`, `include_generators`, and `include_technologies` are supported. Multiple include filters use OR behavior.

### `r2x-reeds.add-pcm-defaults`

Fills or overrides generator fields from PCM defaults.

```yaml
r2x-reeds.add-pcm-defaults:
  pcm_defaults_fpath: <path_to_pcm_defaults.json>
  pcm_defaults_dict: <optional_inline_mapping>
  pcm_defaults_override: false
```

### `r2x-reeds.add-emission-cap`

Adds an annual CO2 constraint and optional precombustion emissions.

```yaml
r2x-reeds.add-emission-cap:
  emission_cap: 1000000
  co2_cap_fpath: <optional_co2_cap.csv>
  switches_fpath: <optional_switches.csv>
  emission_rates_fpath: <optional_emission_rates.csv>
  default_unit: tonne
```

### `r2x-reeds.add-electrolyzer-load`

Adds legacy electrolyzer load and hydrogen fuel-price time series.

```yaml
r2x-reeds.add-electrolyzer-load:
  weather_year: ${weather_year}
  electrolyzer_load_fpath: <path_to_load.csv>
  h2_fuel_price_fpath: <path_to_h2_price.csv>
  hour_map_fpath: <path_to_hour_map.csv>
```

### `r2x-reeds.add-purchaser-load`

Adds hydrogen-production and data-center demand.

```yaml
r2x-reeds.add-purchaser-load:
  solve_year: ${solve_year}
  weather_year: ${weather_year}
  hydrogen_production_capacity_fpath: <optional_cap.csv>
  consume_characteristics_fpath: <optional_consume_char.csv>
  hydrogen_production_load_fpath: <optional_prod_load.csv>
  hydrogen_production_annual_load_fpath: <optional_prod_load_ann.csv>
  loadsite_op_fpath: <optional_loadsite_op.csv>
  hour_map_myr_fpath: <path_to_hmap_myr.csv>
```

### `r2x-reeds.add-ccs-credit`

Applies CCS incentives using three input files:

```yaml
r2x-reeds.add-ccs-credit:
  co2_incentive_fpath: <path_to_co2_incentive.csv>
  emission_capture_rate_fpath: <path_to_capture_rate.csv>
  upgrade_link_fpath: <path_to_upgrade_link.csv>
```

### `r2x-reeds.add-imports`

Adds Canadian import time series.

```yaml
r2x-reeds.add-imports:
  solve_year: ${solve_year}
  weather_year: ${weather_year}
  canada_imports_fpath: ${reeds_run}/inputs_case/can_imports.csv # specific path (for fast lookup)
  canada_szn_frac_fpath: ${reeds_run}/inputs_case/rep/can_imports_szn_frac.csv # specific path (for fast lookup)
  hour_map_fpath: ${reeds_run}/inputs_case/rep/hmap_myr.csv # specific path (for fast lookup)
```

### `r2x-reeds.add-optimal-siting`

Applies loadsite increments to existing demand profiles.

```yaml
r2x-reeds.add-optimal-siting:
  loadsite_op_fpath: <path_to_loadsite_op.csv>
  hour_map_myr_fpath: <path_to_hmap_myr.csv>
  solve_year: ${solve_year}
```

The parser must have attached demand time series before this modifier runs.

## Output Configuration

For PLEXOS, set `model_name`, `horizon_year`, `template`, and `output_path`. The exporter supports PLEXOS 9.0 through 12.0. For Sienna, set `model_year`, `system_name`, `output_path`, `system_base_power`, and `scenario`.
