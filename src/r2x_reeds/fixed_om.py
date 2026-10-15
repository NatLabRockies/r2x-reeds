"""Resolve technology-year FOM and ReEDS' source-specific family overrides.

The assignments follow b_inputs.gms' Fixed OM and storage fixed OM sections.
This does not reconstruct the general thermal vintage averages or age escalation.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl
from loguru import logger
from rust_ok import Err, Ok, Result

from r2x_core import DataStore, TabularProcessing
from r2x_core.exceptions import ReaderError


@dataclass(frozen=True)
class UpgradeLink:
    """Declared source and target technologies for one ReEDS upgrade."""

    source: str
    target: str


@dataclass(frozen=True)
class HintageCost:
    """Hintage capacity in MW and FOM rates normalized to 2004$/MW/year."""

    capacity: float
    fixed_om: float
    ccs_retrofit: float | None


def configure_fom_processing(store: DataStore) -> None:
    """Configure core's hydro unpivot from the run's region-column schema."""
    if "fom_hydro" not in store:
        return
    data_file = store["fom_hydro"]
    processing = data_file.proc_spec
    if not isinstance(processing, TabularProcessing):
        msg = "fom_hydro requires TabularProcessing configuration"
        raise ValueError(msg)
    if processing.unpivot_on:
        return
    raw_frame = store.reader.read_data_file(
        data_file.model_copy(update={"proc_spec": None}), folder_path=store.folder
    )
    if not isinstance(raw_frame, pl.LazyFrame):
        msg = "fom_hydro must be a tabular dataset"
        raise ValueError(msg)
    regions = [column.lower() for column in raw_frame.collect_schema().names() if column != "technology"]
    if not regions:
        msg = "fom_hydro has no region columns to unpivot"
        raise ValueError(msg)
    configured = data_file.model_copy(
        update={"proc_spec": processing.model_copy(update={"unpivot_on": regions})}
    )
    store.add_data([configured], overwrite=True)


def collect_fom_dataset(
    store: DataStore, name: str, *, placeholders: dict[str, int] | None = None
) -> pl.DataFrame:
    """Collect a required configured dataset from the supplied context store."""
    frame = store.read_data(name, placeholders=placeholders)
    if not isinstance(frame, pl.LazyFrame):
        msg = f"Required FOM dataset {name!r} is unavailable"
        raise ValueError(msg)
    return frame.collect()


def prepare_fixed_om(
    capacity_data: pl.LazyFrame,
    *,
    store: DataStore,
    solve_year: int,
) -> Result[pl.LazyFrame, str]:
    """Return costs on capacity keys, preserving unknown costs as null values.

    Hydro uses nonzero regional overrides, PSH uses its scalar, distributed PV
    uses explicit hintage FOM, and upgrades follow their declared target links.
    Core processing converts unit-specific CCS retrofit FOM to $/MW/year.
    """
    try:
        costs = collect_fom_dataset(store, "cost_fom", placeholders={"solve_year": solve_year})
        if costs.is_empty():
            return Err(f"cost_fom: no FOM rows for solve year {solve_year}")
        plant = {
            str(tech): float(value) for tech, value in costs.select("technology", "fom_cost").iter_rows()
        }
        switches = {
            str(parameter): str(value)
            for parameter, value in collect_fom_dataset(store, "fom_switches").iter_rows()
        }
        scalars = {
            str(parameter): float(value)
            for parameter, value in collect_fom_dataset(store, "fom_scalars").iter_rows()
        }
        hydro_costs = {
            (str(tech), str(region)): float(value)
            for tech, region, value in collect_fom_dataset(store, "fom_hydro").iter_rows()
            if value is not None
        }
        subsets = collect_fom_dataset(store, "fom_technology_subsets")
        psh = set(subsets.filter(pl.col("psh") == "yes")["technology"].to_list())
        dpv = set(subsets.filter(pl.col("distpv") == "yes")["technology"].to_list())
        ccs = set(subsets.filter(pl.col("ccs") == "yes")["technology"].to_list())
        links_frame = collect_fom_dataset(store, "fom_upgrade_links")
        if switches.get("gsw_watermain") == "1":
            links_frame = pl.concat([links_frame, collect_fom_dataset(store, "fom_water_upgrade_links")])
        links = {
            str(tech): UpgradeLink(source=str(source), target=str(target))
            for tech, source, target in links_frame.iter_rows()
        }
        unitspec_frame = collect_fom_dataset(store, "fom_unitspec_upgrades")
        histories = {
            (str(row["technology"]), str(row["vintage"]), str(row["region"]), int(row["year"])): HintageCost(
                capacity=float(row["capacity"]),
                fixed_om=float(row["fom_cost"]),
                ccs_retrofit=float(row["ccs_retrofit_fom"]) if row["ccs_retrofit_fom"] is not None else None,
            )
            for row in collect_fom_dataset(store, "fom_hintage").iter_rows(named=True)
        }
        keys = capacity_data.select("technology", "vintage", "region", "year").unique().collect()
        active_upgrades = set(keys["technology"].to_list()) & links.keys()
        upgrade_plant: dict[str, float] = {}
        unitspec: set[str] = set()
        if active_upgrades:
            if switches.get("gsw_upgrades") != "1":
                return Err("Active generator upgrades require GSw_Upgrades=1")
            upgrade_year = int(switches["gsw_upgradechar_year"])
            upgrade_costs = collect_fom_dataset(store, "cost_fom", placeholders={"solve_year": upgrade_year})
            upgrade_plant = {
                str(tech): float(value)
                for tech, value in upgrade_costs.select("technology", "fom_cost").iter_rows()
            }
            if switches.get("gsw_upgradefom_nems") == "1":
                unitspec = set(unitspec_frame["technology"].to_list())
        resolved: list[float | None] = []
        for row in keys.iter_rows(named=True):
            tech, vintage, region, year = (
                str(row["technology"]),
                str(row["vintage"]),
                str(row["region"]),
                int(row["year"]),
            )
            value = plant.get(tech)
            if tech in dpv:
                history = histories.get((tech, vintage, region, year))
                if history is None:
                    return Err(f"Missing distributed-PV hintage FOM for {tech}/{vintage}/{region}/{year}")
                value = history.fixed_om
            regional_cost = hydro_costs.get((tech, region))
            if regional_cost:
                value = regional_cost
            if tech in links:
                link = links[tech]
                target_cost = (
                    upgrade_plant.get(link.target) if vintage.startswith("init") else plant.get(link.target)
                )
                if target_cost is None:
                    return Err(f"Missing upgrade target FOM for {tech}: target {link.target}")
                value = target_cost
                if vintage.startswith("init"):
                    value += hydro_costs.get((link.target, region), 0.0)
                    if tech in unitspec and link.target in ccs:
                        history = histories.get((link.source, vintage, region, year))
                        # ReEDS extends nonzero retrofit characteristics beyond the upgrade year.
                        if history is None or not history.ccs_retrofit:
                            upgrade_start = int(switches["gsw_upgradeyear"])
                            eligible = histories.get((link.source, vintage, region, upgrade_start))
                            if eligible is not None and eligible.capacity > 0:
                                prior = [
                                    (key[3], cost)
                                    for key, cost in histories.items()
                                    if key[:3] == (link.source, vintage, region)
                                    and key[3] < year
                                    and cost.ccs_retrofit
                                ]
                                if prior:
                                    history = max(prior, key=lambda item: item[0])[1]
                        if history is not None and history.ccs_retrofit:
                            value = history.ccs_retrofit
            if tech in psh:
                value = float(scalars["cost_fom_psh"])
            resolved.append(value)
        result = keys.with_columns(pl.Series("fom_cost", resolved, dtype=pl.Float64))
        unknown = result.filter(pl.col("fom_cost").is_null())
        if not unknown.is_empty():
            logger.warning(
                "Fixed O&M is unknown for technologies: {}", sorted(unknown["technology"].unique().to_list())
            )
        return Ok(result.lazy())
    except (OSError, ValueError, KeyError, ReaderError, pl.exceptions.PolarsError) as exc:
        return Err(f"Fixed O&M source data: {exc}")
