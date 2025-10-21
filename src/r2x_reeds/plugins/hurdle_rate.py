"""Plugin to add hurdle rate between regions.

This plugin is only applicable for ReEDs, but could work with similarly arrange data
"""

from infrasys import System
from loguru import logger

from r2x_reeds.config import ReEDSConfig
from r2x_reeds.models.components import ReEDSTransmissionLine
from r2x_reeds.parser import ReEDSParser


# @PluginManager.register_system_update("hurdle_rate")
def update_system(
    config: ReEDSConfig,
    system: System,
    parser: ReEDSParser | None = None,
    hurdle_rate: float | None = None,
) -> System:
    """Apply hurdle rate between regions.

    This function updates the default hurdle rate for the ReEDS parser using a new file

    Parameters
    ----------
    config : ReEDSConfig
        The ReEDS configuration.
    system : System
        The system object to be updated.
    parser : ReEDSParser | None, optional
        The parser object used for parsing.
    hurdle_rate : float | None, optional
        The hurdle rate to apply between regions.

    Returns
    -------
    System
        The updated system object.
    """
    if hurdle_rate is None:
        logger.warning("Could not set hurdle rate value. Skipping plugin.")
        return system

    logger.info("Applying hurdle rate {} to transmission lines", hurdle_rate)

    # Validate parser data if provided
    if parser is not None:
        parser_data = getattr(parser, "data", {})
        if "hierarchy" not in parser_data:
            logger.warning("Did not find hierarchy file on parser. Check parser object.")
        else:
            logger.debug("Found hierarchy data in parser")

    # Apply hurdle rate to all inter-regional transmission lines
    for line in system.get_components(ReEDSTransmissionLine):
        region_to = line.to_region.name
        region_from = line.from_region.name

        # Only apply hurdle rate to inter-regional lines
        if region_to != region_from:
            if previous_hurdle := line.ext.get("Wheeling Charge"):
                logger.debug(
                    "Changing hurdle rate for {} from {} to {}.", line.name, previous_hurdle, hurdle_rate
                )

            # Apply hurdle rate in both directions
            line.ext["Wheeling Charge"] = hurdle_rate
            line.ext["Wheeling Charge Back"] = hurdle_rate

            logger.trace(
                "Applied hurdle rate {} to line {} between {} and {}",
                hurdle_rate,
                line.name,
                region_from,
                region_to,
            )

    logger.info("Finished applying hurdle rate to transmission lines")
    return system
