"""Plugin to create time series for Imports.

This plugin creates the time series representation for imports. Currently, it only processes
Canadian imports on ReEDS.

This plugin is only applicable for ReEDS, but could work with similarly arranged data.
"""

from datetime import datetime, timedelta
from pathlib import Path

import polars as pl
from infrasys import System
from infrasys.time_series_models import SingleTimeSeries
from loguru import logger
from pydantic import Field
from rust_ok import Err, Ok, Result

from r2x_core import DataStore, PluginConfig, expose_plugin
from r2x_reeds.models.components import ReEDSGenerator


class ImportsConfig(PluginConfig):
    """Configuration for adding Canadian imports time series."""

    weather_year: int | None = Field(
        default=None,
        description="Weather year for time series alignment.",
    )
    solve_year: int | None = Field(
        default=None,
        description="ReEDS solve year used to select wide import values.",
    )
    canada_imports_fpath: Path | str | None = Field(
        default=None,
        description="Path to CSV file containing total Canadian import values.",
    )
    canada_szn_frac_fpath: Path | str | None = Field(
        default=None,
        description="Path to CSV file containing seasonal fraction data.",
    )
    hour_map_fpath: Path | str | None = Field(
        default=None,
        description="Path to CSV file containing hour mapping data.",
    )


def _prepare_daily_import_fractions(
    hour_map: pl.DataFrame,
    szn_frac: pl.DataFrame,
    weather_year: int,
) -> pl.Series:
    """Expand ReEDS representative-season fractions to chronological daily fractions."""
    required_hour_map_columns = {"time_index", "season"}
    missing_hour_map_columns = required_hour_map_columns - set(hour_map.columns)
    if missing_hour_map_columns:
        raise ValueError(f"Hour map is missing required columns: {sorted(missing_hour_map_columns)}")

    required_fraction_columns = {"season", "value"}
    missing_fraction_columns = required_fraction_columns - set(szn_frac.columns)
    if missing_fraction_columns:
        raise ValueError(
            f"Seasonal fractions are missing required columns: {sorted(missing_fraction_columns)}"
        )

    if hour_map.schema["time_index"] == pl.String:
        hour_map = hour_map.with_columns(
            pl.col("time_index")
            .str.replace("T", " ")
            .str.replace(r"[+-]\d{2}:\d{2}$", "")
            .str.to_datetime(format="%Y-%m-%d %H:%M:%S"),
        )

    szn_frac = szn_frac.group_by("season").agg(pl.col("value").sum())
    mapped_hours = hour_map.join(szn_frac, on="season", how="inner")
    if mapped_hours.is_empty():
        raise ValueError("Hour map does not contain seasons from the seasonal fractions")

    if "year" in mapped_hours.columns:
        mapped_years = mapped_hours["year"].drop_nulls().unique().sort().to_list()
        if weather_year in mapped_years:
            mapped_hours = mapped_hours.filter(pl.col("year") == weather_year)
        elif len(mapped_years) == 1:
            mapped_hours = mapped_hours.filter(pl.col("year") == mapped_years[0])
        else:
            raise ValueError(f"Could not identify a unique representative weather year: {mapped_years}")

    mapped_days = mapped_hours.select(
        pl.col("time_index").dt.date().alias("date"),
        "season",
        "value",
    ).unique()
    conflicting_days = mapped_days.group_by("date").agg(pl.col("season").n_unique().alias("count"))
    if conflicting_days.filter(pl.col("count") != 1).height:
        raise ValueError("Hour map assigns more than one representative season to a day")

    mapped_seasons = set(mapped_days["season"].to_list())
    missing_seasons = set(szn_frac["season"].to_list()) - mapped_seasons
    if missing_seasons:
        raise ValueError(f"Hour map does not include seasonal fractions for: {sorted(missing_seasons)}")

    daily_fractions = (
        mapped_days.with_columns(pl.len().over("season").alias("days_in_season"))
        .with_columns((pl.col("value") / pl.col("days_in_season")).alias("daily_fraction"))
        .sort("date")
    )
    total_fraction = daily_fractions["daily_fraction"].sum()
    if total_fraction is None or not total_fraction > 0:
        raise ValueError("Seasonal import fractions must have a positive sum")

    daily_fractions = daily_fractions.with_columns(
        (pl.col("daily_fraction") / total_fraction).alias("daily_fraction")
    )
    invalid_fractions = daily_fractions.filter(
        pl.col("daily_fraction").is_null() | ~pl.col("daily_fraction").is_finite()
    )
    if invalid_fractions.height:
        raise ValueError("Daily import fractions contain null or non-finite values")

    return daily_fractions["daily_fraction"]


