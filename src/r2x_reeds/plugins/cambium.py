"""Plugin for Cambium specific configuration.

This plugin is only applicable for ReEDS, but could work with similarly arranged data
"""

import polars as pl
from infrasys import System
from loguru import logger

from r2x_reeds.config import ReEDSConfig
from r2x_reeds.models.components import ReEDSGenerator, ReEDSRegion, ReEDSTransmissionLine
from r2x_reeds.parser import ReEDSParser


# @PluginManager.register_system_update("cambium")
def update_system(
    config: ReEDSConfig, system: System, parser: ReEDSParser, perturb: float, **kwargs
) -> System:
    """Apply hurdle rate between regions.

    This function updates the default hurdle rate for the ReEDS parser using a new file

    Parameters
    ----------
    config : ReEDSConfig
        The ReEDS configuration.
    system : System
        The system object to be updated.
    parser : ReEDSParser
        The parser object used for parsing.
    perturb : float
        Load perturbation scalar.
    **kwargs
        Additional keyword arguments.
    """
    logger.info("Applying cambium configuration")

    system = _derate_plants(system)

    for generator in system.get_components(
        ReEDSGenerator,
        filter_func=lambda x: any(tech in x.technology for tech in ["nuclear", "lfill", "biopower"]),
    ):
        generator.ext["Fixed Load"] = generator.capacity

    for region in system.get_components(ReEDSRegion):
        region.ext["Load Scalar"] = perturb

    if parser is not None:
        hurdle_rate_data = getattr(parser, "hurdle_rate_data", None)

        if hurdle_rate_data is not None:
            for line in system.get_components(ReEDSTransmissionLine):
                to_region = line.to_region.name
                from_region = line.from_region.name

                try:
                    hurdle_rate = (
                        hurdle_rate_data.filter(pl.col("from_region") == from_region)
                        .filter(pl.col("to_region") == to_region)["hurdle_rate"]
                        .item()
                    )
                    logger.debug(
                        f"Setting hurdle rate between {to_region=} and {from_region=} of {hurdle_rate=}"
                    )

                    if to_region != from_region:
                        if previous_hurdle := line.ext.get("Wheeling Charge"):
                            logger.debug(
                                "Changing hurdle rate for {} from {} to {}.",
                                line.name,
                                previous_hurdle,
                                hurdle_rate,
                            )
                        # NOTE: This assumes that we have the same hurdle rate in both directions.
                        line.ext["Wheeling Charge"] = hurdle_rate
                        line.ext["Wheeling Charge Back"] = hurdle_rate
                except Exception as e:
                    logger.debug(f"Could not find hurdle rate for {from_region} -> {to_region}: {e}")
        else:
            logger.debug("Hurdle rate data not found. Skipping hurdle rate configuration.")

    return system


def _derate_plants(system: System) -> System:
    """Apply derating to plants based on outage rates."""
    for generator in system.get_components(ReEDSGenerator):
        if "distpv" in generator.name:
            generator.planned_outage_rate = None

        if generator.planned_outage_rate is None or generator.forced_outage_rate is None:
            continue

        original_capacity = generator.capacity
        derated_capacity = (
            (1 - generator.planned_outage_rate) * (1 - generator.forced_outage_rate) * original_capacity
        )
        generator.capacity = derated_capacity
        generator.planned_outage_rate = None
        generator.forced_outage_rate = None

        if hasattr(generator, "mean_time_to_repair"):
            generator.mean_time_to_repair = None

    return system
