```{toctree}
:maxdepth: 2
:hidden:

install
tutorials/index
how-tos/index
explanations/index
references/index
```

# R2X ReEDS Documentation

R2X ReEDS is an R2X Core plugin for parsing Regional Energy Deployment System (ReEDS) power system model data.

## About R2X ReEDS

R2X ReEDS provides a comprehensive parser for NREL's [ReEDS](https://github.com/NREL/ReEDS-2.0) model, enabling seamless data exchange with other power system modeling platforms through the R2X Core framework.

### Key Features

- Read ReEDS inputs and outputs from multiple file formats including CSV and H5
- Automatic component mapping for generators, regions, transmission lines, reserves, and emissions data
- Time series support for capacity factors, load profiles, and reserve requirements
- Pattern-based technology categorization to automatically handle different technology variants and naming conventions
- JSON-based configuration through defaults and file mapping specifications
- Built-in validation against actual data files to ensure data integrity
- Optional post-parse system modifiers for production workflows (PCM defaults, purchaser load, emission caps, and more)

**Time Series Truncation:**
```{note}
The ReEDS parser automatically truncates all time series data to 8760 values (hours in a standard year).
This ensures consistent annual resolution for hydro generation, renewable dispatch, load profiles, and reserve requirements, regardless of the original input length.
```

### Supported Components

- Solar generators including utility-scale photovoltaic, distributed photovoltaic, concentrating solar power, and photovoltaic with battery storage
- Wind generators for both onshore and offshore installations
- Thermal generation including coal, natural gas combined cycle and combustion turbine units, and nuclear power plants
- Hydroelectric facilities and energy storage systems
- Regional components modeled at the balancing authority level with transmission region hierarchies
- Transmission interfaces and lines with bidirectional capacity representation
- Reserve requirements by type including spinning reserves, regulation reserves, and flexibility reserves organized by region
- Demand profiles representing load by region over time
- Emission data including CO2 and NOX rates for each generator

## Quick Start

The recommended end-to-end workflow uses the `r2x` CLI. See [ReEDS to X with the
CLI](how-tos/reeds-to-x-cli.md) for installation, a complete pipeline
file, parser capabilities, all ReEDS system modifiers, and validation commands.

For a minimal parser-only pipeline:

```yaml
variables:
    reeds_run: <reeds_run_path>
    solve_year: 2050
    weather_year: 2012

pipelines:
    parse:
        - r2x-reeds.reeds-parser

config:
    r2x-reeds.reeds-parser:
        path: ${reeds_run}
        solve_year: ${solve_year}
        weather_year: ${weather_year}
```

Run it with:

```bash
r2x run reeds-parser-pipeline.yaml parse
```

Apply optional transforms after parsing by adding them to the pipeline and
giving each step a matching `config` block:

```yaml
- r2x-reeds.add-purchaser-load
- r2x-reeds.add-optimal-siting
```

## Documentation Sections

- [Tutorials](tutorials/index.md) - End-to-end examples and workflows
- [How-To Guides](how-tos/index.md) - Task-focused recipes for transforms and parsing
- [Explanations](explanations/index.md) - Architecture, lifecycle, and design rationale
- [References](references/index.md) - API, configuration assets, transforms, and upgrader details

## Resources

- [Configuration Reference](references/configuration.md) - Parser config, defaults, mappings, and rules
- [Transforms Reference](references/transforms.md) - Available system modifiers and expected inputs
- [Upgrader Reference](references/upgrader.md) - ReEDS version detection and upgrade pipeline
- [API Reference](references/api.md) - Complete API documentation
- [R2X Core](https://github.com/NREL/r2x-core) - Core framework documentation

## Indices and Tables

- {ref}`genindex`
- {ref}`modindex`
- {ref}`search`
