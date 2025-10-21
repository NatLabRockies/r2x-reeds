"""Plugin to add CCS incentive to the model.

This plugin is only applicable for ReEDS, but could work with similarly arranged data
"""

import polars as pl
from infrasys import System
from loguru import logger

from r2x_reeds.config import ReEDSConfig
from r2x_reeds.models.components import ReEDSGenerator
from r2x_reeds.parser import ReEDSParser


# @PluginManager.register_system_update("ccs_credit")
def update_system(config: ReEDSConfig, system: System, parser: ReEDSParser | None, **kwargs) -> System:
    """Apply CCS incentive to CCS eligible technologies.

    The incentive is calculated with the capture incentive ($/ton) and capture rate
    (ton/MWh), to produce a subtractor ($/MWh) implemented with PLEXOS' "Use of
    Service Charge".

    Parameters
    ----------
    config : ReEDSConfig
        The ReEDS configuration.
    system : System
        The system object to be updated.
    parser : ReEDSParser | None
        The parser object used for parsing.
    **kwargs
        Additional keyword arguments.

    Returns
    -------
    System
        The updated system object.

    Notes
    -----
    The names of some of the columns for the parser data are specified in the `file_mapping.json`.
    """
    if parser is None:
        msg = "Missing parser information for ccs_credit. Skipping plugin."
        logger.debug(msg)
        return system

    required_files = ["co2_incentive", "emission_capture_rate", "upgrade_link"]
    parser_data = getattr(parser, "data", {})
    if not all(key in parser_data for key in required_files):
        logger.warning("Missing required files for ccs_credit. Skipping plugin.")
        return system

    production_rate = parser_data["emission_capture_rate"]

    # Some technologies on ReEDS are eligible for incentive but have not been upgraded yet. Since the
    # co2_incentive does not capture all the possible technologies, we get the technologies before upgrading
    # and if they exist in the system we apply the incentive.
    incentive = parser_data["co2_incentive"].join(
        parser_data["upgrade_link"], left_on="tech", right_on="to", how="left"
    )
    ccs_techs = incentive["tech"].unique()
    ccs_techs = ccs_techs.unique().extend(incentive["from"].unique())

    for generator in system.get_components(
        ReEDSGenerator, filter_func=lambda gen: gen.technology in ccs_techs
    ):
        reeds_tech = generator.technology
        reeds_vintage = generator.vintage
        reeds_region = generator.region.name

        reeds_tech_mask = (
            (pl.col("tech") == reeds_tech)
            & (pl.col("region") == reeds_region)
            & (pl.col("vintage") == reeds_vintage)
        )
        generator_production_rate = production_rate.filter(reeds_tech_mask)

        if generator_production_rate.is_empty():
            msg = f"Generator {generator.name=} does not appear on the production rate file. Skipping it."
            logger.debug(msg)
            continue

        upgrade_mask = (
            (pl.col("from") == reeds_tech)
            & (pl.col("region") == reeds_region)
            & (pl.col("vintage") == reeds_vintage)
        )

        try:
            generator_incentive = incentive.filter(reeds_tech_mask.or_(upgrade_mask))["incentive"].item()
            capture_rate = generator_production_rate["capture_rate"].item()
            uos_charge = -generator_incentive * capture_rate

            generator.ext["UoS Charge"] = uos_charge
            logger.debug(
                f"Applied CCS credit to {generator.name}: "
                f"incentive={generator_incentive} $/ton, capture_rate={capture_rate} ton/MWh, "
                f"UoS_charge={uos_charge} $/MWh"
            )

        except Exception as e:
            logger.warning(f"Failed to apply CCS credit to {generator.name}: {e}")
            continue

    return system
