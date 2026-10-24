"""System modifier for fixed purchaser loads and data center demand."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import TypeVar

import polars as pl
from infrasys import Component, SingleTimeSeries, System
from loguru import logger
from pydantic import Field
from rust_ok import Err, Ok, Result

from r2x_core import PluginConfig, expose_plugin
from r2x_core.exceptions import ReaderError
from r2x_reeds.models.components import (
    ReEDSDataCenterDemand,
    ReEDSElectrolyzerDemand,
    ReEDSRegion,
    ReEDSSteamMethaneReformingDemand,
)
from r2x_reeds.sysmod.utils import read_tabular_frame

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
    """Read a configured input, returning None only when no path was supplied."""
    if path is None:
        return None
    input_path = Path(path)
    dataset_key = H5_DATASET_KEYS.get(name) if input_path.suffix.lower() in {".h5", ".hdf5"} else None
    return read_tabular_frame(input_path, name=name, hdf5_group=dataset_key)


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


def _scope_solve_year(frame: pl.DataFrame, solve_year: int | None) -> pl.DataFrame:
    """Normalize an input's year dimension and select the configured state."""
    if "year" not in frame.columns:
        value: int | None = solve_year
        return frame.with_columns(pl.lit(value, dtype=pl.Int64).alias("year"))

    normalized = frame.with_columns(pl.col("year").cast(pl.Int64))
    if solve_year is not None:
        normalized = normalized.filter(pl.col("year") == solve_year)
    return normalized


def _year_filter(year: int | None) -> pl.Expr:
    """Select one solve-year partition, including static inputs without a year."""
    return pl.col("year").is_null() if year is None else pl.col("year") == year


