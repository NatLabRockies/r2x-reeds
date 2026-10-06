"""System modifier for fixed purchaser loads and data center demand."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import TypeVar

import h5py
import numpy as np
import polars as pl
from infrasys import Component, SingleTimeSeries, System
from loguru import logger
from pydantic import Field
from rust_ok import Err, Ok, Result

from r2x_core import DataStore, PluginConfig, expose_plugin
from r2x_reeds.models.components import (
    ReEDSDataCenterDemand,
    ReEDSElectrolyzerDemand,
    ReEDSRegion,
    ReEDSSteamMethaneReformingDemand,
)
from r2x_reeds.parser_utils import expand_loadsite_hourly

TComponent = TypeVar("TComponent", bound=Component)
HYDROGEN_PRODUCTION_COMPONENT_TYPES = {
    "electrolyzer": ReEDSElectrolyzerDemand,
    "smr": ReEDSSteamMethaneReformingDemand,
    "smr_ccs": ReEDSSteamMethaneReformingDemand,
}
HYDROGEN_PRODUCTION_TECHNOLOGIES = tuple(HYDROGEN_PRODUCTION_COMPONENT_TYPES)
H5_DATASET_KEYS = {
    "hydrogen_production_capacity": "cap",
    "hydrogen_production_load": "prod_load",
    "hydrogen_production_annual_load": "prod_load_ann",
    "loadsite_op": "loadsite_op",
}


class PurchaserLoadConfig(PluginConfig):
    """Configuration for adding purchaser-load consuming technologies."""

    solve_year: int | None = Field(
        default=None,
        description="Solve year used to filter purchaser load inputs when files contain multiple years.",
    )
    weather_year: int = Field(
        default=2012,
        description="Weather year used for time series initial timestamp.",
    )
    hydrogen_production_capacity_fpath: Path | str | None = Field(
        default=None,
        description="Path to cap.csv containing hydrogen-production installed capacity.",
    )
    consume_characteristics_fpath: Path | str | None = Field(
        default=None,
        description="Path to consume_char.csv containing electricity_efficiency.",
    )
    hydrogen_production_load_fpath: Path | str | None = Field(
        default=None,
        description="Path to prod_load.csv containing representative-period hydrogen-production demand.",
    )
    hydrogen_production_annual_load_fpath: Path | str | None = Field(
        default=None,
        description="Path to prod_load_ann.csv with annual hydrogen-production demand targets.",
    )
    loadsite_op_fpath: Path | str | None = Field(
        default=None,
        description="Path to loadsite_op.csv containing data center demand by representative period.",
    )
    hour_map_myr_fpath: Path | str | None = Field(
        default=None,
        description="Path to hmap_myr.csv mapping sequential hours to representative periods.",
    )


def _read_optional_frame(path: Path | str | None, name: str) -> pl.DataFrame | None:
    """Load an optional CSV/HDF-backed frame and collect it eagerly.

    Parameters
    ----------
    path : Path | str | None
        Input path to load. If ``None``, returns ``None``.
    name : str
        Logical dataset name used for DataStore reader selection.

    Returns
    -------
    pl.DataFrame | None
        Collected DataFrame if available, otherwise ``None``.
    """
    if path is None:
        return None
    path = Path(path)
    if path.suffix.lower() in {".h5", ".hdf5"}:
        dataset_key = H5_DATASET_KEYS.get(name, name)
        with h5py.File(path, mode="r") as h5_file:
            group = h5_file.get(dataset_key)
            if not isinstance(group, h5py.Group):
                logger.warning("Dataset '{}' not found in {}", dataset_key, path)
                return None

            columns_node = group.get("columns")
            if columns_node is None:
                logger.warning("Dataset '{}' is missing 'columns' in {}", dataset_key, path)
                return None

            columns = [_decode_h5_scalar(value) for value in np.asarray(columns_node[()]).tolist()]
            data: dict[str, list[object]] = {}
            for column in columns:
                node = group.get(str(column))
                if node is None:
                    logger.warning("Dataset '{}' is missing column '{}' in {}", dataset_key, column, path)
                    return None
                values = np.asarray(node[()])
                if values.ndim == 0:
                    values = values.reshape(1)
                data[str(column)] = [_decode_h5_scalar(value) for value in values.tolist()]
            return pl.DataFrame(data, strict=False)

    frame = DataStore.load_file(path, name=name)
    if frame is None:
        return None
    return frame.collect()


def _decode_h5_scalar(value: object) -> object:
    """Decode byte-valued HDF5 columns to strings."""
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, np.bytes_):
        return value.tobytes().decode("utf-8")
    return value


def _normalize_hour_map_myr(frame: pl.DataFrame) -> pl.DataFrame:
    """Normalize `hmap_myr` schema to parser-utils expected column names.

    Parameters
    ----------
    frame : pl.DataFrame
        Raw mapping frame which may contain legacy columns ``yearhour``/``h``.

    Returns
    -------
    pl.DataFrame
        Normalized frame with ``sequential_hour`` and ``hour_period`` columns.
    """
    rename_map: dict[str, str] = {}
    if "yearhour" in frame.columns:
        rename_map["yearhour"] = "sequential_hour"
    if "h" in frame.columns:
        rename_map["h"] = "hour_period"
    normalized = frame.rename(rename_map)
    return normalized.with_columns(
        pl.col("sequential_hour").cast(pl.Int64, strict=False),
        pl.col("hour_period").cast(pl.Utf8),
    )


def _rename_existing_columns(frame: pl.DataFrame, rename_map: dict[str, str]) -> pl.DataFrame:
    """Rename raw ReEDS columns without repeating DataStore mappings."""
    return frame.rename(
        {
            source: target
            for source, target in rename_map.items()
            if source in frame.columns and target not in frame.columns
        }
    )


def _normalize_loadsite(frame: pl.DataFrame, solve_year: int | None) -> pl.DataFrame:
    """Normalize loadsite-like tables to region/hour/value format.

    Parameters
    ----------
    frame : pl.DataFrame
        Input frame using ReEDS-style columns (e.g. ``r``, ``allh``, ``Value``, ``t``).
    solve_year : int | None
        Optional solve year filter.

    Returns
    -------
    pl.DataFrame
        Frame with columns ``region``, ``hour_period``, ``value``.
    """
    rename_map: dict[str, str] = {}
    if "r" in frame.columns:
        rename_map["r"] = "region"
    if "allh" in frame.columns:
        rename_map["allh"] = "hour_period"
    if "Value" in frame.columns:
        rename_map["Value"] = "value"
    if "t" in frame.columns:
        rename_map["t"] = "year"

    normalized = frame.rename(rename_map)
    if solve_year is not None and "year" in normalized.columns:
        normalized = normalized.filter(pl.col("year").cast(pl.Int64, strict=False) == solve_year)

    return normalized.with_columns(
        pl.col("region").cast(pl.Utf8),
        pl.col("hour_period").cast(pl.Utf8),
        pl.when(pl.col("value").cast(pl.Utf8, strict=False).str.to_lowercase() == "eps")
        .then(pl.lit(0.0))
        .otherwise(pl.col("value"))
        .cast(pl.Float64, strict=False)
        .fill_null(0.0)
        .alias("value"),
    ).select("region", "hour_period", "value")


def _get_region(system: System, region_name: str) -> ReEDSRegion | None:
    """Fetch region component by name, returning ``None`` when absent."""
    try:
        return system.get_component(ReEDSRegion, name=region_name)
    except Exception:
        return None


def _component_exists(system: System, component_type: type[TComponent], name: str) -> bool:
    """Check whether a component of ``component_type`` exists in system by name."""
    try:
        system.get_component(component_type, name)
        return True
    except Exception:
        return False


@expose_plugin
def add_purchaser_load(system: System, config: PurchaserLoadConfig) -> Result[System, str]:
    """Attach purchaser-load consuming technologies to a pre-built system."""

    try:
        hour_map_raw = _read_optional_frame(config.hour_map_myr_fpath, "hour_map_myr")
        if hour_map_raw is None or hour_map_raw.is_empty():
            logger.debug("Missing hour_map_myr input; skipping purchaser load modifier.")
            return Ok(system)

        hour_map = _normalize_hour_map_myr(hour_map_raw)

        # Hydrogen-production demand components from cap.csv + consume_char.csv.
        hydrogen_production_capacity_raw = _read_optional_frame(
            config.hydrogen_production_capacity_fpath,
            "hydrogen_production_capacity",
        )
        consume_char_raw = _read_optional_frame(
            config.consume_characteristics_fpath,
            "consume_characteristics",
        )
        if hydrogen_production_capacity_raw is not None and not hydrogen_production_capacity_raw.is_empty():
            cap_df = _rename_existing_columns(
                hydrogen_production_capacity_raw,
                {"i": "technology", "r": "region", "Value": "capacity", "t": "year"},
            )
            if config.solve_year is not None and "year" in cap_df.columns:
                cap_df = cap_df.filter(pl.col("year").cast(pl.Int64, strict=False) == config.solve_year)

            cap_df = cap_df.with_columns(
                pl.col("technology").cast(pl.Utf8).str.to_lowercase().alias("technology")
            ).filter(pl.col("technology").is_in(HYDROGEN_PRODUCTION_TECHNOLOGIES))

            efficiencies: dict[str, float] = {}
            if consume_char_raw is not None and not consume_char_raw.is_empty():
                consume_df = _rename_existing_columns(
                    consume_char_raw,
                    {"*i": "technology", "t": "year"},
                )
                if config.solve_year is not None and "year" in consume_df.columns:
                    consume_df = consume_df.filter(
                        pl.col("year").cast(pl.Int64, strict=False) == config.solve_year
                    )
                eff_rows = consume_df.with_columns(
                    pl.col("technology").cast(pl.Utf8).str.to_lowercase().alias("technology"),
                    pl.col("parameter").cast(pl.Utf8).str.to_lowercase().alias("parameter"),
                ).filter(
                    pl.col("technology").is_in(HYDROGEN_PRODUCTION_TECHNOLOGIES)
                    & (pl.col("parameter") == "electricity_efficiency")
                )
                for row in eff_rows.select("technology", "value").iter_rows(named=True):
                    efficiencies.setdefault(str(row["technology"]), float(row["value"]))

            created = 0
            for row in cap_df.iter_rows(named=True):
                technology = str(row["technology"])
                region_name = str(row.get("region", ""))
                region = _get_region(system, region_name)
                if not region:
                    logger.debug("Skipping {} load in unknown region '{}'", technology, region_name)
                    continue

                capacity = float(row.get("capacity", 0.0) or 0.0)
                if capacity <= 0.0:
                    continue

                name = f"{region_name}_{technology}_demand"
                component_type = HYDROGEN_PRODUCTION_COMPONENT_TYPES[technology]
                if _component_exists(system, component_type, name):
                    continue

                system.add_component(
                    component_type(
                        name=name,
                        region=region,
                        technology=technology,
                        capacity=capacity,
                        electricity_efficiency=efficiencies.get(technology, 1.0),
                    )
                )
                created += 1
            if created > 0:
                logger.info("Attached {} hydrogen-production demand components", created)

        # Data center consuming demand components from loadsite_op.csv.
        loadsite_raw = _read_optional_frame(config.loadsite_op_fpath, "loadsite_op")
        if loadsite_raw is not None and not loadsite_raw.is_empty():
            loadsite = _normalize_loadsite(loadsite_raw, config.solve_year)
            expanded_result = expand_loadsite_hourly(loadsite_data=loadsite, hour_map_myr=hour_map)
            if expanded_result.is_err():
                return Err(str(expanded_result.unwrap_err()))
            expanded = expanded_result.unwrap()

            created = 0
            for region_name in expanded.select("region").unique().to_series().to_list():
                region_key = str(region_name)
                region = _get_region(system, region_key)
                if not region:
                    logger.debug("Skipping data center load in unknown region '{}'", region_key)
                    continue

                region_profile = (
                    expanded.filter(pl.col("region") == region_key)
                    .sort("sequential_hour")
                    .select("value")
                    .to_series()
                    .to_numpy()
                )
                if region_profile.size == 0:
                    continue

                name = f"{region_key}_data_center_demand"
                if _component_exists(system, ReEDSDataCenterDemand, name):
                    continue

                system.add_component(
                    ReEDSDataCenterDemand(
                        name=name,
                        region=region,
                        technology="data-center",
                        capacity=float(region_profile.max()),
                        electricity_efficiency=1.0,
                    )
                )
                created += 1
            if created > 0:
                logger.info("Attached {} data center demand components", created)

        # Attach hydrogen-production profile time series.
        hydrogen_production_profile_raw = _read_optional_frame(
            config.hydrogen_production_load_fpath,
            "hydrogen_production_load",
        )
        hydrogen_production_annual_raw = _read_optional_frame(
            config.hydrogen_production_annual_load_fpath,
            "hydrogen_production_annual_load",
        )
        if hydrogen_production_profile_raw is not None and not hydrogen_production_profile_raw.is_empty():
            profile = _rename_existing_columns(
                hydrogen_production_profile_raw,
                {
                    "i": "technology",
                    "r": "region",
                    "allh": "hour_period",
                    "Value": "value",
                    "t": "year",
                },
            )
            if config.solve_year is not None and "year" in profile.columns:
                profile = profile.filter(pl.col("year").cast(pl.Int64, strict=False) == config.solve_year)

            profile = profile.with_columns(
                pl.col("technology").cast(pl.Utf8).str.to_lowercase().alias("technology")
            ).filter(pl.col("technology").is_in(HYDROGEN_PRODUCTION_TECHNOLOGIES))
            profile = profile.select("technology", "region", "hour_period", "value")

            annual_targets: dict[tuple[str, str], float] = {}
            if hydrogen_production_annual_raw is not None and not hydrogen_production_annual_raw.is_empty():
                annual = _rename_existing_columns(
                    hydrogen_production_annual_raw,
                    {
                        "i": "technology",
                        "r": "region",
                        "Value": "value",
                        "t": "year",
                    },
                )
                if config.solve_year is not None and "year" in annual.columns:
                    annual = annual.filter(pl.col("year").cast(pl.Int64, strict=False) == config.solve_year)

                annual = annual.with_columns(
                    pl.col("technology").cast(pl.Utf8).str.to_lowercase().alias("technology")
                )
                annual_targets = {
                    (str(row["technology"]), str(row["region"])): float(row["value"])
                    for row in annual.filter(pl.col("technology").is_in(HYDROGEN_PRODUCTION_TECHNOLOGIES))
                    .select("technology", "region", "value")
                    .iter_rows(named=True)
                }

            attached = 0
            for technology, component_type in HYDROGEN_PRODUCTION_COMPONENT_TYPES.items():
                technology_profile = profile.filter(pl.col("technology") == technology)
                if technology_profile.is_empty():
                    continue

                expanded_result = expand_loadsite_hourly(
                    loadsite_data=_normalize_loadsite(
                        technology_profile.select("region", "hour_period", "value"), None
                    ),
                    hour_map_myr=hour_map,
                )
                if expanded_result.is_err():
                    return Err(str(expanded_result.unwrap_err()))
                expanded = expanded_result.unwrap()

                for demand in system.get_components(component_type):
                    if demand.technology.casefold() != technology:
                        continue
                    region_profile = (
                        expanded.filter(pl.col("region") == demand.region.name)
                        .sort("sequential_hour")
                        .select("value")
                        .to_series()
                        .to_numpy()
                    )
                    if region_profile.size == 0:
                        continue

                    target = annual_targets.get((technology, demand.region.name))
                    current = float(region_profile.sum())
                    if target is not None and current > 0 and target >= 0:
                        region_profile = region_profile * (target / current)

                    ts = SingleTimeSeries.from_array(
                        data=region_profile,
                        name="max_active_power",
                        initial_timestamp=datetime(year=config.weather_year, month=1, day=1),
                        resolution=timedelta(hours=1),
                    )
                    system.add_time_series(ts, demand)
                    attached += 1
            if attached > 0:
                logger.info("Attached hydrogen-production profiles to {} demand components", attached)

        # Attach data center profile time series from loadsite_op.
        if loadsite_raw is not None and not loadsite_raw.is_empty():
            loadsite = _normalize_loadsite(loadsite_raw, config.solve_year)
            expanded_result = expand_loadsite_hourly(loadsite_data=loadsite, hour_map_myr=hour_map)
            if expanded_result.is_err():
                return Err(str(expanded_result.unwrap_err()))
            expanded = expanded_result.unwrap()

            attached = 0
            for demand in system.get_components(ReEDSDataCenterDemand):
                region_profile = (
                    expanded.filter(pl.col("region") == demand.region.name)
                    .sort("sequential_hour")
                    .select("value")
                    .to_series()
                    .to_numpy()
                )
                if region_profile.size == 0:
                    continue

                ts = SingleTimeSeries.from_array(
                    data=region_profile,
                    name="max_active_power",
                    initial_timestamp=datetime(year=config.weather_year, month=1, day=1),
                    resolution=timedelta(hours=1),
                )
                system.add_time_series(ts, demand)
                attached += 1
            if attached > 0:
                logger.info("Attached data center load profiles to {} demand components", attached)

    except Exception as exc:
        logger.error("Error in purchaser load modifier: {}", exc)
        return Err(str(exc))

    return Ok(system)
