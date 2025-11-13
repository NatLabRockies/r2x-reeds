"""Electrolyzer representation on PC.

This extension incorporates the load related to the usage of electrolyzer for
each of the ReEDS regions.
"""

from datetime import datetime, timedelta

import numpy as np
import polars as pl
from infrasys import System
from infrasys.time_series_models import SingleTimeSeries
from loguru import logger

from r2x_core import DataStore
from r2x_reeds.models.components import ReEDSDemand, ReEDSGenerator, ReEDSRegion


def add_electrolizer_load(
    system: System,
    weather_year: int | None = None,
    electrolyzer_load_fpath: str | None = None,
    h2_fuel_price_fpath: str | None = None,
    hour_map_fpath: str | None = None,
    **kwargs,
) -> System:
    """Modify infrasys system to include electrolyzer load and monthly hydrogen fuel price.

    Parameters
    ----------
    system : System
        The system object to be updated (from stdin).
    weather_year : int, optional
        The weather year for time series data.
    electrolyzer_load_fpath : str, optional
        Path to CSV file containing electrolyzer load data with columns:
        region, hour, load_MW.
    h2_fuel_price_fpath : str, optional
        Path to CSV file containing monthly hydrogen fuel prices with columns:
        region, month, h2_price.
    hour_map_fpath : str, optional
        Path to CSV file containing hour mapping data with columns:
        hour, time_index, season.
    **kwargs
        Additional keyword arguments (ignored).

    Returns
    -------
    System
        The updated system object.
    """
    logger.info("Adding electrolyzer representation to the system")

    if weather_year is None:
        logger.warning("Weather year not specified. Skipping electrolyzer plugin.")
        return system

    try:
        # Load required data files
        hour_map = DataStore.load_file(hour_map_fpath, name="hour_map") if hour_map_fpath else None
        electrolyzer_load = (
            DataStore.load_file(electrolyzer_load_fpath, name="electrolyzer_load")
            if electrolyzer_load_fpath
            else None
        )
        h2_prices = (
            DataStore.load_file(h2_fuel_price_fpath, name="h2_fuel_price") if h2_fuel_price_fpath else None
        )
        if hour_map is not None:
            hour_map = hour_map.collect()
        if electrolyzer_load is not None:
            electrolyzer_load = electrolyzer_load.collect()
        if h2_prices is not None:
            h2_prices = h2_prices.collect()

        if hour_map is None:
            logger.warning("hour_map data not available. Cannot add electrolyzer load.")
            return system

        # Add electrolyzer load
        if electrolyzer_load is not None:
            system = _add_electrolyzer_load(system, electrolyzer_load, hour_map, weather_year)

        # Add hydrogen fuel prices
        if h2_prices is not None:
            system = _add_hydrogen_fuel_price(system, h2_prices, weather_year)

    except Exception as e:
        logger.error(f"Error in electrolyzer plugin: {e}")

    return system


