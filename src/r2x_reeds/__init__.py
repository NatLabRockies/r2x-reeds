"""R2X ReEDS Plugin.

A plugin for parsing ReEDS (Regional Energy Deployment System) model data
into the R2X framework using infrasys components.
"""

from importlib.metadata import version

from loguru import logger

__version__ = version("r2x_reeds")

# Import getters to register them with r2x-core
from . import getters  # noqa: F401
from .data_readers import register_modeled_years_reader
from .models import (
    EmissionRate,
    EmissionType,
    FromTo_ToFrom,
    Percentage,
    ReEDSComponent,
    ReEDSConsumingTechnology,
    ReEDSDataCenterDemand,
    ReEDSDemand,
    ReEDSElectrolyzerDemand,
    ReEDSEmission,
    ReEDSGenerator,
    ReEDSH2Pipeline,
    ReEDSH2Storage,
    ReEDSHydroGenerator,
    ReEDSInterface,
    ReEDSRegion,
    ReEDSReserve,
    ReEDSReserveRegion,
    ReEDSResourceBuild,
    ReEDSResourceClass,
    ReEDSResourceSite,
    ReEDSSteamMethaneReformingDemand,
    ReEDSStorage,
    ReEDSThermalGenerator,
    ReEDSTransmissionLine,
    ReEDSVariableGenerator,
    ReserveDirection,
    ReserveType,
)
from .parser import ReEDSParser
from .plugin_config import ReEDSConfig
from .region_mapping import (
    CountyMembership,
    CountyMembershipError,
    RegionAlignment,
    RegionAlignmentError,
    RegionAlignmentPolicy,
    RegionMatch,
    RegionResolution,
    align_regions,
    load_county_membership,
    normalize_county_fips,
)
from .upgrader import ReEDSUpgrader

logger.disable("r2x_reeds")

latest_commit = "401c0bb15cbf93d2ff9696b14b799edad763247a"

__all__ = [
    "CountyMembership",
    "CountyMembershipError",
    "EmissionRate",
    "EmissionType",
    "FromTo_ToFrom",
    "Percentage",
    "ReEDSComponent",
    "ReEDSConfig",
    "ReEDSConsumingTechnology",
    "ReEDSDataCenterDemand",
    "ReEDSDemand",
    "ReEDSElectrolyzerDemand",
    "ReEDSEmission",
    "ReEDSGenerator",
    "ReEDSH2Pipeline",
    "ReEDSH2Storage",
    "ReEDSHydroGenerator",
    "ReEDSInterface",
    "ReEDSParser",
    "ReEDSRegion",
    "ReEDSReserve",
    "ReEDSReserveRegion",
    "ReEDSResourceBuild",
    "ReEDSResourceClass",
    "ReEDSResourceSite",
    "ReEDSSteamMethaneReformingDemand",
    "ReEDSStorage",
    "ReEDSThermalGenerator",
    "ReEDSTransmissionLine",
    "ReEDSUpgrader",
    "ReEDSVariableGenerator",
    "RegionAlignment",
    "RegionAlignmentError",
    "RegionAlignmentPolicy",
    "RegionMatch",
    "RegionResolution",
    "ReserveDirection",
    "ReserveType",
    "__version__",
    "align_regions",
    "load_county_membership",
    "normalize_county_fips",
    "register_modeled_years_reader",
]
