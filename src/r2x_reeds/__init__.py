"""R2X ReEDS Plugin.

A plugin for parsing ReEDS (Regional Energy Deployment System) model data
into the R2X framework using infrasys components.
"""

from importlib.metadata import version

from loguru import logger

__version__ = version("r2x_reeds")

from .config import ReEDSConfig
from .models import (
    EmissionRate,
    EmissionType,
    EnergyMWh,
    FromTo_ToFrom,
    Percentage,
    PowerMW,
    ReEDSComponent,
    ReEDSDemand,
    ReEDSEmission,
    ReEDSGenerator,
    ReEDSInterface,
    ReEDSRegion,
    ReEDSReserve,
    ReEDSReserveRegion,
    ReEDSResourceClass,
    ReEDSTransmissionLine,
    ReserveDirection,
    ReserveType,
    TimeHours,
)
from .parser import ReEDSParser

# Disable default loguru handler for library usage
# Applications using this library should configure their own handlers
logger.disable("r2x_reeds")

latest_commit = "401c0bb15cbf93d2ff9696b14b799edad763247a"

__all__ = [
    "EmissionRate",
    "EmissionType",
    "EnergyMWh",
    "FromTo_ToFrom",
    "Percentage",
    "PowerMW",
    "ReEDSComponent",
    "ReEDSConfig",
    "ReEDSDemand",
    "ReEDSEmission",
    "ReEDSGenerator",
    "ReEDSInterface",
    "ReEDSParser",
    "ReEDSRegion",
    "ReEDSReserve",
    "ReEDSReserveRegion",
    "ReEDSResourceClass",
    "ReEDSTransmissionLine",
    "ReserveDirection",
    "ReserveType",
    "TimeHours",
    "__version__",
]
