"""Plugin to add CCS incentive to the model.

This plugin is only applicable for ReEDS, but could work with similarly arranged data
"""

import polars as pl
from infrasys import System
from loguru import logger

from r2x_core import DataStore
from r2x_reeds.models.components import ReEDSGenerator


def _cast_string_columns(frame: pl.DataFrame | None, string_columns: tuple[str, ...]) -> pl.DataFrame:
    """Ensure the listed columns are UTF-8 strings for joining/filtering."""

    if frame is None or frame.is_empty():
        return frame or pl.DataFrame()

    casts = [pl.col(column).cast(pl.Utf8) for column in string_columns if column in frame.columns]
    if casts:
        frame = frame.with_columns(casts)
    return frame


def add_ccs_credit(
    system: System,
    co2_incentive_fpath: str | None = None,
    emission_capture_rate_fpath: str | None = None,
    upgrade_link_fpath: str | None = None,
    **kwargs,
) -> System:
    """Apply CCS incentive to CCS eligible technologies.

    The incentive is calculated with the capture incentive ($/ton) and capture rate
    (ton/MWh), to produce a subtractor ($/MWh) implemented with PLEXOS' "Use of
    Service Charge".

    Parameters
    ----------
    system : System
        The system object to be updated (from stdin).
    co2_incentive_fpath : str, optional
        Path to CSV file containing CO2 incentive data with columns:
        tech, region, vintage, incentive.
    emission_capture_rate_fpath : str, optional
        Path to CSV file containing emission capture rate data with columns:
        tech, region, vintage, capture_rate.
    upgrade_link_fpath : str, optional
        Path to CSV file containing technology upgrade links with columns:
        from, to, region, vintage.
    **kwargs
        Additional keyword arguments (ignored).

    Returns
    -------
    System
        The updated system object.

    Notes
    -----
    This plugin expects data files to be specified as file paths. All three files
    (co2_incentive, emission_capture_rate, and upgrade_link) must be provided
    for the plugin to function.
    """
    if co2_incentive_fpath is None or emission_capture_rate_fpath is None or upgrade_link_fpath is None:
        msg = "Missing required data file paths for ccs_credit "
        msg += "(co2_incentive_fpath, emission_capture_rate_fpath, upgrade_link_fpath). Skipping plugin."
        logger.debug(msg)
        return system

    try:
        co2_incentive = DataStore.load_file(co2_incentive_fpath, name="co2_incentive")
        emission_capture_rate = DataStore.load_file(emission_capture_rate_fpath, name="emission_capture_rate")
        upgrade_link = DataStore.load_file(upgrade_link_fpath, name="upgrade_link")

        if isinstance(co2_incentive, pl.LazyFrame):
            co2_incentive = co2_incentive.collect()
        if isinstance(emission_capture_rate, pl.LazyFrame):
            emission_capture_rate = emission_capture_rate.collect()
        if isinstance(upgrade_link, pl.LazyFrame):
            upgrade_link = upgrade_link.collect()

        co2_incentive = _cast_string_columns(co2_incentive, ("tech", "region", "vintage"))
        emission_capture_rate = _cast_string_columns(emission_capture_rate, ("tech", "region", "vintage"))
        upgrade_link = _cast_string_columns(upgrade_link, ("from", "to", "region", "vintage"))

        # Apply CCS incentives using loaded data
        system = _apply_ccs_credit(system, co2_incentive, emission_capture_rate, upgrade_link)
    except Exception as e:
        logger.error(f"CCS credit plugin failed: {e}")
        return system

    return system


def _apply_ccs_credit(
    system: System,
    co2_incentive: pl.DataFrame,
    emission_capture_rate: pl.DataFrame,
    upgrade_link: pl.DataFrame,
) -> System:
    """Apply CCS credit to eligible generators.

    Parameters
    ----------
    system : System
        The system to modify.
    co2_incentive : pl.DataFrame
        CO2 incentive data with columns: tech, region, vintage, incentive.
    emission_capture_rate : pl.DataFrame
        Emission capture rate data with columns: tech, region, vintage, capture_rate.
    upgrade_link : pl.DataFrame
        Technology upgrade links with columns: from, to, region, vintage.

    Returns
    -------
    System
        The modified system.
    """
    production_rate = emission_capture_rate

    # Some technologies on ReEDS are eligible for incentive but have not been upgraded yet.
    # Since the co2_incentive does not capture all the possible technologies, we get the
    # technologies before upgrading and if they exist in the system we apply the incentive.
    incentive = co2_incentive.join(upgrade_link, left_on="tech", right_on="to", how="left")

    # Get list of CCS technologies
    ccs_techs = incentive["tech"].unique().to_list()
    from_column = incentive["from"]
    if from_column is not None:
        ccs_techs.extend(from_column.drop_nulls().unique().to_list())
    ccs_techs = list(set(ccs_techs))  # Remove duplicates

    for generator in system.get_components(
        ReEDSGenerator, filter_func=lambda gen: gen.technology in ccs_techs
    ):
        reeds_tech = generator.technology
        reeds_vintage = generator.vintage
        reeds_region = generator.region.name

        # Create filter for this generator's characteristics
        reeds_tech_mask = (
            (pl.col("tech") == reeds_tech)
            & (pl.col("region") == reeds_region)
            & (pl.col("vintage") == reeds_vintage)
        )

        generator_production_rate = production_rate.filter(reeds_tech_mask)

        if generator_production_rate.is_empty():
            msg = f"Generator {generator.name} does not appear in the production rate file. Skipping it."
            logger.debug(msg)
            continue

        # Filter for upgrade path if it exists
        upgrade_mask = (
            (pl.col("from") == reeds_tech)
            & (pl.col("region") == reeds_region)
            & (pl.col("vintage") == reeds_vintage)
        )

        try:
            # Get incentive value - try direct match first, then upgrade path
            incentive_matches = incentive.filter(reeds_tech_mask.or_(upgrade_mask))

            if incentive_matches.is_empty():
                logger.debug(f"No incentive found for {generator.name}")
                continue

            generator_incentive = incentive_matches["incentive"].item()
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
