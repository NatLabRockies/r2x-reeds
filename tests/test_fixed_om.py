"""FOM source precedence through configured core datasets and ReEDS component rules."""

import json
from dataclasses import dataclass
from pathlib import Path

import polars as pl
import pytest
from rust_ok import Err, Ok, Result

from r2x_core import DataFile, DataStore, Rule, System, TabularProcessing
from r2x_core.exceptions import ReaderError
from r2x_core.utils import build_component_kwargs
from r2x_reeds import ReEDSConfig
from r2x_reeds.data_readers import configure_fom_processing
from r2x_reeds.models.components import ReEDSRegion
from r2x_reeds.parser_utils import aggregate_variable_generators, prepare_generator_inputs
from r2x_reeds.rules_helper import create_parser_context

pytestmark = pytest.mark.unit


def evaluate_fom_rule(
    capacity_data: pl.LazyFrame, *, store: DataStore, solve_year: int
) -> Result[pl.LazyFrame, str]:
    """Exercise the shipped dataset mappings, generator joins, and component rule."""
    config = ReEDSConfig(solve_year=solve_year, weather_year=2012)
    assets = config.load_config()
    system = System(name="FOM rules")
    for region in capacity_data.select("region").unique().collect()["region"]:
        system.add_component(ReEDSRegion(name=region))
    context = create_parser_context(system, config, assets["defaults"], store=store)
    record = next(rule for rule in assets["parser_rules"] if rule["name"] == "base_generator")
    rule = Rule.from_records([record])[0]
    try:
        optional_data = {}
        for name in ("cost_fom", "fom_hydro", "fom_hintage", "fom_technology_subsets", "fom_upgrade_links"):
            frame = store.read_data(name, placeholders={"solve_year": solve_year})
            if not isinstance(frame, pl.LazyFrame):
                return Err(f"Required FOM dataset {name!r} is unavailable")
            if name == "cost_fom" and frame.collect().is_empty():
                return Err(f"cost_fom: no FOM rows for solve year {solve_year}")
            optional_data[name] = frame
        # Mirror required-file validation before the normal row-to-component rule.
        for name in ("fom_unitspec_upgrades", "fom_scalars", "fom_switches"):
            store.read_data(name).collect()
        switches = dict(store.read_data("fom_switches").collect().iter_rows())
        if switches.get("gsw_watermain") == "1":
            water = store.read_data("fom_water_upgrade_links")
            if water is None:
                return Err("Required FOM dataset 'fom_water_upgrade_links' is unavailable")
            optional_data["fom_upgrade_links"] = pl.concat([optional_data["fom_upgrade_links"], water])
        if "capacity" not in capacity_data.collect_schema().names():
            capacity_data = capacity_data.with_columns(pl.lit(100.0).alias("capacity"))
        prepared = prepare_generator_inputs(
            capacity_data.with_columns(pl.lit("OTHER").alias("fuel_type")),
            optional_data=optional_data,
            excluded_technologies=[],
            technology_categories=assets["defaults"]["tech_categories"],
        )
        if prepared.is_err():
            return Err(str(prepared.err()))
        groups = prepared.ok()
        assert groups is not None
        rows = pl.concat(list(groups), how="diagonal_relaxed")
        costs: list[float | None] = []
        for row in rows.iter_rows(named=True):
            result = build_component_kwargs(row, rule=rule, context=context)
            if result.is_err():
                return Err(str(result.err()))
            fields = result.ok()
            assert fields is not None
            costs.append(fields.get("fom_cost"))
        return Ok(rows.with_columns(pl.Series("fom_cost", costs, dtype=pl.Float64)).lazy())
    except (OSError, ValueError, KeyError, ReaderError, pl.exceptions.PolarsError) as exc:
        return Err(str(exc))


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
    records = [
        item
        for item in json.loads(config.fmap_path.read_text())
        if item["name"] == "cost_fom" or item["name"].startswith("fom_")
    ]
    store = DataStore(path=tmp_path)
    store.add_data(DataFile.from_records(records, folder_path=tmp_path))
    configure_fom_processing(store)
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
    result = evaluate_fom_rule(capacity, store=fom_case.store, solve_year=2032)
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
    result = evaluate_fom_rule(capacity, store=fom_case.store, solve_year=2032)
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
    result = evaluate_fom_rule(capacity, store=fom_case.store, solve_year=2032)
    assert result.is_err()
    assert filename in str(result.err())