def _add_electrolyzer_load(
    system: System, electrolyzer_load: pl.DataFrame, hour_map: pl.DataFrame, weather_year: int
) -> System:
    """Add electrolyzer load to each region as a fixed load.

    Parameters
    ----------
    system : System
        The system to modify.
    electrolyzer_load : pl.DataFrame
        Electrolyzer load data with columns: region, hour, load_MW.
    hour_map : pl.DataFrame
        Hour mapping data with columns: hour, time_index, season.
    weather_year : int
        The weather year for the time series.

    Returns
    -------
    System
        The modified system.
    """
    if electrolyzer_load is None or electrolyzer_load.is_empty():
        logger.warning("Electrolyzer load data is empty. Skipping electrolyzer load.")
        return system

    # Pivot load data to have sum of load for all techs on each column
    load_data_pivot = electrolyzer_load.pivot(
        index="hour", on="region", values="load_MW", aggregate_function="sum"
    )

    # Join with hour map to get full 8760 hours
    total_load_per_region = hour_map.join(load_data_pivot, on="hour", how="left").fill_null(0)

    for region_name in electrolyzer_load.select("region").unique().to_series():
        # Get the ReEDS region component
        try:
            region = system.get_component(ReEDSRegion, name=region_name)
        except Exception:
            logger.warning(f"Region {region_name} not found in system. Skipping electrolyzer load.")
            continue

        # Calculate total electrolyzer load for the region
        if region_name not in total_load_per_region.columns:
            logger.debug(f"No electrolyzer load data for region {region_name}")
            continue

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
            max_active_power=max_load,
            category="electrolyzer",
        )

        # Store electrolyzer metadata
        electrolyzer_demand.ext = {
            "load_type": "electrolyzer",
            "interruptible": True,
            "original_region": region_name,
        }

        system.add_component(electrolyzer_demand)

        # Create time series for hourly load
        ts = SingleTimeSeries.from_array(
            data=region_load_data,  # Data in MW
            name="fixed_load",
            initial_timestamp=datetime(year=weather_year, month=1, day=1),
            resolution=timedelta(hours=1),
        )

        # Add time series to the component
        system.add_time_series(ts, electrolyzer_demand)
        logger.debug("Adding electrolyzer load to region: {}", region_name)

    return system


def _add_hydrogen_fuel_price(system: System, h2_prices: pl.DataFrame, weather_year: int) -> System:
    """Add monthly hydrogen fuel price for generators using hydrogen.

    Parameters
    ----------
    system : System
        The system to modify.
    h2_prices : pl.DataFrame
        Hydrogen fuel price data with columns: region, month, h2_price.
    weather_year : int
        The weather year for the time series.

    Returns
    -------
    System
        The modified system.
    """
    if isinstance(h2_prices, pl.LazyFrame):
        h2_prices = h2_prices.collect()

    if h2_prices is None or h2_prices.is_empty():
        logger.warning("Hydrogen fuel price data is empty. Skipping hydrogen fuel price.")
        return system

    logger.debug("Adding monthly fuel prices for h2 technologies.")

    # Create datetime array for the weather year
    date_time_array = np.arange(
        f"{weather_year}",
        f"{weather_year + 1}",
        dtype="datetime64[h]",
    )[:-24]  # Removing 1 day to match ReEDS convention

    months = np.array([dt.astype("datetime64[M]").astype(int) % 12 + 1 for dt in date_time_array])

    # Adding fuel price for all hydrogen generators
    for h2_generator in system.get_components(
        ReEDSGenerator, filter_func=lambda x: "h2" in x.name.lower() or "hydrogen" in x.technology.lower()
    ):
        region_name = h2_generator.region.name

        if region_name not in h2_prices.select("region").unique().to_series().to_list():
            logger.debug(f"No hydrogen fuel price data for region {region_name}")
            continue

        region_h2_fprice = h2_prices.filter(pl.col("region") == region_name)

        month_datetime_series = np.zeros(len(date_time_array), dtype=float)

        for row in region_h2_fprice.iter_rows(named=True):
            # Handle month as either string or int
            month_val = row["month"]
            if isinstance(month_val, str):
                month = int(month_val.strip("m")) if "m" in month_val else int(month_val)
            else:
                month = int(month_val)

            month_filter = np.where(months == month)
            month_datetime_series[month_filter] = row["h2_price"]

        # Units from monthly hydrogen fuel price are in $/kg
        # Convert $/kg to $/MWh using conversion factor
        # Typical conversion: ~33.3 kWh/kg H2, so 1 kg = 0.0333 MWh
        # Therefore $/kg * (1 kg / 0.0333 MWh) = $/MWh * 30
        month_datetime_series = month_datetime_series * 30.0  # Convert $/kg to $/MWh

        ts = SingleTimeSeries.from_array(
            data=month_datetime_series,  # Data in $/MWh
            name="fuel_price",
            initial_timestamp=datetime(year=weather_year, month=1, day=1),
            resolution=timedelta(hours=1),
        )

        system.add_time_series(ts, h2_generator)
        logger.debug(f"Added hydrogen fuel price time series to generator: {h2_generator.name}")

    return system
