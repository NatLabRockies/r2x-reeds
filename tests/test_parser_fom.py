"""Fixed O&M reaches generator components from processed ReEDS inputs."""

import copy
import shutil
from pathlib import Path

import polars as pl
import pytest

from r2x_core import DataStore, PluginContext
from r2x_reeds import ReEDSConfig, ReEDSParser
from r2x_reeds.models.components import ReEDSGenerator
from tests.fixtures.data_fixtures import csv_file_mapping

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "dataset,header",
    [
        ("fom_upgrade_links", "*TO,FROM,DELTA\n"),
        ("fom_unitspec_upgrades", "*i\n"),
    ],
)
@pytest.mark.parametrize("missing", [False, True])
def test_required_fom_sets_may_be_empty_but_must_exist(
    reeds_run_path: Path, tmp_path: Path, dataset: str, header: str, missing: bool
) -> None:
    shutil.copytree(reeds_run_path, tmp_path, dirs_exist_ok=True)
    config = ReEDSConfig(
        solve_year=2032,
        weather_year=2012,
        asset_overrides={"file_mapping": csv_file_mapping()},
    )
    store = DataStore.from_plugin_config(config, path=tmp_path)
    parser = ReEDSParser.from_context(PluginContext(config=config, store=store))
    path = store[dataset].fpath
    assert path is not None
    path = path if path.is_absolute() else tmp_path / path
    if missing:
        path.unlink()
    else:
        path.write_text(header)
    result = parser.on_validate()
    if missing:
        assert result.is_err()
        assert dataset in str(result.err())
    else:
        assert result.is_ok(), result


@pytest.mark.parametrize("source", ["missing", "empty"])
def test_fixed_om_requires_a_nonempty_physical_source(
    reeds_run_path: Path, tmp_path: Path, source: str
) -> None:
    shutil.copytree(reeds_run_path, tmp_path, dirs_exist_ok=True)
    path = tmp_path / "inputs_case" / "plantcharout.csv"
    path.write_text("*i,t,variable,value\nGas-CC,2032,fom,20081\n")
    config = ReEDSConfig(
        solve_year=2032,
        weather_year=2012,
        asset_overrides={"file_mapping": csv_file_mapping()},
    )
    store = DataStore.from_plugin_config(config, path=tmp_path)
    parser = ReEDSParser.from_context(PluginContext(config=config, store=store))
    if source == "missing":
        path.unlink()
    elif source == "empty":
        path.write_text("*i,t,variable,value\n")

    result = parser.on_validate()

    assert result.is_err()
    assert "cost_fom" in str(result.err())


@pytest.mark.parametrize("marker", ["", "*"])
def test_fixed_om_dataset_preserves_all_characteristic_years(
    reeds_run_path: Path, tmp_path: Path, marker: str
) -> None:
    shutil.copytree(reeds_run_path, tmp_path, dirs_exist_ok=True)
    inputs = tmp_path / "inputs_case"
    (inputs / "plantcharout.csv").write_text(
        f"{marker}i,t,variable,value\n"
        "Gas-CC,2032,fom,20081\n"
        "Gas-CC,2029,fom,99999\n"
        "Gas-CC,2032,capcost,736901\n"
        "wind-ons_1,2032,fom,31000\n"
    )
    config = ReEDSConfig(
        solve_year=2032,
        weather_year=2012,
        asset_overrides={"file_mapping": csv_file_mapping()},
    )
    store = DataStore.from_plugin_config(config, path=tmp_path)
    ReEDSParser.from_context(PluginContext(config=config, store=store))

    costs = store.read_data("cost_fom").collect()

    assert costs.to_dicts() == [
        {"technology": "gas-cc", "year": 2032, "fom_cost": 20081},
        {"technology": "gas-cc", "year": 2029, "fom_cost": 99999},
        {"technology": "wind-ons_1", "year": 2032, "fom_cost": 31000},
    ]


def test_fom_recipe_reads_its_configured_physical_cost_source(reeds_run_path: Path, tmp_path: Path) -> None:
    """Changing the configured physical FOM source changes constructed components."""
    run_path = tmp_path / "run"
    shutil.copytree(reeds_run_path, run_path)
    inputs = run_path / "inputs_case"
    (inputs / "plantcharout.csv").write_text("*i,t,variable,value\nGas-CC,2032,fom,20081\n")
    alternate_path = "inputs_case/alternate_plantcharout.csv"
    (run_path / alternate_path).write_text("*i,t,variable,value\nGas-CC,2032,fom,43210\n")

    file_mapping = csv_file_mapping()
    alternate = copy.deepcopy(next(item for item in file_mapping["files"] if item["name"] == "cost_fom"))
    alternate.update(name="alternate_cost_fom", fpath=alternate_path)
    alternate["info"]["is_input"] = False
    file_mapping["files"].append(alternate)
    fom_table = next(item for item in file_mapping["tables"] if item["name"] == "generator_fom_policy")
    cost_joins = [join for join in fom_table["joins"] if join["source"] == "cost_fom"]
    for join in cost_joins:
        join["source"] = "alternate_cost_fom"

    config = ReEDSConfig(
        solve_year=2032,
        weather_year=2012,
        asset_overrides={"file_mapping": file_mapping},
    )
    store = DataStore.from_plugin_config(config, path=run_path)
    context = PluginContext(config=config, store=store)
    result = ReEDSParser.from_context(context).run(ctx=context)

    assert result.system is not None
    generators = [
        generator
        for generator in result.system.get_components(ReEDSGenerator)
        if generator.technology == "gas-cc"
    ]
    assert generators
    assert {generator.fom_cost for generator in generators} == {43210.0}