@pytest.mark.parametrize(
    "filename,content,technology,year,error",
    [
        ("plantcharout.csv", "*i,t,variable,value\nGas-CC,2029,fom,10\n", "gas-cc", 2032, "no FOM rows"),
        ("hyd_fom.csv", "technology,p1\nhydED,42000\n", "hyded", 2032, "fom_hydro"),
        ("scalars.csv", "cost_fom_psh\n", "pumped-hydro-flex", 2032, "fom_scalars"),
        (
            "hintage_data.csv",
            "TECH,bin,r,yr,cap,wFOM,wCCS_Retro_FOM\ndistpv,init-1,p1,2029,100,0,0\n",
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
        ("switches.csv", "GSw_WaterMain,1\n", "gas-cc", 2032, "fom_water_upgrade_links"),
    ],
)
def test_invalid_or_incomplete_sources_fail(
    fom_case: FOMCase, filename: str, content: str, technology: str, year: int, error: str
) -> None:
    (fom_case.inputs / filename).write_text(content)
    capacity = pl.LazyFrame(
        {"technology": [technology], "vintage": ["init-1"], "region": ["p1"], "year": [year]}
    )
    result = evaluate_fom_rule(capacity, store=fom_case.store, solve_year=year)
    assert result.is_err()
    assert error in str(result.err())


@pytest.mark.parametrize(
    "dataset,columns",
    [
        ("cost_fom", ["technology", "year", "fom_cost"]),
        ("fom_hydro", ["technology", "region", "hydro_fom_cost"]),
        ("fom_scalars", ["parameter", "value"]),
        ("fom_switches", ["parameter", "value"]),
        ("fom_technology_subsets", ["technology", "psh", "distpv", "ccs"]),
        ("fom_upgrade_links", ["technology", "source_technology", "target_technology"]),
        ("fom_unitspec_upgrades", ["technology"]),
        (
            "fom_hintage",
            [
                "technology",
                "vintage",
                "region",
                "year",
                "hintage_capacity",
                "hintage_fom_cost",
                "ccs_retrofit_fom",
            ],
        ),
    ],
)
def test_core_configuration_reads_and_processes_fom_sources(
    fom_case: FOMCase, dataset: str, columns: list[str]
) -> None:
    data_file = fom_case.store[dataset]
    assert data_file.reader is None or data_file.reader.function is None
    frame = fom_case.store.read_data(dataset, placeholders={"solve_year": 2032}).collect()
    assert frame.columns == columns
    assert not frame.is_empty()
    if "fom_cost" in frame.columns:
        assert frame.schema["fom_cost"] == pl.Float64
    if dataset == "fom_hydro":
        assert frame.to_dicts() == [
            {"technology": "hyded", "region": "p1", "hydro_fom_cost": 42000.0},
            {"technology": "hyded", "region": "p2", "hydro_fom_cost": 0.0},
        ]
    if dataset == "fom_hintage":
        assert frame.filter((pl.col("technology") == "coalolduns") & (pl.col("year") == 2032))[
            "ccs_retrofit_fom"
        ].to_list() == [55000.0]


def test_fom_resolution_uses_the_context_store_source_override(fom_case: FOMCase, tmp_path: Path) -> None:
    alternate = tmp_path / "alternate-scalars.csv"
    alternate.write_text("cost_fom_psh,777,2004$/MW/year\n")
    fom_case.store.add_data(
        [fom_case.store["fom_scalars"].model_copy(update={"fpath": alternate})], overwrite=True
    )
    capacity = pl.LazyFrame(
        {"technology": ["pumped-hydro-flex"], "vintage": ["init-1"], "region": ["p1"], "year": [2032]}
    )
    result = evaluate_fom_rule(capacity, store=fom_case.store, solve_year=2032)
    assert result.is_ok(), result
    frame = result.ok()
    assert frame is not None
    assert frame.collect()["fom_cost"].to_list() == [777.0]


def test_core_hydro_unpivot_uses_the_configured_run_region_columns(fom_case: FOMCase, tmp_path: Path) -> None:
    alternate = tmp_path / "alternate-hydro.csv"
    alternate.write_text("*i,z999\nhydED,888\n")
    data_file = fom_case.store["fom_hydro"]
    processing = data_file.proc_spec
    assert isinstance(processing, TabularProcessing)
    fom_case.store.add_data(
        [
            data_file.model_copy(
                update={
                    "fpath": alternate,
                    "proc_spec": processing.model_copy(update={"unpivot_on": []}),
                }
            )
        ],
        overwrite=True,
    )
    configure_fom_processing(fom_case.store)
    frame = fom_case.store.read_data("fom_hydro").collect()
    assert frame.to_dicts() == [{"technology": "hyded", "region": "z999", "hydro_fom_cost": 888.0}]


def test_empty_upgrade_sets_are_valid_configured_inputs(fom_case: FOMCase) -> None:
    (fom_case.inputs / "upgrade_link.csv").write_text("*TO,FROM,DELTA\n")
    (fom_case.inputs / "unitspec_upgrades.csv").write_text("*i\n")
    capacity = pl.LazyFrame(
        {"technology": ["gas-cc"], "vintage": ["init-1"], "region": ["p1"], "year": [2032]}
    )
    result = evaluate_fom_rule(capacity, store=fom_case.store, solve_year=2032)
    assert result.is_ok(), result
    frame = result.ok()
    assert frame is not None
    assert frame.collect()["fom_cost"].to_list() == [20081.0]


def test_hydro_configuration_requires_region_columns(fom_case: FOMCase) -> None:
    (fom_case.inputs / "hyd_fom.csv").write_text("*i\nhydED\n")
    data_file = fom_case.store["fom_hydro"]
    processing = data_file.proc_spec
    assert isinstance(processing, TabularProcessing)
    fom_case.store.add_data(
        [data_file.model_copy(update={"proc_spec": processing.model_copy(update={"unpivot_on": []})})],
        overwrite=True,
    )
    with pytest.raises(ValueError, match="no region columns"):
        configure_fom_processing(fom_case.store)
