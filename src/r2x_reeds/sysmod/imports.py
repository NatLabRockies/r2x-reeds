"""Plugin to create time series for Imports.

This plugin creates the time series representation for imports. Currently, it only processes
Canadian imports on ReEDS.

This plugin is only applicable for ReEDS, but could work with similarly arranged data.
"""

from datetime import datetime, timedelta

import polars as pl
from infrasys import System
from infrasys.time_series_models import SingleTimeSeries
from loguru import logger

from r2x_core import DataStore
from r2x_reeds.models.components import ReEDSGenerator


def add_imports(
    system: System,
    weather_year: int | None = None,
    canada_imports_fpath: str | None = None,
    canada_szn_frac_fpath: str | None = None,
    hour_map_fpath: str | None = None,
    **kwargs,
) -> System:
    """Add Canadian imports time series to the system.

    This function adds time series data for Canadian imports generators,
    creating daily hydro budget time series based on seasonal fractions.

    Parameters
    ----------
    system : System
        The system object to be updated (from stdin).
    weather_year : int, optional
        The weather year for the time series.
    canada_imports_fpath : str, optional
        Path to CSV file containing total Canadian import values with columns:
        r (region), value.
    canada_szn_frac_fpath : str, optional
        Path to CSV file containing seasonal fraction data with columns:
        season, value.
    hour_map_fpath : str, optional
        Path to CSV file containing hour mapping with columns:
        hour, time_index, season.
    **kwargs
        Additional keyword arguments (ignored).

    Returns
    -------
    System
        The updated system object.
    """
    if weather_year is None:
        logger.warning("Weather year not specified. Skipping imports plugin.")
        return system

    if canada_imports_fpath is None or canada_szn_frac_fpath is None or hour_map_fpath is None:
        msg = "Missing required file paths for imports plugin (canada_imports_fpath, "
        msg += "canada_szn_frac_fpath, hour_map_fpath)."
        logger.debug(msg)
        return system

    logger.info("Adding imports time series...")

    try:
        # Load required data files using DataStore helper
        hour_map = DataStore.load_file(hour_map_fpath, name="hour_map")
        szn_frac = DataStore.load_file(canada_szn_frac_fpath, name="canada_szn_frac")
        total_imports = DataStore.load_file(canada_imports_fpath, name="canada_imports")

        if hour_map is not None:
            hour_map = hour_map.collect()
        if szn_frac is not None:
            szn_frac = szn_frac.collect()
        if total_imports is not None:
            total_imports = total_imports.collect()

        # Create hourly time series by joining hour map with seasonal fractions
        hourly_time_series = hour_map.join(szn_frac, on="season", how="left")

        if hourly_time_series.is_empty():
            logger.warning("Empty time series after joining hour_map and seasonal fractions")
            return system

        # Convert time_index to datetime
        hourly_time_series = hourly_time_series.with_columns(
            pl.col("time_index").str.to_datetime(),
        )

        # Group by date to get daily values
        daily_time_series = hourly_time_series.group_by(pl.col("time_index").dt.date()).median()

        # NOTE: Since the seasons can be repeated, the szn frac can be greater than one. To avoid this, we
        # normalize it again to redistribute the fraction throughout the 365 or 366 days.
        if "value" in daily_time_series.columns:
            daily_time_series = daily_time_series.with_columns(pl.col("value") / pl.col("value").sum())

        initial_time = datetime(year=weather_year, month=1, day=1)

        # Find Canadian import generators
        for generator in system.get_components(
            ReEDSGenerator,
            filter_func=lambda x: "can-imports" in x.name.lower() or "canada" in x.technology.lower(),
        ):
            # Get region name from the generator's region
            region_name = generator.region.name

            # Filter total imports for this region
            region_imports = total_imports.filter(pl.col("r") == region_name)

            if region_imports.is_empty():
                logger.warning("No import data found for region {}", region_name)
                continue

            total_import_value = region_imports["value"].item()
            daily_budget = total_import_value * daily_time_series["value"].to_numpy()
            daily_budget_gwh = daily_budget[:-1] / 1e3  # Convert MWh to GWh

            ts = SingleTimeSeries.from_array(
                data=daily_budget_gwh,  # Data in GWh
                name="hydro_budget",
                initial_timestamp=initial_time,
                resolution=timedelta(days=1),
            )

            system.add_time_series(ts, generator)
            logger.debug("Added imports time series to generator: {}", generator.name)

        logger.info("Finished adding imports time series")
    except Exception as e:
        logger.error(f"Error in imports plugin: {e}")

    return system