@expose_plugin
def add_imports(system: System, config: ImportsConfig) -> Result[System, str]:
    """Add Canadian imports time series to the system.

    This function adds time series data for Canadian imports generators,
    creating daily hydro budget time series based on seasonal fractions.

    Parameters
    ----------
    system : System
        The system object to be updated (from stdin).
    config : ImportsConfig
        Configuration for required input file paths and weather year.

    Returns
    -------
    Result[System, str]
        The updated system object or an error message.
    """
    if config.weather_year is None:
        logger.warning("Weather year not specified. Skipping imports plugin.")
        return Ok(system)

    if (
        config.canada_imports_fpath is None
        or config.canada_szn_frac_fpath is None
        or config.hour_map_fpath is None
    ):
        msg = "Missing required file paths for imports plugin (canada_imports_fpath, "
        msg += "canada_szn_frac_fpath, hour_map_fpath)."
        logger.debug(msg)
        return Ok(system)

    logger.info("Adding imports time series...")

    try:
        # Load required data files using DataStore helper
        hour_map = DataStore.load_file(config.hour_map_fpath, name="hour_map")
        szn_frac = DataStore.load_file(config.canada_szn_frac_fpath, name="canada_szn_frac")
        total_imports = DataStore.load_file(config.canada_imports_fpath, name="canada_imports")

        if hour_map is None or szn_frac is None or total_imports is None:
            logger.warning("Imports input data could not be loaded. Skipping imports plugin.")
            return Ok(system)

        if hour_map is not None:
            hour_map = hour_map.collect()
        if szn_frac is not None:
            szn_frac = szn_frac.collect()
        if total_imports is not None:
            total_imports = total_imports.collect()

        if "*szn" in szn_frac.columns:
            szn_frac = szn_frac.rename({"*szn": "season"})
        if "frac_weighted" in szn_frac.columns:
            szn_frac = szn_frac.rename({"frac_weighted": "value"})

        if "*timestamp" in hour_map.columns:
            hour_map = hour_map.rename({"*timestamp": "time_index"})
        if "actual_period" in hour_map.columns and "season" not in hour_map.columns:
            hour_map = hour_map.rename({"actual_period": "season"})

        if "r" not in total_imports.columns:
            raise ValueError("Import data is missing required region column 'r'")
        if "value" in total_imports.columns:
            if "t" in total_imports.columns:
                if config.solve_year is None:
                    raise ValueError("Solve year is required for long-form Canadian import data")
                total_imports = total_imports.filter(pl.col("t") == config.solve_year)
            total_imports = total_imports.select("r", pl.col("value").cast(pl.Float64))
        else:
            if config.solve_year is None:
                raise ValueError("Solve year is required for wide Canadian import data")
            if str(config.solve_year) not in total_imports.columns:
                raise ValueError(f"Import data does not contain a column for year {config.solve_year}")
            total_imports = total_imports.select(
                "r",
                pl.col(str(config.solve_year)).cast(pl.Float64).alias("value"),
            )

        duplicate_regions = total_imports.group_by("r").len().filter(pl.col("len") > 1)
        if not duplicate_regions.is_empty():
            region_name = duplicate_regions["r"].item(0)
            raise ValueError(
                f"Import data contains multiple values for region {region_name} "
                f"in solve year {config.solve_year}"
            )

        daily_fractions = _prepare_daily_import_fractions(hour_map, szn_frac, config.weather_year)

        initial_time = datetime(year=config.weather_year, month=1, day=1)

        # Find Canadian import generators
        for generator in system.get_components(
            ReEDSGenerator,
            filter_func=lambda component: (
                component.category == "imports"
                or "can-imports" in component.name.lower()
                or "canada_import" in component.technology.lower()
            ),
        ):
            # Get region name from the generator's region
            region_name = generator.region.name

            # Filter total imports for this region
            region_imports = total_imports.filter(pl.col("r") == region_name)

            if region_imports.is_empty():
                logger.warning("No import data found for region {}", region_name)
                continue

            total_import_value = region_imports["value"].item()
            daily_budget_gwh = total_import_value * daily_fractions.to_numpy() / 1e3

            ts = SingleTimeSeries.from_array(
                data=daily_budget_gwh,  # Data in GWh
                name="hydro_budget",
                initial_timestamp=initial_time,
                resolution=timedelta(days=1),
            )

            features = {"solve_year": config.solve_year} if config.solve_year is not None else {}
            system.add_time_series(ts, generator, **features)
            logger.debug("Added imports time series to generator: {}", generator.name)

        logger.info("Finished adding imports time series")
    except Exception as e:
        logger.error("Error in imports plugin: {}", e)
        return Err(str(e))

    return Ok(system)
