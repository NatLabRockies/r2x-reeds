"""Fixed O&M reaches generator components from processed ReEDS inputs."""

import shutil
from pathlib import Path

import pytest

from r2x_core import DataStore, PluginContext
from r2x_reeds import ReEDSConfig, ReEDSParser
from r2x_reeds.models.components import ReEDSGenerator

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("marker", ["", "*"])
def test_fixed_om_dataset_selects_only_solve_year_fom(
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
    config = ReEDSConfig(solve_year=2032, weather_year=2012)
    store = DataStore.from_plugin_config(config, path=tmp_path)
    ReEDSParser.from_context(PluginContext(config=config, store=store))

    costs = store.read_data("cost_fom", placeholders={"solve_year": 2032}).collect()

    assert costs.to_dicts() == [
        {"technology": "gas-cc", "year": 2032, "fom_cost": 20081},
        {"technology": "wind-ons_1", "year": 2032, "fom_cost": 31000},
    ]


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
    config = ReEDSConfig(solve_year=2032, weather_year=2012, case_name="test", scenario="base")
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
