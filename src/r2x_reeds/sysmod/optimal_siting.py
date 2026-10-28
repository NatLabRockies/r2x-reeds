"""Apply cost-optimal siting load increments to existing demand profiles."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl
from infrasys import SingleTimeSeries, System
from loguru import logger
from pydantic import Field
from rust_ok import Err, Ok, Result

from r2x_core import PluginConfig, expose_plugin
from r2x_core.exceptions import ReaderError
from r2x_reeds.models.components import ReEDSDemand
from r2x_reeds.sysmod.utils import read_tabular_frame


class OptimalSitingConfig(PluginConfig):
    """Configuration for applying loadsite-based optimal siting increments."""

    loadsite_op_fpath: Path | str | None = Field(
        default=None,
        description="Path to loadsite_op.csv file.",
    )
    hour_map_myr_fpath: Path | str | None = Field(
        default=None,
        description="Path to hmap_myr.csv file.",
    )
    solve_year: int | list[int] | None = Field(
        default=None,
        description="Solve year used to filter loadsite rows when the file contains multiple years.",
    )


@expose_plugin
def add_optimal_siting(system: System, config: OptimalSitingConfig) -> Result[System, Exception]:
    """Add optimal siting increments to existing load profiles.

    This transform expects load time series to already exist on ReEDSDemand components.
    """
    if config.loadsite_op_fpath is None or config.hour_map_myr_fpath is None:
        logger.debug("Missing loadsite_op_fpath or hour_map_myr_fpath. Skipping optimal siting plugin.")
        return Ok(system)

    try:
        prepared_frames = _load_and_prepare_frames(config)
        if prepared_frames is None:
            return Ok(system)
        loadsite, hour_map_myr = prepared_frames

        increments_by_region = _build_region_increments(loadsite, hour_map_myr)
        if not increments_by_region:
            logger.info("No optimal siting increments found. Skipping optimal siting plugin.")
            return Ok(system)

        updated = _apply_increments_to_demands(system, increments_by_region)
        logger.info("Applied optimal siting increments to {} demand components", updated)
    except (OSError, ReaderError, ValueError, TypeError, pl.exceptions.PolarsError) as exc:
        logger.error("Optimal siting plugin failed: {}", exc)
        return Err(exc)

    return Ok(system)


def _normalize_loadsite_columns(frame: pl.DataFrame) -> pl.DataFrame:
    """Normalize known loadsite column names from raw and mapped schemas."""
    rename_map = {
        "r": "region",
        "allh": "hour_period",
        "t": "year",
        "Value": "value",
    }
    normalized = frame.rename({k: v for k, v in rename_map.items() if k in frame.columns})
    if "year" in normalized.columns:
        normalized = normalized.with_columns(pl.col("year").cast(pl.Int64))
    return normalized


def _load_and_prepare_frames(config: OptimalSitingConfig) -> tuple[pl.DataFrame, pl.DataFrame] | None:
    """Load, normalize, and year-filter input frames; return None when plugin should no-op."""
    if config.loadsite_op_fpath is None or config.hour_map_myr_fpath is None:
        return None

    loadsite = read_tabular_frame(config.loadsite_op_fpath, name="loadsite_op")
    hour_map_myr = read_tabular_frame(config.hour_map_myr_fpath, name="hour_map_myr")

    if loadsite.is_empty():
        logger.debug("loadsite_op data is empty. Skipping optimal siting plugin.")
        return None
    if hour_map_myr.is_empty():
        logger.debug("hour_map_myr data is empty. Skipping optimal siting plugin.")
        return None

    loadsite = _normalize_loadsite_columns(loadsite)
    hour_map_myr = _normalize_hour_map_columns(hour_map_myr)

    solve_years = tuple(
        dict.fromkeys(
            (config.solve_year,) if isinstance(config.solve_year, int) else (config.solve_year or ())
        )
    )
    if solve_years:
        if "year" in loadsite.columns:
            loadsite = loadsite.filter(pl.col("year").is_in(solve_years))
        else:
            selected_years = pl.DataFrame({"year": pl.Series(solve_years, dtype=pl.Int64)})
            loadsite = loadsite.join(selected_years, how="cross")

    if loadsite.is_empty():
        logger.info("No loadsite rows remained after year filtering. Skipping optimal siting plugin.")
        return None

    return loadsite, hour_map_myr


def _build_region_increments(
    loadsite: pl.DataFrame, hour_map_myr: pl.DataFrame
) -> dict[tuple[int | None, str], np.ndarray]:
    """Expand region values over the hour map, retaining any source solve year."""
    has_year = "year" in loadsite.columns
    state_columns = ["year", "region"] if has_year else ["region"]
    keys = [*state_columns, "hour_period"]
    if loadsite.select(*keys).is_duplicated().any():
        msg = "Loadsite rows contain duplicate solve-year/region/hour-period keys"
        raise ValueError(msg)
    if hour_map_myr.select("sequential_hour").is_duplicated().any():
        msg = "Hour map contains duplicate sequential hours"
        raise ValueError(msg)

    states = loadsite.select(*state_columns).unique(maintain_order=True)
    expanded = states.join(hour_map_myr.select("hour_period", "sequential_hour"), how="cross")
    expanded = expanded.join(
        loadsite.select(*keys, "value"),
        on=keys,
        how="left",
    ).with_columns(pl.col("value").fill_null(0.0).round(5))
    increments: dict[tuple[int | None, str], np.ndarray] = {}
    for state in states.iter_rows(named=True):
        region = str(state["region"])
        year = int(state["year"]) if has_year else None
        selector = pl.col("region") == region
        if year is not None:
            selector &= pl.col("year") == year
        increments[(year, region)] = expanded.filter(selector).sort("sequential_hour")["value"].to_numpy()
    return increments


def _apply_increments_to_demands(
    system: System, increments_by_state: dict[tuple[int | None, str], np.ndarray]
) -> int:
    """Apply year-matched increments while preserving each series' metadata features."""
    updated = 0
    for demand in system.get_components(ReEDSDemand):
        region_name = demand.region.name
        increment = increments_by_state.get((demand.solve_year, region_name))
        if increment is None:
            increment = increments_by_state.get((None, region_name))
        if increment is None:
            continue

        for metadata in system.list_time_series_metadata(demand, name="max_active_power"):
            series_solve_year = metadata.features.get("solve_year")
            if series_solve_year is not None and series_solve_year != demand.solve_year:
                continue
            series = system.get_time_series(demand, name=metadata.name, **metadata.features)
            base = np.asarray(series.data, dtype=np.float64)
            values = np.asarray(increment, dtype=np.float64)
            min_len = min(len(base), len(values))
            if min_len == 0:
                continue

            merged = base.copy()
            merged[:min_len] += values[:min_len]
            updated_ts = SingleTimeSeries.from_array(
                data=merged,
                name=series.name,
                initial_timestamp=series.initial_timestamp,
                resolution=series.resolution,
            )
            system.remove_time_series(demand, name=series.name, **metadata.features)
            system.add_time_series(updated_ts, demand, **metadata.features)
            updated += 1
    return updated


def _normalize_hour_map_columns(frame: pl.DataFrame) -> pl.DataFrame:
    """Normalize known hour-map column names from raw and mapped schemas."""
    rename_map = {
        "yearhour": "sequential_hour",
        "h": "hour_period",
    }
    return frame.rename({k: v for k, v in rename_map.items() if k in frame.columns})
