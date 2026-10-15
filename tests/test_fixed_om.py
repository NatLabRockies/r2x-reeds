"""Source precedence and validation through the public FOM preparation API."""

import json
from dataclasses import dataclass
from pathlib import Path

import polars as pl
import pytest

from r2x_core import DataFile, DataStore
from r2x_reeds import ReEDSConfig
from r2x_reeds.data_readers import register_gams_header_readers
from r2x_reeds.fixed_om import prepare_fixed_om
from r2x_reeds.parser_utils import aggregate_variable_generators

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("costs,expected", [([10.0, 30.0], 25.0), ([10.0, None], None)])
def test_renewable_fom_preserves_annual_cost_and_unknowns(
    costs: list[float | None], expected: float | None
) -> None:
    generators = pl.DataFrame(
        {
            "technology": ["wind-ons_1", "wind-ons_1"],
            "region": ["p1", "p1"],
            "category": ["wind", "wind"],
            "categories": [["wind"], ["wind"]],
            "capacity": [100.0, 300.0],
            "fom_cost": costs,
        }
    )
    result = aggregate_variable_generators(generators)
    assert result["capacity"].to_list() == [400.0]
    assert result["fom_cost"].to_list() == [expected]
    if expected is not None:
        assert result["capacity"][0] * result["fom_cost"][0] == 10000.0


@dataclass(frozen=True)
class FOMCase:
    store: DataStore
    inputs: Path


@pytest.fixture
def fom_case(tmp_path: Path) -> FOMCase:
    inputs = tmp_path / "inputs_case"
    inputs.mkdir()
    (inputs / "plantcharout.csv").write_text(
        "*i,t,variable,value\n"
        "Gas-CC,2032,fom,20081\n"
        "hydED,2032,fom,1000\n"
        "coal-ccs_mod,2028,fom,45000\n"
        "coal-ccs_mod,2032,fom,46000\n"
    )
    (inputs / "hyd_fom.csv").write_text("i,p1,p2\nhydED,42000,0\n")
    (inputs / "scalars.csv").write_text("cost_fom_psh,13030,2004$/MW-year\n")
    (inputs / "switches.csv").write_text(
        "GSw_Upgrades,1\nGSw_UpgradeChar_Year,2028\nGSw_UpgradeFOM_Nems,1\n"
        "GSw_UpgradeYear,2028\nGSw_WaterMain,0\nGSw_BinOM,1\n"
    )
    (inputs / "tech-subset-table.csv").write_text(
        ",HYDRO,PSH,distpv,CCS\nhydED,YES,,,\npumped-hydro-flex,,YES,,\ndistpv,,,YES,\ncoal-ccs_mod,,,,YES\n"
    )
    (inputs / "upgrade_link.csv").write_text(
        "*TO,FROM,DELTA\nCoalOldUns_Coal-CCS_mod,CoalOldUns,coal-ccs_mod\n"
    )
    (inputs / "unitspec_upgrades.csv").write_text("*i\nCoalOldUns_Coal-CCS_mod\n")
    (inputs / "hintage_data.csv").write_text(
        "TECH,bin,r,yr,cap,wFOM,wCCS_Retro_FOM\n"
        "distpv,init-1,p1,2032,100,0,0\n"
        "CoalOldUns,init-1,p1,2028,100,50000,66\n"
        "CoalOldUns,init-1,p1,2032,100,50000,55\n"
    )
    config = ReEDSConfig(solve_year=2032, weather_year=2012)
    record = next(item for item in json.loads(config.fmap_path.read_text()) if item["name"] == "cost_fom")
    store = DataStore(path=tmp_path)
    store.add_data(DataFile.from_records([record], folder_path=tmp_path))
    register_gams_header_readers(store)
    return FOMCase(store=store, inputs=inputs)


