"""Plugin to add hourly Canadian exports to regional electric demand."""

from pathlib import Path

import numpy as np
import polars as pl
from infrasys import System
from infrasys.time_series_models import SingleTimeSeries
from loguru import logger
from pydantic import Field
from rust_ok import Err, Ok, Result

from r2x_core import DataStore, PluginConfig, expose_plugin
from r2x_reeds.models.components import ReEDSDemand


class ExportsConfig(PluginConfig):
    """Configuration for adding Canadian export time series."""

    weather_year: int | None = Field(default=None, description="Weather year for time series alignment.")
    solve_year: int | None = Field(
        default=None, description="ReEDS solve year used to select annual exports."
    )
    canada_exports_fpath: Path | str | None = Field(
        default=None,
        description="Path to CSV file containing annual Canadian exports by region and year.",
    )
    canada_exports_h_frac_fpath: Path | str | None = Field(
        default=None,
        description="Path to CSV file containing representative-hour export fractions.",
    )
    hour_map_fpath: Path | str | None = Field(
        default=None,
        description="Path to CSV file containing the chronological hour mapping.",
    )


def _prepare_hourly_export_fractions(
    hour_map: pl.DataFrame,
    hourly_fractions: pl.DataFrame,
    weather_year: int,
) -> pl.Series:
    """Expand representative-hour fractions into a normalized chronological profile."""
    required_map_columns = {"time_index", "h"}
    missing_map_columns = required_map_columns - set(hour_map.columns)
    if missing_map_columns:
        raise ValueError(f"Hour map is missing required columns: {sorted(missing_map_columns)}")

    required_fraction_columns = {"h", "value"}
    missing_fraction_columns = required_fraction_columns - set(hourly_fractions.columns)
    if missing_fraction_columns:
        raise ValueError(
            f"Hourly export fractions are missing required columns: {sorted(missing_fraction_columns)}"
        )

    if hour_map.schema["time_index"] == pl.String:
        hour_map = hour_map.with_columns(
            pl.col("time_index")
            .str.replace("T", " ")
            .str.replace(r"[+-]\d{2}:\d{2}$", "")
            .str.to_datetime(format="%Y-%m-%d %H:%M:%S"),
        )

    mapped_profile_hours = hour_map.select("h").unique()

    if "year" in hour_map.columns:
        mapped_years = hour_map["year"].drop_nulls().cast(pl.Int32).unique().sort().to_list()
        if weather_year in mapped_years:
            hour_map = hour_map.filter(pl.col("year").cast(pl.Int32) == weather_year)
        elif len(mapped_years) == 1:
            hour_map = hour_map.filter(pl.col("year").cast(pl.Int32) == mapped_years[0])
        else:
            raise ValueError(f"Could not identify a unique representative weather year: {mapped_years}")

    if hour_map.is_empty():
        raise ValueError(f"Hour map does not contain weather year {weather_year}")

    duplicate_hours = hourly_fractions.group_by("h").len().filter(pl.col("len") > 1)
    if duplicate_hours.height:
        raise ValueError("Hourly export fractions contain duplicate representative hours")

    mapped_hours = hour_map.join(hourly_fractions, on="h", how="left").sort("time_index")
    if mapped_hours["value"].null_count():
        raise ValueError("Hour map contains representative hours without export fractions")
    missing_profile_hours = hourly_fractions.join(mapped_profile_hours, on="h", how="anti")
    if missing_profile_hours.height:
        raise ValueError("Hourly export fractions contain hours absent from the hour map")

    invalid_fractions = mapped_hours.filter(
        pl.col("value").is_null() | ~pl.col("value").is_finite() | (pl.col("value") < 0)
    )
    if invalid_fractions.height:
        raise ValueError("Hourly export fractions contain negative or non-finite values")

    mapped_hours = mapped_hours.with_columns((pl.col("value") / pl.len().over("h")).alias("hourly_fraction"))
    total_fraction = mapped_hours["hourly_fraction"].sum()
    if total_fraction is None or total_fraction <= 0:
        raise ValueError("Hourly export fractions must have a positive sum")

    return mapped_hours.select((pl.col("hourly_fraction") / total_fraction).alias("value"))["value"]


