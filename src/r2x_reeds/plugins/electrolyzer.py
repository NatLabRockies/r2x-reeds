"""Electrolyzer representation on PC.

This extension incorporates the load related to the usage of electrolyzer for
each of the ReEDS regions.
"""

# System packages
from datetime import datetime, timedelta

# Third-party packages
import numpy as np
import polars as pl
from infrasys import System
from infrasys.time_series_models import SingleTimeSeries
from loguru import logger

# Local imports
from r2x_reeds.config import ReEDSConfig
from r2x_reeds.models.components import ReEDSDemand, ReEDSGenerator, ReEDSRegion
from r2x_reeds.parser import ReEDSParser

ELECTROLYZER_LOAD_FMAP = "electrolyzer_load"
MONTHLY_H2_FPRICE_FMAP = "h2_fuel_price"


# @PluginManager.register_system_update("electrolyzer")
def update_system(
    config: ReEDSConfig,
    system: System,
    parser: ReEDSParser,
    **kwargs
) -> System:
    """Modify infrasys system to include electrolyzer load and monthly hydrogen fuel price.

    Parameters
    ----------
    config : ReEDSConfig
        The ReEDS configuration.
    system : System
        The system object to be updated.
    parser : ReEDSParser
        The parser object used for parsing.
    **kwargs
        Additional keyword arguments.

    Returns
    -------
    System
        The updated system object.
    """
    logger.info("Adding electrolyzer representation to the system")

    system = electrolyzer_load(config=config, parser=parser, system=system)
    system = hydrogen_fuel_price(config=config, parser=parser, system=system)

    return system


def electrolyzer_load(config: ReEDSConfig, parser: ReEDSParser, system: System) -> System:
    """Add electrolyzer load to each region as a fixed load."""
    if not hasattr(config, 'weather_year') or config.weather_year is None:
        logger.warning("Weather year not specified in config. Skipping electrolyzer load.")
        return system

    # Check if parser has the required data
    parser_data = getattr(parser, 'data', {})
    if ELECTROLYZER_LOAD_FMAP not in parser_data:
        logger.warning("No electrolyzer data found on parser. Check parsing filenames.")
        return system

    load_data = parser_data[ELECTROLYZER_LOAD_FMAP]

    if load_data is None:
        logger.warning("No electrolyzer data found on parser. Check parsing filenames.")
        return system

    # Pivot load data to have sum of load for all techs on each column
    load_data_pivot = load_data.pivot(
        index="hour", columns="region", values="load_MW", aggregate_function="sum"
    ).lazy()

    # Create 8760 using hour_map
    hour_map = parser_data.get("hour_map")
    if hour_map is None:
        logger.warning("No hour_map found in parser data. Cannot create hourly electrolyzer load.")
        return system

    # Join with hour map to get full 8760 hours
    total_load_per_region = hour_map.join(load_data_pivot, on="hour", how="left").fill_null(0)

    for region_name in load_data["region"].unique():
        # Get the ReEDS region component
        try:
            region = system.get_component(ReEDSRegion, name=region_name)
        except Exception:
            logger.warning(f"Region {region_name} not found in system. Skipping electrolyzer load.")
            continue

        # Calculate total electrolyzer load for the region
        region_load_data = total_load_per_region[region_name].to_numpy()
        max_load = float(np.max(region_load_data))

        # Assert that max load is greater than 1 MW
        if max_load < 1:
            logger.warning("Electrolyzer load for region {} is smaller than 1 MW. Skipping it.", region_name)
            continue

        # Create electrolyzer demand component
        electrolyzer_demand = ReEDSDemand(
            name=f"{region_name}_electrolyzer",
            region=region,
            peak_demand=max_load,  # MW
            category="electrolyzer"
        )

        # Store electrolyzer metadata
        electrolyzer_demand.ext = {
            "load_type": "electrolyzer",
            "interruptible": True,
            "original_region": region_name
        }

        system.add_component(electrolyzer_demand)

        # Create time series for hourly load
        ts = SingleTimeSeries.from_array(
            data=region_load_data,  # Data in MW
            variable_name="fixed_load",
            initial_time=datetime(year=config.weather_year, month=1, day=1),
            resolution=timedelta(hours=1),
        )

        # Add time series to the component
        system.add_time_series(ts, electrolyzer_demand)
        logger.debug("Adding electrolyzer load to region: {}", region_name)

    return system


def hydrogen_fuel_price(config: ReEDSConfig, parser: ReEDSParser, system: System) -> System:
    """Add monthly hydrogen fuel price for generator using hydrogen."""
    parser_data = getattr(parser, 'data', {})
    if MONTHLY_H2_FPRICE_FMAP not in parser_data:
        logger.warning("No monthly electrolyzer data found on parser. Check parsing filenames.")
        return system

    if not hasattr(config, 'weather_year') or config.weather_year is None:
        logger.warning("Weather year not specified in config. Skipping hydrogen fuel price.")
        return system

    logger.debug("Adding monthly fuel prices for h2 technologies.")
    h2_fprice = parser_data[MONTHLY_H2_FPRICE_FMAP]

    # Create datetime array for the weather year
    date_time_array = np.arange(
        f"{config.weather_year}",
        f"{config.weather_year + 1}",
        dtype="datetime64[h]",
    )[:-24]  # Removing 1 day to match ReEDS convention

    months = np.array([dt.astype("datetime64[M]").astype(int) % 12 + 1 for dt in date_time_array])

    # Adding fuel price for all hydrogen generators
    for h2_generator in system.get_components(
        ReEDSGenerator,
        filter_func=lambda x: "h2" in x.name.lower() or "hydrogen" in x.technology.lower()
    ):
        region_name = h2_generator.region.name

        if region_name not in h2_fprice["region"]:
            logger.debug(f"No hydrogen fuel price data for region {region_name}")
            continue

        region_h2_fprice = h2_fprice.filter(pl.col("region") == region_name)

        month_datetime_series = np.zeros(len(date_time_array), dtype=float)

        for row in region_h2_fprice.iter_rows(named=True):
            month = int(row["month"].strip("m"))
            month_filter = np.where(months == month)
            month_datetime_series[month_filter] = row["h2_price"]

        # Units from monthly hydrogen fuel price are in $/kg
        # Convert $/kg to $/MWh using conversion factor
        # Typical conversion: ~33.3 kWh/kg H2, so 1 kg = 0.0333 MWh
        # Therefore $/kg * (1 kg / 0.0333 MWh) = $/MWh * 30
        month_datetime_series = month_datetime_series * 30.0  # Convert $/kg to $/MWh

        ts = SingleTimeSeries.from_array(
            data=month_datetime_series,  # Data in $/MWh
            variable_name="fuel_price",
            initial_time=datetime(year=config.weather_year, month=1, day=1),
            resolution=timedelta(hours=1),
        )

        system.add_time_series(ts, h2_generator)
        logger.debug(f"Added hydrogen fuel price time series to generator: {h2_generator.name}")

    return system