@pytest.mark.parametrize(
    "technology,vintage,region,expected",
    [
        ("gas-cc", "init-1", "p1", 20081),
        ("hyded", "init-1", "p1", 42000),
        ("hyded", "init-1", "p2", 1000),
        ("pumped-hydro-flex", "init-1", "p1", 13030),
        ("distpv", "init-1", "p1", 0),
        ("coalolduns_coal-ccs_mod", "init-1", "p1", 55000),
        ("coalolduns_coal-ccs_mod", "new1", "p1", 46000),
        ("unknown", "new1", "p1", None),
    ],
)
def test_source_precedence(
    fom_case: FOMCase, technology: str, vintage: str, region: str, expected: float | None
) -> None:
    capacity = pl.LazyFrame(
        {"technology": [technology], "vintage": [vintage], "region": [region], "year": [2032]}
    )
    result = prepare_fixed_om(capacity, store=fom_case.store, solve_year=2032)
    assert result.is_ok(), result
    costs = result.ok()
    assert costs is not None
    assert costs.collect()["fom_cost"].to_list() == [expected]


@pytest.mark.parametrize("retrofit", [False, True])
def test_initial_upgrades_use_characteristic_year_or_extended_unit_cost(
    fom_case: FOMCase, retrofit: bool
) -> None:
    if retrofit:
        path = fom_case.inputs / "hintage_data.csv"
        frame = pl.read_csv(path).filter(pl.col("yr") != 2032)
        frame.write_csv(path)
    else:
        path = fom_case.inputs / "switches.csv"
        path.write_text(path.read_text().replace("GSw_UpgradeFOM_Nems,1", "GSw_UpgradeFOM_Nems,0"))
    capacity = pl.LazyFrame(
        {"technology": ["coalolduns_coal-ccs_mod"], "vintage": ["init-1"], "region": ["p1"], "year": [2032]}
    )
    result = prepare_fixed_om(capacity, store=fom_case.store, solve_year=2032)
    assert result.is_ok(), result
    costs = result.ok()
    assert costs is not None
    assert costs.collect()["fom_cost"].to_list() == [66000.0 if retrofit else 45000.0]


@pytest.mark.parametrize(
    "filename",
    [
        "plantcharout.csv",
        "switches.csv",
        "scalars.csv",
        "hyd_fom.csv",
        "hintage_data.csv",
        "tech-subset-table.csv",
        "upgrade_link.csv",
        "unitspec_upgrades.csv",
    ],
)
def test_missing_required_sources_fail(fom_case: FOMCase, filename: str) -> None:
    (fom_case.inputs / filename).unlink()
    capacity = pl.LazyFrame(
        {"technology": ["coalolduns_coal-ccs_mod"], "vintage": ["init-1"], "region": ["p1"], "year": [2032]}
    )
    result = prepare_fixed_om(capacity, store=fom_case.store, solve_year=2032)
    assert result.is_err()
    assert filename in str(result.err())


@pytest.mark.parametrize(
    "filename,content,technology,year,error",
    [
        ("plantcharout.csv", "*i,t,variable,value\nGas-CC,2029,fom,10\n", "gas-cc", 2032, "no FOM rows"),
        ("hyd_fom.csv", "technology,p1\nhydED,42000\n", "hyded", 2032, "missing FOM columns"),
        ("scalars.csv", "cost_fom_psh\n", "pumped-hydro-flex", 2032, "parameter and value"),
        (
            "hintage_data.csv",
            "TECH,bin,r,yr,cap,wFOM\ndistpv,init-1,p1,2029,100,0\n",
            "distpv",
            2032,
            "distributed-PV",
        ),
        (
            "plantcharout.csv",
            "*i,t,variable,value\nGas-CC,2032,fom,10\n",
            "coalolduns_coal-ccs_mod",
            2032,
            "upgrade target",
        ),
        (
            "switches.csv",
            "GSw_Upgrades,0\nGSw_WaterMain,0\n",
            "coalolduns_coal-ccs_mod",
            2032,
            "GSw_Upgrades=1",
        ),
    ],
)
def test_invalid_or_incomplete_sources_fail(
    fom_case: FOMCase, filename: str, content: str, technology: str, year: int, error: str
) -> None:
    (fom_case.inputs / filename).write_text(content)
    capacity = pl.LazyFrame(
        {"technology": [technology], "vintage": ["init-1"], "region": ["p1"], "year": [year]}
    )
    result = prepare_fixed_om(capacity, store=fom_case.store, solve_year=year)
    assert result.is_err()
    assert error in str(result.err())
