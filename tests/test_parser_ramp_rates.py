"""ReEDS CSV ramp rates reach generator objects without capacity or time scaling."""

import json
import shutil
from importlib.resources import files

import pytest

from r2x_core import DataStore, PluginContext
from r2x_reeds import ReEDSConfig, ReEDSParser
from r2x_reeds.models import ReEDSGenerator, ReEDSHydroGenerator, ReEDSThermalGenerator
from r2x_reeds.sysmod.pcm_defaults import PCMDefaultsConfig, add_pcm_defaults

pytestmark = pytest.mark.integration


def test_parser_and_pcm_defaults_share_fraction_per_minute(reeds_run_path, tmp_path):
    run_path = tmp_path / "run"
    shutil.copytree(reeds_run_path, run_path)
    (run_path / "inputs_case" / "ramprate.csv").write_text("Gas-CC,0.05\nGas-CT,0.08\n")
    config = ReEDSConfig(solve_year=2032, weather_year=2012, case_name="test", scenario="base")
    store = DataStore.from_plugin_config(config, path=run_path)
    context = PluginContext(config=config, store=store)
    parser = ReEDSParser.from_context(context)

    data = parser.read_data_file("ramprate").collect()
    assert dict(data.iter_rows()) == {"gas-cc": 0.05, "gas-ct": 0.08}
    mappings = json.loads(files("r2x_reeds.config").joinpath("file_mapping.json").read_text())
    ramp_mapping = next(mapping for mapping in mappings if mapping["name"] == "ramprate")
    assert ramp_mapping["info"]["units"] == "fraction/min"

    result = parser.run(ctx=context)
    assert result.system is not None
    defaults = PCMDefaultsConfig(
        pcm_defaults_dict={"gas-cc": {"ramp_rate": 0.05}, "gas-ct": {"ramp_rate": 0.08}}
    )
    for technology, expected in [("gas-cc", 0.05), ("gas-ct", 0.08)]:
        generators = [
            generator
            for generator in result.system.get_components(ReEDSThermalGenerator)
            if generator.technology == technology
        ]
        assert generators, technology
        assert all(generator.ramp_rate == pytest.approx(expected) for generator in generators)
        for generator in generators:
            generator.ramp_rate = None
        add_pcm_defaults(result.system, defaults).unwrap()
        assert all(generator.ramp_rate == pytest.approx(expected) for generator in generators)


@pytest.mark.parametrize("water_mode", [False, True])
@pytest.mark.parametrize("water_switch", [False, True])
def test_upgrade_inputs_and_water_switch_control_generator_ramp_rates(
    reeds_run_path, tmp_path, water_mode, water_switch
):
    run_path = tmp_path / "run"
    shutil.copytree(reeds_run_path, run_path)
    inputs = run_path / "inputs_case"
    switches = inputs / "switches.csv"
    rows = [row.split(",", 1) for row in switches.read_text().splitlines()]
    assert any(key.casefold() == "gsw_watermain" for key, _ in rows)
    switches.write_text(
        "".join(
            f"{key},{int(water_switch) if key.casefold() == 'gsw_watermain' else value}\n"
            for key, value in rows
        )
    )
    header = "*TO,FROM,DELTA\n"
    relationships = "Gas-CC_H2-CC,Gas-CC,H2-CC\nCoalOldUns_Coal-CCS_mod,CoalOldUns,coal-ccs_mod\n"
    (inputs / "upgrade_link.csv").write_text(header + ("" if water_mode else relationships))
    (inputs / "upgradelink_water.csv").write_text(header + (relationships if water_mode else ""))
    (inputs / "ramprate.csv").write_text("H2-CC,0.08\ncoal-ccs_mod,0.02\nHydro,1.0\n")
    with (run_path / "outputs" / "cap_ivrt.csv").open("a") as file:
        file.write("Gas-CC_H2-CC,new1,p1,2032,100\n")
        file.write("CoalOldUns_Coal-CCS_mod,new1,p1,2032,100\n")

    config = ReEDSConfig(solve_year=2032, weather_year=2012)
    store = DataStore.from_plugin_config(config, path=run_path)
    context = PluginContext(config=config, store=store)
    result = ReEDSParser.from_context(context).run(ctx=context)
    assert result.system is not None
    generators = list(result.system.get_components(ReEDSGenerator))
    for technology, rate in [("gas-cc_h2-cc", 0.08), ("coalolduns_coal-ccs_mod", 0.02)]:
        matched = [generator for generator in generators if generator.technology == technology]
        assert matched, technology
        assert all(isinstance(generator, ReEDSThermalGenerator) for generator in matched)
        expected = rate if not water_mode or water_switch else None
        assert all(generator.ramp_rate == expected for generator in matched)

    hydro = [generator for generator in generators if generator.technology == "hyded"]
    assert hydro
    assert all(isinstance(generator, ReEDSHydroGenerator) for generator in hydro)
    assert all(generator.ramp_rate == 1.0 for generator in hydro)
    nondispatchable = [generator for generator in generators if generator.technology == "hydnd"]
    assert nondispatchable
    assert all(isinstance(generator, ReEDSHydroGenerator) for generator in nondispatchable)
    assert all(generator.ramp_rate is None for generator in nondispatchable)


@pytest.mark.parametrize("missing_file", [False, True])
def test_parser_preserves_missing_rates_and_pcm_only_fills_nulls(reeds_run_path, tmp_path, missing_file):
    run_path = tmp_path / "run"
    shutil.copytree(reeds_run_path, run_path)
    ramp_path = run_path / "inputs_case" / "ramprate.csv"
    if missing_file:
        if ramp_path.exists():
            ramp_path.unlink()
    else:
        ramp_path.write_text("Gas-CC,0.08\n")
    config = ReEDSConfig(solve_year=2032, weather_year=2012)
    store = DataStore.from_plugin_config(config, path=run_path)
    context = PluginContext(config=config, store=store)
    result = ReEDSParser.from_context(context).run(ctx=context)
    assert result.system is not None
    generators = list(result.system.get_components(ReEDSGenerator))
    selected = {
        technology: [generator for generator in generators if generator.technology == technology]
        for technology in ("gas-cc", "gas-ct", "hyded")
    }
    for technology, matched in selected.items():
        assert matched, technology
        expected = 0.08 if technology == "gas-cc" and not missing_file else None
        assert all(generator.ramp_rate == expected for generator in matched)
    add_pcm_defaults(
        result.system,
        PCMDefaultsConfig(
            pcm_defaults_override=False,
            pcm_defaults_dict={
                "gas-cc": {"ramp_rate": 0.05},
                "gas-ct": {"ramp_rate": 0.1},
            },
        ),
    ).unwrap()

    for technology, expected in [
        ("gas-cc", 0.05 if missing_file else 0.08),
        ("gas-ct", 0.1),
        ("hyded", None),
    ]:
        assert all(generator.ramp_rate == expected for generator in selected[technology])
