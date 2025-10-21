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

    # Apply hurdle rate to all transmission lines
    for line in system.get_components(ReEDSTransmissionLine):
        # Get regions through the interface
        region_from = line.interface.from_region.name
        region_to = line.interface.to_region.name

        # Check if there was a previous hurdle rate
        if line.hurdle_rate is not None:
            logger.debug(
                "Changing hurdle rate for {} from {} to {}.", line.name, line.hurdle_rate, hurdle_rate
            )

        # Apply the new hurdle rate
        line.hurdle_rate = hurdle_rate

        logger.trace(
            "Applied hurdle rate {} to line {} between {} and {}",
            hurdle_rate,
            line.name,
            region_from,
            region_to,
        )

    logger.info("Finished applying hurdle rate to transmission lines")
    return system