def _normalize_loadsite(frame: pl.DataFrame, solve_year: int | None) -> pl.DataFrame:
    """Normalize loadsite-like rows while retaining their solve year."""
    rename_map: dict[str, str] = {}
    if "r" in frame.columns:
        rename_map["r"] = "region"
    if "allh" in frame.columns:
        rename_map["allh"] = "hour_period"
    if "Value" in frame.columns:
        rename_map["Value"] = "value"
    if "t" in frame.columns:
        rename_map["t"] = "year"

    normalized = _scope_solve_year(frame.rename(rename_map), solve_year)
    return normalized.with_columns(
        pl.col("region").cast(pl.Utf8),
        pl.col("hour_period").cast(pl.Utf8),
        pl.when(pl.col("value").cast(pl.Utf8, strict=False).str.to_lowercase() == "eps")
        .then(pl.lit(0.0))
        .otherwise(pl.col("value"))
        .cast(pl.Float64, strict=False)
        .fill_null(0.0)
        .alias("value"),
    ).select("year", "region", "hour_period", "value")


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
def add_purchaser_load(system: System, config: PurchaserLoadConfig) -> Result[System, Exception]:
    """Attach purchaser-load consuming technologies to a pre-built system."""

    try:
        hour_map_raw = _read_optional_frame(config.hour_map_myr_fpath, "hour_map_myr")
        if hour_map_raw is None or hour_map_raw.is_empty():
            logger.debug("Missing hour_map_myr input; skipping purchaser load modifier.")
            return Ok(system)

        hour_map = _normalize_hour_map_myr(hour_map_raw)
        if hour_map.select("sequential_hour").is_duplicated().any():
            msg = "Hour map contains duplicate sequential hours"
            raise ValueError(msg)

        expanded_loadsite: pl.DataFrame | None = None

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
            cap_df = (
                _scope_solve_year(
                    _rename_existing_columns(
                        hydrogen_production_capacity_raw,
                        {"i": "technology", "r": "region", "Value": "capacity", "t": "year"},
                    ),
                    config.solve_year,
                )
                .with_columns(pl.col("technology").cast(pl.Utf8).str.to_lowercase().alias("technology"))
                .filter(pl.col("technology").is_in(HYDROGEN_PRODUCTION_TECHNOLOGIES))
            )

            efficiencies: dict[tuple[int | None, str], float] = {}
            if consume_char_raw is not None and not consume_char_raw.is_empty():
                consume_df = _scope_solve_year(
                    _rename_existing_columns(
                        consume_char_raw,
                        {"*i": "technology", "t": "year"},
                    ),
                    config.solve_year,
                )
                eff_rows = consume_df.with_columns(
                    pl.col("technology").cast(pl.Utf8).str.to_lowercase().alias("technology"),
                    pl.col("parameter").cast(pl.Utf8).str.to_lowercase().alias("parameter"),
                ).filter(
                    pl.col("technology").is_in(HYDROGEN_PRODUCTION_TECHNOLOGIES)
                    & (pl.col("parameter") == "electricity_efficiency")
                )
                for row in eff_rows.select("year", "technology", "value").iter_rows(named=True):
                    efficiencies.setdefault((row["year"], str(row["technology"])), float(row["value"]))

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

                solve_year = row["year"]
                suffix = f"_{solve_year}" if solve_year is not None else ""
                name = f"{region_name}_{technology}_demand{suffix}"
                component_type = HYDROGEN_PRODUCTION_COMPONENT_TYPES[technology]
                if _component_exists(system, component_type, name):
                    continue

                system.add_component(
                    component_type(
                        name=name,
                        region=region,
                        technology=technology,
                        capacity=capacity,
                        electricity_efficiency=efficiencies.get((solve_year, technology), 1.0),
                        solve_year=solve_year,
                    )
                )
                created += 1
            if created > 0:
                logger.info("Attached {} hydrogen-production demand components", created)

        # Data center consuming demand components from loadsite_op.csv.
        loadsite_raw = _read_optional_frame(config.loadsite_op_fpath, "loadsite_op")
        if loadsite_raw is not None and not loadsite_raw.is_empty():
            loadsite = _normalize_loadsite(loadsite_raw, config.solve_year)
            if loadsite.select("year", "region", "hour_period").is_duplicated().any():
                msg = "Loadsite rows contain duplicate solve-year/region/hour-period keys"
                raise ValueError(msg)
            expanded_loadsite = (
                loadsite.select("year", "region")
                .unique(maintain_order=True)
                .join(hour_map.select("hour_period", "sequential_hour"), how="cross")
                .join(
                    loadsite.select("year", "region", "hour_period", "value"),
                    on=["year", "region", "hour_period"],
                    how="left",
                    nulls_equal=True,
                )
                .with_columns(pl.col("value").fill_null(0.0).round(5))
                .sort(["year", "region", "sequential_hour"])
            )

            created = 0
            for state in expanded_loadsite.select("year", "region").unique().iter_rows(named=True):
                solve_year = state["year"]
                region_key = str(state["region"])
                selector = _year_filter(solve_year) & (pl.col("region") == region_key)
                region = _get_region(system, region_key)
                if not region:
                    logger.debug("Skipping data center load in unknown region '{}'", region_key)
                    continue

                region_profile = (
                    expanded_loadsite.filter(selector)
                    .sort("sequential_hour")
                    .select("value")
                    .to_series()
                    .to_numpy()
                )
                if region_profile.size == 0:
                    continue

                suffix = f"_{solve_year}" if solve_year is not None else ""
                name = f"{region_key}_data_center_demand{suffix}"
                if _component_exists(system, ReEDSDataCenterDemand, name):
                    continue

                system.add_component(
                    ReEDSDataCenterDemand(
                        name=name,
                        region=region,
                        technology="data-center",
                        capacity=float(region_profile.max()),
                        electricity_efficiency=1.0,
                        solve_year=solve_year,
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
            profile = (
                _scope_solve_year(
                    _rename_existing_columns(
                        hydrogen_production_profile_raw,
                        {
                            "i": "technology",
                            "r": "region",
                            "allh": "hour_period",
                            "Value": "value",
                            "t": "year",
                        },
                    ),
                    config.solve_year,
                )
                .with_columns(pl.col("technology").cast(pl.Utf8).str.to_lowercase().alias("technology"))
                .filter(pl.col("technology").is_in(HYDROGEN_PRODUCTION_TECHNOLOGIES))
            )
            profile = profile.select("year", "technology", "region", "hour_period", "value")
            if profile.select("year", "technology", "region", "hour_period").is_duplicated().any():
                msg = "Hydrogen profiles contain duplicate solve-year/technology/region/hour-period keys"
                raise ValueError(msg)
            expanded_profile = (
                profile.select("year", "technology", "region")
                .unique(maintain_order=True)
                .join(hour_map.select("hour_period", "sequential_hour"), how="cross")
                .join(
                    profile,
                    on=["year", "technology", "region", "hour_period"],
                    how="left",
                    nulls_equal=True,
                )
                .with_columns(pl.col("value").fill_null(0.0).round(5))
                .sort(["year", "technology", "region", "sequential_hour"])
            )

            annual_targets: dict[tuple[int | None, str, str], float] = {}
            if hydrogen_production_annual_raw is not None and not hydrogen_production_annual_raw.is_empty():
                annual = (
                    _scope_solve_year(
                        _rename_existing_columns(
                            hydrogen_production_annual_raw,
                            {
                                "i": "technology",
                                "r": "region",
                                "Value": "value",
                                "t": "year",
                            },
                        ),
                        config.solve_year,
                    )
                    .with_columns(pl.col("technology").cast(pl.Utf8).str.to_lowercase().alias("technology"))
                    .filter(pl.col("technology").is_in(HYDROGEN_PRODUCTION_TECHNOLOGIES))
                )
                if annual.select("year", "technology", "region").is_duplicated().any():
                    msg = "Hydrogen annual loads contain duplicate solve-year/technology/region keys"
                    raise ValueError(msg)
                annual_targets = {
                    (row["year"], str(row["technology"]), str(row["region"])): float(row["value"])
                    for row in annual.select("year", "technology", "region", "value").iter_rows(named=True)
                }

            attached = 0
            for technology, component_type in HYDROGEN_PRODUCTION_COMPONENT_TYPES.items():
                technology_profile = profile.filter(pl.col("technology") == technology)
                if technology_profile.is_empty():
                    continue

                for demand in system.get_components(component_type):
                    if demand.technology.casefold() != technology:
                        continue
                    region_profile = (
                        expanded_profile.filter(
                            (pl.col("technology") == technology)
                            & (pl.col("region") == demand.region.name)
                            & _year_filter(demand.solve_year)
                        )
                        .sort("sequential_hour")
                        .select("value")
                        .to_series()
                        .to_numpy()
                    )
                    if region_profile.size == 0:
                        continue

                    target = annual_targets.get((demand.solve_year, technology, demand.region.name))
                    current = float(region_profile.sum())
                    if target is not None and current > 0 and target >= 0:
                        region_profile = region_profile * (target / current)

                    ts = SingleTimeSeries.from_array(
                        data=region_profile,
                        name="max_active_power",
                        initial_timestamp=datetime(year=config.weather_year, month=1, day=1),
                        resolution=timedelta(hours=1),
                    )
                    features = {"solve_year": demand.solve_year} if demand.solve_year is not None else {}
                    system.add_time_series(ts, demand, **features)
                    attached += 1
            if attached > 0:
                logger.info("Attached hydrogen-production profiles to {} demand components", attached)

        # Attach data center profile time series from loadsite_op.
        if expanded_loadsite is not None:
            attached = 0
            for demand in system.get_components(ReEDSDataCenterDemand):
                region_profile = (
                    expanded_loadsite.filter(
                        (pl.col("region") == demand.region.name) & _year_filter(demand.solve_year)
                    )
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
                features = {"solve_year": demand.solve_year} if demand.solve_year is not None else {}
                system.add_time_series(ts, demand, **features)
                attached += 1
            if attached > 0:
                logger.info("Attached data center load profiles to {} demand components", attached)

    except (OSError, ReaderError, ValueError, pl.exceptions.PolarsError) as exc:
        logger.error("Error in purchaser load modifier: {}", exc)
        return Err(exc)

    return Ok(system)
