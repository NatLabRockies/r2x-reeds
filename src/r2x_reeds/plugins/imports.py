"""Plugin to create time series for Imports.

This plugin create the time series representation for imports. Currently, it only process the canadian imports
on ReEDS.

This plugin is only applicable for ReEDs, but could work with similarly arrange data
"""

from datetime import datetime, timedelta

import polars as pl
from infrasys import System
from infrasys.time_series_models import SingleTimeSeries
from loguru import logger

from r2x_reeds.config import ReEDSConfig
from r2x_reeds.models.components import ReEDSGenerator
from r2x_reeds.parser import ReEDSParser


# @PluginManager.register_system_update("imports")
def update_system(config: ReEDSConfig, system: System, parser: ReEDSParser | None = None) -> System:
    """Add Canadian imports time series to the system.

    This function adds time series data for Canadian imports generators,
    creating daily hydro budget time series based on seasonal fractions.

    Parameters
    ----------
    config : ReEDSConfig
        The ReEDS configuration.
    system : System
        The system object to be updated.
    parser : ReEDSParser | None
        The parser object used for parsing.

    Returns
    -------
    System
        The updated system object.
    """
    if not hasattr(config, "weather_year") or config.weather_year is None:
        logger.warning("Weather year not specified in config. Skipping imports plugin.")
        return system

    weather_year = config.weather_year

    if parser is None:
        msg = "Missing parser information for imports. Skipping plugin."
        logger.debug(msg)
        return system

    # Check if required data files are available
    parser_data = getattr(parser, "data", {})
    required_files = ["canada_imports", "canada_szn_frac", "hour_map"]

    if not all(key in parser_data for key in required_files):
        missing_files = [key for key in required_files if key not in parser_data]
        logger.warning("Missing required files for import plugin: {}", missing_files)
        return system

    logger.info("Adding imports time series...")

    hour_map = parser_data["hour_map"]
    szn_frac = parser_data["canada_szn_frac"]
    total_imports = parser_data["canada_imports"]

    # Create hourly time series by joining hour map with seasonal fractions
    hourly_time_series = hour_map.join(szn_frac, on="season", how="left")

    if hourly_time_series.is_empty():
        logger.warning("Empty time series after joining hour_map and canada_szn_frac")
        return system

    hourly_time_series = hourly_time_series.with_columns(
        pl.col("time_index").str.to_datetime(),
    )

    # Group by date to get daily values
    daily_time_series = hourly_time_series.group_by(pl.col("time_index").dt.date()).median()

    # NOTE: Since the seasons can be repeated, the szn frac can be greater than one. To avoid this, we
    # normalize it again to redistribute the fraction throughout the 365 or 366 days.
    daily_time_series_normalized = daily_time_series.with_columns(pl.col("value") / pl.col("value").sum())

    # NOTE: This will need change if we modify the model for the imports. Currently all is assumed to be
    # modeled as HydroEnergyReservoir. Currently we only apply it to can-imports.
    initial_time = datetime(year=weather_year, month=1, day=1)

    # Find Canadian import generators - updated to use ReEDSGenerator
    for generator in system.get_components(
        ReEDSGenerator,
        filter_func=lambda x: "can-imports" in x.name.lower() or "canada" in x.technology.lower(),
    ):
        # Get region name from the generator's region instead of bus
        region_name = generator.region.name

        # Filter total imports for this region
        region_imports = total_imports.filter(pl.col("r") == region_name)

        if region_imports.is_empty():
            logger.warning("No import data found for region {}", region_name)
            continue

        total_import_value = region_imports["value"].item()
        daily_budget = total_import_value * daily_time_series_normalized["value"].to_numpy()
        daily_budget_gwh = daily_budget[:-1] / 1e3  # Convert MWh to GWh

        ts = SingleTimeSeries.from_array(
            data=daily_budget_gwh,  # Data in GWh
            variable_name="hydro_budget",
            initial_time=initial_time,
            resolution=timedelta(days=1),
        )

        system.add_time_series(ts, generator)
        logger.debug("Added imports time series to generator: {}", generator.name)

    logger.info("Finished adding imports time series")
    return system
