# Reference

R2X ReEDS provides a parser plugin for converting ReEDS model outputs to R2X format:

## Core Classes

- {py:class}`~r2x_reeds.ReEDSParser` - Main parser implementation
- {py:class}`~r2x_reeds.ReEDSConfig` - Configuration model

## System Modifiers

- `add-pcm-defaults`
- `add-emission-cap`
- `add-electrolyzer-load`
- `add-purchaser-load`
- `add-ccs-credit`
- `break-gens`
- `add-imports`
- `add-optimal-siting`

## Component Models

- {py:class}`~r2x_reeds.ReEDSGenerator` - Generator component
- {py:class}`~r2x_reeds.ReEDSRegion` - Region/bus component
- {py:class}`~r2x_reeds.ReEDSTransmissionLine` - Transmission line
- {py:class}`~r2x_reeds.ReEDSReserve` - Reserve requirement
- {py:class}`~r2x_reeds.ReEDSDemand` - Load/demand profile
- {py:class}`~r2x_reeds.ReEDSEmission` - Emission rate data

## Enumerations

- {py:class}`~r2x_reeds.EmissionType` - Emission type enumeration
- {py:class}`~r2x_reeds.ReserveType` - Reserve type enumeration
- {py:class}`~r2x_reeds.ReserveDirection` - Reserve direction enumeration

## Configuration and Assets

- [Configuration Reference](configuration.md) - `ReEDSConfig`, defaults, file mapping, parser rules
- [Transforms Reference](transforms.md) - available post-parse system modifiers
- [Upgrader Reference](upgrader.md) - ReEDS run version detection and upgrade steps

For detailed API documentation with examples and method signatures, see the [Complete API Documentation](./api.md).

## Documentation Coverage

```{eval-rst}
.. report:doc-coverage::
   :reportid: src
```

```{toctree}
:maxdepth: 1
:hidden:

api
configuration
transforms
upgrader
```