@expose_plugin
def add_exports(system: System, config: ExportsConfig) -> Result[System, str]:
    """Add hourly Canadian export availability profiles to the system."""
    if config.weather_year is None:
        logger.warning("Weather year not specified. Skipping exports plugin.")
        return Ok(system)

    if (
        config.canada_exports_fpath is None
        or config.canada_exports_h_frac_fpath is None
        or config.hour_map_fpath is None
    ):
        logger.debug(
            "Missing required file paths for exports plugin "
            "(canada_exports_fpath, canada_exports_h_frac_fpath, hour_map_fpath)."
        )
        return Ok(system)

    try:
        hour_map = DataStore.load_file(config.hour_map_fpath, name="hour_map")
        hourly_fractions = DataStore.load_file(
            config.canada_exports_h_frac_fpath,
            name="canada_exports_h_frac",
        )
        annual_exports = DataStore.load_file(config.canada_exports_fpath, name="canada_exports")
        if hour_map is None or hourly_fractions is None or annual_exports is None:
            logger.warning("Exports input data could not be loaded. Skipping exports plugin.")
            return Ok(system)

        hour_map = hour_map.collect()
        hourly_fractions = hourly_fractions.collect()
        annual_exports = annual_exports.collect()

        if "*timestamp" in hour_map.columns:
            hour_map = hour_map.rename({"*timestamp": "time_index"})
        if "*h" in hour_map.columns:
            hour_map = hour_map.rename({"*h": "h"})
        if "*h" in hourly_fractions.columns:
            hourly_fractions = hourly_fractions.rename({"*h": "h"})
        if "frac_weighted" in hourly_fractions.columns:
            hourly_fractions = hourly_fractions.rename({"frac_weighted": "value"})

        if config.solve_year is None:
            raise ValueError("Solve year is required for wide Canadian export data")
        solve_year_column = str(config.solve_year)
        if solve_year_column not in annual_exports.columns:
            raise ValueError(f"Export data does not contain a column for year {config.solve_year}")
        if "r" not in annual_exports.columns:
            raise ValueError("Annual export data is missing required region column 'r'")
        duplicate_regions = annual_exports.group_by("r").len().filter(pl.col("len") > 1)
        if not duplicate_regions.is_empty():
            region_name = duplicate_regions["r"].item(0)
            raise ValueError(f"Export data contains multiple rows for region {region_name}")

        annual_exports = annual_exports.select(
            "r",
            pl.col(solve_year_column).cast(pl.Float64).alias("value"),
        )
        hourly_profile = _prepare_hourly_export_fractions(
            hour_map,
            hourly_fractions,
            config.weather_year,
        )

        demands_by_region: dict[str, ReEDSDemand] = {}
        for demand in system.get_components(
            ReEDSDemand,
            filter_func=lambda component: component.category != "electrolyzer",
        ):
            region_name = demand.region.name
            if region_name in demands_by_region:
                raise ValueError(f"Multiple demand components found for region {region_name}")
            demands_by_region[region_name] = demand

        for export_row in annual_exports.iter_rows(named=True):
            region_name = export_row["r"]
            demand = demands_by_region.get(region_name)
            if demand is None:
                logger.warning("No demand component found for export region {}", region_name)
                continue
            if not system.has_time_series(demand, name="max_active_power"):
                logger.warning("Demand component for export region {} has no load profile", region_name)
                continue

            annual_energy_mwh = export_row["value"]
            if annual_energy_mwh is None or not float("-inf") < annual_energy_mwh < float("inf"):
                raise ValueError(f"Export energy for region {region_name} must be finite")
            if annual_energy_mwh < 0:
                raise ValueError(f"Export energy for region {region_name} cannot be negative")

            time_series = system.get_time_series(demand, name="max_active_power")
            base_load_mw = np.asarray(time_series.data, dtype=np.float64)
            export_load_mw = annual_energy_mwh * hourly_profile.to_numpy()
            if len(base_load_mw) != len(export_load_mw):
                raise ValueError(
                    f"Load profile for region {region_name} has {len(base_load_mw)} hours, "
                    f"but the export profile has {len(export_load_mw)} hours"
                )

            updated_time_series = SingleTimeSeries.from_array(
                data=base_load_mw + export_load_mw,
                name=time_series.name,
                initial_timestamp=time_series.initial_timestamp,
                resolution=time_series.resolution,
            )
            system.remove_time_series(demand, name=time_series.name)
            system.add_time_series(updated_time_series, demand)
            logger.debug("Added Canadian export demand to region {}", region_name)
    except Exception as error:
        logger.error("Error in exports plugin: {}", error)
        return Err(str(error))

    return Ok(system)
