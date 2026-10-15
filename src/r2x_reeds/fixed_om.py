"""Resolve technology-year FOM and ReEDS' source-specific family overrides.

The assignments follow b_inputs.gms' Fixed OM and storage fixed OM sections.
This does not reconstruct the general thermal vintage averages or age escalation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import polars as pl
from loguru import logger
from rust_ok import Err, Ok, Result

from r2x_core import DataStore

from .data_readers import read_gams_header_csv


@dataclass(frozen=True)
class UpgradeLink:
    source: str
    target: str


@dataclass(frozen=True)
class HintageCost:
    capacity: float
    fixed_om: float
    ccs_retrofit: float | None


def read_fom_table(path: Path, *, required: set[str]) -> pl.DataFrame:
    """Read a required ReEDS table and validate the columns used for FOM."""
    frame = read_gams_header_csv(path).collect()
    frame = frame.rename({name: name.lower() for name in frame.columns})
    frame = frame.with_columns(pl.col(pl.String).str.to_lowercase())
    missing = required - set(frame.columns)
    if missing:
        msg = f"{path.name} is missing FOM columns: {sorted(missing)}"
        raise ValueError(msg)
    return frame


def read_fom_parameters(path: Path) -> dict[str, str]:
    """Read headerless switches/scalars without interpreting their descriptions."""
    frame = pl.read_csv(path, has_header=False, infer_schema=False)
    if frame.width < 2:
        msg = f"{path.name} must contain parameter and value columns"
        raise ValueError(msg)
    return {str(name).lower(): str(value) for name, value in frame.select(frame.columns[:2]).iter_rows()}


def prepare_fixed_om(
    capacity_data: pl.LazyFrame,
    *,
    store: DataStore,
    solve_year: int,
) -> Result[pl.LazyFrame, str]:
    """Return costs on capacity keys, preserving unknown costs as null values.

    Hydro uses nonzero regional overrides, PSH uses its scalar, distributed PV
    uses explicit hintage FOM, and upgrades follow their declared target links.
    Unit-specific CCS retrofit FOM is converted from $/kW-year to $/MW-year.
    """
    inputs = store.folder / "inputs_case"
    try:
        costs = store.read_data("cost_fom", placeholders={"solve_year": solve_year}).collect()
        if costs.is_empty():
            return Err(f"cost_fom: no FOM rows for solve year {solve_year}")
        plant = {
            str(tech): float(value) for tech, value in costs.select("technology", "fom_cost").iter_rows()
        }
        switches = read_fom_parameters(inputs / "switches.csv")
        scalars = read_fom_parameters(inputs / "scalars.csv")
        hydro = read_fom_table(inputs / "hyd_fom.csv", required={"i"})
        hydro_costs = {
            (str(tech), str(region)): float(value)
            for tech, region, value in hydro.unpivot(index="i").iter_rows()
            if value is not None
        }
        subsets = read_gams_header_csv(inputs / "tech-subset-table.csv").collect()
        subsets = subsets.rename({subsets.columns[0]: "technology"})
        subsets = subsets.rename({name: name.lower() for name in subsets.columns})
        subsets = subsets.with_columns(pl.col(pl.String).str.to_lowercase())
        psh = set(subsets.filter(pl.col("psh") == "yes")["technology"].to_list())
        dpv = set(subsets.filter(pl.col("distpv") == "yes")["technology"].to_list())
        ccs = set(subsets.filter(pl.col("ccs") == "yes")["technology"].to_list())
        links_frame = read_fom_table(inputs / "upgrade_link.csv", required={"to", "from", "delta"})
        if switches.get("gsw_watermain") == "1":
            water_links = read_fom_table(inputs / "upgradelink_water.csv", required={"to", "from", "delta"})
            links_frame = pl.concat([links_frame, water_links])
        links = {
            str(tech): UpgradeLink(source=str(source), target=str(target))
            for tech, source, target in links_frame.select("to", "from", "delta").iter_rows()
        }
        hintage = read_fom_table(
            inputs / "hintage_data.csv", required={"tech", "bin", "r", "yr", "cap", "wfom"}
        )
        histories = {
            (str(row["tech"]), str(row["bin"]), str(row["r"]), int(row["yr"])): HintageCost(
                capacity=float(row["cap"]),
                fixed_om=float(row["wfom"]),
                ccs_retrofit=float(row["wccs_retro_fom"]) if row.get("wccs_retro_fom") is not None else None,
            )
            for row in hintage.iter_rows(named=True)
        }
        keys = capacity_data.select("technology", "vintage", "region", "year").unique().collect()
        active_upgrades = set(keys["technology"].to_list()) & links.keys()
        upgrade_plant: dict[str, float] = {}
        unitspec: set[str] = set()
        if active_upgrades:
            if switches.get("gsw_upgrades") != "1":
                return Err("Active generator upgrades require GSw_Upgrades=1")
            upgrade_year = int(switches["gsw_upgradechar_year"])
            upgrade_costs = store.read_data("cost_fom", placeholders={"solve_year": upgrade_year}).collect()
            upgrade_plant = {
                str(tech): float(value)
                for tech, value in upgrade_costs.select("technology", "fom_cost").iter_rows()
            }
            if switches.get("gsw_upgradefom_nems") == "1":
                unitspec_frame = read_fom_table(inputs / "unitspec_upgrades.csv", required={"i"})
                unitspec = set(unitspec_frame["i"].to_list())
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
                            value = history.ccs_retrofit * 1000.0
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
    except (OSError, ValueError, KeyError, pl.exceptions.PolarsError) as exc:
        return Err(f"Fixed O&M source data: {exc}")
