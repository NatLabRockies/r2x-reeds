"""Plugin to add CCS incentive to the model.

This plugin is only applicable for ReEDS, but could work with similarly arranged data
"""

from pathlib import Path

import polars as pl
from infrasys import System
from loguru import logger
from pydantic import Field
from rust_ok import Err, Ok, Result

from r2x_core import PluginConfig, expose_plugin
from r2x_reeds.models.components import ReEDSGenerator
from r2x_reeds.sysmod.utils import read_tabular_frame


def _cast_string_columns(frame: pl.DataFrame | None, string_columns: tuple[str, ...]) -> pl.DataFrame:
    """Ensure the listed columns are UTF-8 strings for joining/filtering."""

    if frame is None or frame.is_empty():
        return frame or pl.DataFrame()

    casts = [pl.col(column).cast(pl.Utf8) for column in string_columns if column in frame.columns]
    if casts:
        frame = frame.with_columns(casts)
    return frame


def _normalize_solve_year(frame: pl.DataFrame) -> pl.DataFrame:
    """Retain ReEDS's native ``t`` year key for per-state policy matching."""
    if "t" in frame.columns and "solve_year" in frame.columns:
        raise ValueError("CCS input cannot contain both 't' and 'solve_year' columns")
    if "t" in frame.columns:
        frame = frame.rename({"t": "solve_year"})
    if "solve_year" in frame.columns:
        frame = frame.with_columns(pl.col("solve_year").cast(pl.Int64))
    return frame


def _join_upgrade_links(co2_incentive: pl.DataFrame, upgrade_link: pl.DataFrame) -> pl.DataFrame:
    """Join upgrades on every available policy dimension to avoid cross-year fan-out."""
    dimensions = ("region", "vintage", "solve_year")
    unsupported = [
        column
        for column in dimensions
        if column in upgrade_link.columns and column not in co2_incentive.columns
    ]
    if unsupported:
        msg = f"CCS upgrade link keys are missing from incentives: {unsupported}"
        raise ValueError(msg)

    shared_dimensions = [
        column for column in dimensions if column in co2_incentive.columns and column in upgrade_link.columns
    ]
    return co2_incentive.join(
        upgrade_link,
        left_on=["tech", *shared_dimensions],
        right_on=["to", *shared_dimensions],
        how="left",
    )


def _generator_key_filter(
    frame: pl.DataFrame,
    generator: ReEDSGenerator,
    *,
    technology_column: str,
) -> pl.Expr:
    """Match policy rows to one generator, including year when the source provides it."""
    selector = (
        (pl.col(technology_column) == generator.technology)
        & (pl.col("region") == generator.region.name)
        & (pl.col("vintage") == generator.vintage)
    )
    if "solve_year" in frame.columns:
        if generator.solve_year is None:
            return pl.lit(False)
        selector &= pl.col("solve_year") == generator.solve_year
    return selector


class CCSCreditConfig(PluginConfig):
    """Configuration for applying CCS incentives to eligible technologies."""

    co2_incentive_fpath: Path | str | None = Field(
        default=None,
        description="Path to CSV file containing CO2 incentive data.",
    )
    emission_capture_rate_fpath: Path | str | None = Field(
        default=None,
        description="Path to CSV file containing emission capture rate data.",
    )
    upgrade_link_fpath: Path | str | None = Field(
        default=None,
        description="Path to CSV file containing technology upgrade links.",
    )


@expose_plugin
def add_ccs_credit(system: System, config: CCSCreditConfig) -> Result[System, Exception]:
    """Apply CCS incentive to CCS eligible technologies.

    The incentive is calculated with the capture incentive ($/ton) and capture rate
    (ton/MWh), to produce a subtractor ($/MWh) implemented with PLEXOS' "Use of
    Service Charge".

    Parameters
    ----------
    system : System
        The system object to be updated (from stdin).
    config : CCSCreditConfig
        Configuration for required input file paths.

    Returns
    -------
    Result[System, Exception]
        The updated system object or the original input or processing error.

    Notes
    -----
    This plugin expects data files to be specified as file paths. All three files
    (co2_incentive, emission_capture_rate, and upgrade_link) must be provided
    for the plugin to function.
    """
    if (
        config.co2_incentive_fpath is None
        or config.emission_capture_rate_fpath is None
        or config.upgrade_link_fpath is None
    ):
        msg = "Missing required data file paths for ccs_credit "
        msg += "(co2_incentive_fpath, emission_capture_rate_fpath, upgrade_link_fpath). Skipping plugin."
        logger.debug(msg)
        return Ok(system)

    try:
        co2_incentive = read_tabular_frame(config.co2_incentive_fpath, name="co2_incentive")
        emission_capture_rate = read_tabular_frame(
            config.emission_capture_rate_fpath, name="emission_capture_rate"
        )
        upgrade_link = read_tabular_frame(config.upgrade_link_fpath, name="upgrade_link")

        co2_incentive = _cast_string_columns(
            _normalize_solve_year(co2_incentive), ("tech", "region", "vintage")
        )
        emission_capture_rate = _cast_string_columns(
            _normalize_solve_year(emission_capture_rate), ("tech", "region", "vintage")
        )
        upgrade_link = _cast_string_columns(
            _normalize_solve_year(upgrade_link), ("from", "to", "region", "vintage")
        )

        # Apply CCS incentives using loaded data
        system = _apply_ccs_credit(system, co2_incentive, emission_capture_rate, upgrade_link)
    except Exception as exc:
        logger.error("CCS credit plugin failed: {}", exc)
        return Err(exc)

    return Ok(system)


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
    incentive = _join_upgrade_links(co2_incentive, upgrade_link)

    # Get list of CCS technologies
    ccs_techs = incentive["tech"].unique().to_list()
    from_column = incentive["from"]
    if from_column is not None:
        ccs_techs.extend(from_column.drop_nulls().unique().to_list())
    ccs_techs = list(set(ccs_techs))  # Remove duplicates

    for generator in system.get_components(
        ReEDSGenerator, filter_func=lambda gen: gen.technology in ccs_techs
    ):
        generator_production_rate = production_rate.filter(
            _generator_key_filter(production_rate, generator, technology_column="tech")
        )

        if generator_production_rate.is_empty():
            msg = f"Generator {generator.name} does not appear in the production rate file. Skipping it."
            logger.debug(msg)
            continue

        # Filter for upgrade path if it exists
        direct_mask = _generator_key_filter(incentive, generator, technology_column="tech")
        upgrade_mask = _generator_key_filter(incentive, generator, technology_column="from")

        incentive_matches = incentive.filter(direct_mask | upgrade_mask)
        if incentive_matches.is_empty():
            logger.debug("No incentive found for {}", generator.name)
            continue
        if incentive_matches.height != 1:
            msg = f"Ambiguous CCS incentive rows for {generator.name}: {incentive_matches.height}"
            raise ValueError(msg)
        if generator_production_rate.height != 1:
            msg = f"Ambiguous CCS capture-rate rows for {generator.name}: {generator_production_rate.height}"
            raise ValueError(msg)

        generator_incentive = incentive_matches["incentive"].item()
        capture_rate = generator_production_rate["capture_rate"].item()
        uos_charge = -generator_incentive * capture_rate

        generator.ext["UoS Charge"] = uos_charge
        logger.debug(
            "Applied CCS credit to {}: incentive={} $/ton, capture_rate={} ton/MWh, UoS_charge={} $/MWh",
            generator.name,
            generator_incentive,
            capture_rate,
            uos_charge,
        )

    return system