def test_generators_receive_solve_year_fixed_om(reeds_run_path: Path, tmp_path: Path) -> None:
    run_path = tmp_path / "run"
    shutil.copytree(reeds_run_path, run_path)
    # plantcharout is already deflated to 2004 dollars and converted to MW.
    (run_path / "inputs_case" / "plantcharout.csv").write_text(
        "*i,t,variable,value\n"
        "Gas-CC,2032,fom,20081\n"
        "Gas-CC,2029,fom,99999\n"
        "Gas-CC,2032,capcost,736901\n"
        "wind-ons_1,2032,fom,31000\n"
        "upv_1,2032,fom,12000\n"
        "battery_4,2032,fom,0\n"
    )
    config = ReEDSConfig(
        solve_year=2032,
        weather_year=2012,
        case_name="test",
        scenario="base",
        asset_overrides={"file_mapping": csv_file_mapping()},
    )
    store = DataStore.from_plugin_config(config, path=run_path)
    ctx = PluginContext(config=config, store=store)
    parser = ReEDSParser.from_context(ctx)
    result = parser.run(ctx=ctx)
    assert result.system is not None

    expected_costs = {"gas-cc": 20081.0, "wind-ons_1": 31000.0, "upv_1": 12000.0, "battery_4": 0.0}
    generators = list(result.system.get_components(ReEDSGenerator))
    for technology, expected in expected_costs.items():
        matched = [generator for generator in generators if generator.technology == technology]
        assert matched, technology
        assert all(generator.fom_cost == expected for generator in matched), technology

    unmatched = [generator for generator in generators if generator.technology == "gas-ct"]
    assert unmatched
    assert all(generator.fom_cost is None for generator in unmatched)


def test_fom_policy_configuration_controls_selection(reeds_run_path: Path, tmp_path: Path) -> None:
    run_path = tmp_path / "run"
    shutil.copytree(reeds_run_path, run_path)
    inputs = run_path / "inputs_case"
    (inputs / "plantcharout.csv").write_text(
        "*i,t,variable,value\n"
        "Gas-CC,2032,fom,20081\n"
        "coal-ccs_mod,2028,fom,45000\n"
        "coal-ccs_mod,2032,fom,46000\n"
    )
    hydro = pl.read_csv(inputs / "hyd_fom.csv")
    hydro.with_columns(pl.lit(42000.0).alias(column) for column in hydro.columns if column != "i").write_csv(
        inputs / "hyd_fom.csv"
    )
    (inputs / "scalars.csv").write_text("cost_fom_psh,13030,2004$/MW-year\n")

    mapping = csv_file_mapping()
    table = next(item for item in mapping["tables"] if item["name"] == "generator_fom_policy")
    assignments = table["proc_spec"]["conditional_assignments"]
    psh_assignment = next(item for item in assignments if item["when"][0]["column"] == "psh")
    psh_assignment["value_source"] = {"kind": "literal", "value": 54321.0}

    config = ReEDSConfig(
        solve_year=2032,
        weather_year=2012,
        asset_overrides={"file_mapping": mapping},
    )
    store = DataStore.from_plugin_config(config, path=run_path)
    ctx = PluginContext(config=config, store=store)
    result = ReEDSParser.from_context(ctx).run(ctx=ctx)
    assert result.system is not None

    pumped_hydro = [
        generator
        for generator in result.system.get_components(ReEDSGenerator)
        if generator.technology == "pumped-hydro"
    ]
    assert pumped_hydro
    assert {generator.fom_cost for generator in pumped_hydro} == {54321.0}


