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

```python
from pathlib import Path
from r2x_reeds import ReEDSParser, ReEDSConfig, ReEDSRegion
from r2x_core.store import DataStore

# Configure
config = ReEDSConfig(
    solve_years=2030,
    weather_years=2012,
    case_name="High_Renewable"
)

# Load data using the default file mapping
file_mapping = ReEDSConfig.get_file_mapping_path()
data_store = DataStore.from_json(
    file_mapping,
    path=Path("path/to/reeds/outputs")
)

# Parse
parser = ReEDSParser(config, store=data_store, name="ReEDS_System")
system = parser.build_system()

# Access components
regions = list(system.get_components(ReEDSRegion))
print(f"Built system with {len(regions)} regions")
```

## Documentation Sections

- [Tutorials](tutorials/index.md) - Step-by-step learning guides
- [How-To Guides](how-tos/index.md) - Task-focused recipes
- [Explanations](explanations/index.md) - Architecture and design
- [References](references/index.md) - API and configuration reference

## Resources

- [Configuration Reference](references/configuration.md) - Configuration options and defaults
- [API Reference](references/api.md) - Complete API documentation
- [Parser Reference](references/parser.md) - Parser implementation details
- [Models Reference](references/models.md) - Component model documentation
- [R2X Core](https://github.com/NREL/r2x-core) - Core framework documentation

## Indices and Tables

- {ref}`genindex`
- {ref}`modindex`
- {ref}`search`