@pytest.mark.parametrize(
    "retrofit_mode,initial_cost", [("current", 55000.0), ("disabled", 45000.0), ("carry", 66000.0)]
)
def test_hydro_storage_dpv_and_upgrades_receive_their_source_costs(
    reeds_run_path: Path, tmp_path: Path, retrofit_mode: str, initial_cost: float
) -> None:
    shutil.copytree(reeds_run_path, tmp_path, dirs_exist_ok=True)
    inputs = tmp_path / "inputs_case"
    (inputs / "plantcharout.csv").write_text(
        "*i,t,variable,value\n"
        "Gas-CC,2032,fom,20081\n"
        "coal-ccs_mod,2028,fom,45000\n"
        "coal-ccs_mod,2032,fom,46000\n"
    )
    hydro = pl.read_csv(inputs / "hyd_fom.csv")
    hydro.with_columns(pl.lit(42000.0).alias(column) for column in hydro.columns if column != "i").write_csv(
        inputs / "hyd_fom.csv"
    )
    (inputs / "scalars.csv").write_text("cost_fom_psh,13030,2004$/MW-year\n")
    switches = inputs / "switches.csv"
    if retrofit_mode == "disabled":
        switches.write_text(switches.read_text().replace("GSw_UpgradeFOM_Nems,1", "GSw_UpgradeFOM_Nems,0"))
    hintage = pl.read_csv(inputs / "hintage_data.csv")
    retrofit = pl.DataFrame(
        {
            "TECH": ["CoalOldUns", "CoalOldUns"],
            "bin": ["init-1", "init-1"],
            "r": ["p1", "p1"],
            "yr": [2028, 2032],
            "cap": [100.0, 100.0],
            "wFOM": [50000.0, 50000.0],
            "wCCS_Retro_FOM": [66.0, 0.0 if retrofit_mode == "carry" else 55.0],
        }
    )
    pl.concat([hintage, retrofit], how="diagonal_relaxed").write_csv(inputs / "hintage_data.csv")
    (inputs / "upgrade_link.csv").write_text(
        "*TO,FROM,DELTA\nCoalOldUns_Coal-CCS_mod,CoalOldUns,coal-ccs_mod\n"
    )
    with (tmp_path / "outputs" / "cap_ivrt.csv").open("a") as file:
        file.write("CoalOldUns_Coal-CCS_mod,init-1,p1,2032,100\n")
        file.write("CoalOldUns_Coal-CCS_mod,new1,p1,2032,100\n")
    config = ReEDSConfig(
        solve_year=2032,
        weather_year=2012,
        asset_overrides={"file_mapping": csv_file_mapping()},
    )
    store = DataStore.from_plugin_config(config, path=tmp_path)
    ctx = PluginContext(config=config, store=store)
    result = ReEDSParser.from_context(ctx).run(ctx=ctx)
    assert result.system is not None
    generators = list(result.system.get_components(ReEDSGenerator))
    expected = {"hyded": 42000.0, "pumped-hydro": 13030.0, "distpv": 0.0}
    for technology, cost in expected.items():
        matched = [generator for generator in generators if generator.technology == technology]
        if technology == "distpv":
            matched = [generator for generator in matched if generator.region.name == "p1"]
        assert matched, technology
        assert all(generator.fom_cost == cost for generator in matched), technology
    upgrades = [generator for generator in generators if generator.technology == "coalolduns_coal-ccs_mod"]
    assert {generator.vintage: generator.fom_cost for generator in upgrades} == {
        "init-1": initial_cost,
        "new1": 46000.0,
    }


def test_variable_fom_aggregation_preserves_annual_cost(
    reeds_run_path: Path, tmp_path: Path, reeds_config: ReEDSConfig
) -> None:
    """Configured grouping uses capacity-weighted FOM before component mapping."""
    run_path = tmp_path / "run"
    shutil.copytree(reeds_run_path, run_path)
    (run_path / "outputs" / "cap_ivrt.csv").write_text(
        "i,v,r,t,Value\ndistpv,init-1,p1,2032,100\ndistpv,new1,p1,2032,300\n"
    )
    hintage_path = run_path / "inputs_case" / "hintage_data.csv"
    hintage = pl.read_csv(hintage_path)
    controlled = (
        (pl.col("TECH").str.to_lowercase() == "distpv") & (pl.col("r") == "p1") & (pl.col("yr") == 2032)
    ).fill_null(False)
    hintage = hintage.filter(~controlled)
    rates = pl.DataFrame(
        {
            "TECH": ["distpv", "distpv"],
            "bin": ["init-1", "new1"],
            "r": ["p1", "p1"],
            "yr": [2032, 2032],
            "cap": [100.0, 300.0],
            "wFOM": [10.0, 30.0],
            "wCCS_Retro_FOM": [0.0, 0.0],
        }
    )
    pl.concat([hintage, rates], how="diagonal_relaxed").write_csv(hintage_path)

    defaults = reeds_config.load_config()["defaults"]
    defaults["reserve_products"] = []
    parser_rules = copy.deepcopy(reeds_config.load_config()["parser_rules"])
    next(stage for stage in parser_rules["execution"] if stage["name"] == "resources")["rules"] = []
    config = reeds_config.model_copy(
        update={
            "asset_overrides": {
                **reeds_config.asset_overrides,
                "defaults": defaults,
                "parser_rules": parser_rules,
            }
        }
    )
    store = DataStore.from_plugin_config(config, path=run_path)
    context = PluginContext(config=config, store=store)
    result = ReEDSParser.from_context(context).run(ctx=context)

    assert result.system is not None
    generators = list(result.system.get_components(ReEDSGenerator))
    assert len(generators) == 1
    assert generators[0].capacity == 400.0
    assert generators[0].fom_cost == pytest.approx(25.0)
    assert generators[0].capacity * generators[0].fom_cost == pytest.approx(10_000.0)
