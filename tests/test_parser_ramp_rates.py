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


def set_water_switch(inputs, enabled):
    switches = inputs / "switches.csv"
    rows = [row.split(",", 1) for row in switches.read_text().splitlines()]
    assert any(key.casefold() == "gsw_watermain" for key, _ in rows)
    switches.write_text(
        "".join(
            f"{key},{int(enabled) if key.casefold() == 'gsw_watermain' else value}\n" for key, value in rows
        )
    )


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
    set_water_switch(inputs, water_switch)
    header = "*TO,FROM,DELTA\n"
    relationships = "Gas-CC_H2-CC,Gas-CC,H2-CC\nCoalOldUns_Coal-CCS_mod,CoalOldUns,coal-ccs_mod\n"
    (inputs / "upgrade_link.csv").write_text(header + ("" if water_mode else relationships))
    (inputs / "upgradelink_water.csv").write_text(header + (relationships if water_mode else ""))
    if water_switch:
        (inputs / "i_coolingtech_watersource_link.csv").write_text(
            "*i,ii,ctt,wst\ngas-CC_r_fsa,gas-CC,r,fsa\n"
        )
        (inputs / "i_coolingtech_watersource_upgrades_link.csv").write_text(
            "*i,ii,ctt,wst\ngas-CC_r_fsa_H2-CC,Gas-CC_H2-CC,r,fsa\n"
        )
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
        expected = rate if not water_mode or water_switch else None
        for generator in matched:
            assert isinstance(generator, ReEDSThermalGenerator)
            assert generator.ramp_rate == expected

    hydro = [generator for generator in generators if generator.technology == "hyded"]
    assert hydro
    for generator in hydro:
        assert isinstance(generator, ReEDSHydroGenerator)
        assert generator.ramp_rate == 1.0
    nondispatchable = [generator for generator in generators if generator.technology == "hydnd"]
    assert nondispatchable
    for generator in nondispatchable:
        assert isinstance(generator, ReEDSHydroGenerator)
        assert generator.ramp_rate is None


@pytest.mark.parametrize("water_switch", [False, True])
def test_real_cooling_names_reach_generators_with_destination_precedence(
    reeds_run_path, tmp_path, water_switch
):
    run_path = tmp_path / "run"
    shutil.copytree(reeds_run_path, run_path)
    inputs = run_path / "inputs_case"
    set_water_switch(inputs, water_switch)
    technologies = {
        "gas-CC_r_fsa": 0.05,
        "gas-CC_r_fsa_H2-CC": 0.08,
        "CoalOldUns_r_fsa_coal-CCS_mod_r_fsa": 0.02,
        "gas-CC_r_fsa_Gas-CC-CCS_mod_r_fsa": 0.05,
    }
    (inputs / "upgradelink_water.csv").write_text(
        "*TO-WATER,FROM-WATER,DELTA-WATER\n"
        "gas-CC_r_fsa_H2-CC,gas-CC_r_fsa,H2-CC\n"
        "CoalOldUns_r_fsa_coal-CCS_mod_r_fsa,CoalOldUns_r_fsa,coal-CCS_mod_r_fsa\n"
        "gas-CC_r_fsa_Gas-CC-CCS_mod_r_fsa,gas-CC_r_fsa,Gas-CC-CCS_mod_r_fsa\n"
    )
    (inputs / "i_coolingtech_watersource_link.csv").write_text(
        "*i,ii,ctt,wst\n"
        "gas-CC_r_fsa,gas-CC,r,fsa\n"
        "coal-CCS_mod_r_fsa,coal-CCS_mod,r,fsa\n"
        "Gas-CC-CCS_mod_r_fsa,Gas-CC-CCS_mod,r,fsa\n"
    )
    (inputs / "i_coolingtech_watersource_upgrades_link.csv").write_text(
        "*i,ii,ctt,wst\n"
        "gas-CC_r_fsa_H2-CC,Gas-CC_H2-CC,r,fsa\n"
        "CoalOldUns_r_fsa_coal-CCS_mod_r_fsa,CoalOldUns_coal-CCS_mod,r,fsa\n"
        "gas-CC_r_fsa_Gas-CC-CCS_mod_r_fsa,gas-CC_Gas-CC-CCS_mod,r,fsa\n"
    )
    (inputs / "ramprate.csv").write_text(
        "gas-CC,0.05\nH2-CC,0.08\ncoal-CCS_mod,0.02\nGas-CC-CCS_mod,0.05\n"
        + "".join(f"{technology},0.9\n" for technology in technologies)
    )
    with (run_path / "outputs" / "cap_ivrt.csv").open("a") as file:
        file.writelines(f"{technology},new1,p1,2032,100\n" for technology in technologies)
    with (inputs / "plantcharout.csv").open("a") as file:
        file.writelines(
            f"{technology},{year},fom,10000\n"
            for technology in [*technologies, "coal-CCS_mod_r_fsa", "Gas-CC-CCS_mod_r_fsa"]
            for year in (2030, 2032)
        )

    config = ReEDSConfig(solve_year=2032, weather_year=2012)
    store = DataStore.from_plugin_config(config, path=run_path)
    context = PluginContext(config=config, store=store)
    result = ReEDSParser.from_context(context).run(ctx=context)

    assert result.system is not None
    generators = list(result.system.get_components(ReEDSThermalGenerator))
    for technology, rate in technologies.items():
        matched = [generator for generator in generators if generator.technology == technology.lower()]
        assert matched, technology
        assert all(
            generator.ramp_rate == pytest.approx(rate if water_switch else 0.9) for generator in matched
        )


@pytest.mark.parametrize(
    "missing_dataset",
    ["cooling_technology_links", "cooling_upgrade_technology_links"],
)
def test_water_mode_requires_both_cooling_files(reeds_run_path, tmp_path, missing_dataset):
    run_path = tmp_path / "run"
    shutil.copytree(reeds_run_path, run_path)
    inputs = run_path / "inputs_case"
    set_water_switch(inputs, True)
    (inputs / "upgradelink_water.csv").write_text("*TO-WATER,FROM-WATER,DELTA-WATER\n")
    filenames = {
        "cooling_technology_links": "i_coolingtech_watersource_link.csv",
        "cooling_upgrade_technology_links": "i_coolingtech_watersource_upgrades_link.csv",
    }
    for dataset, filename in filenames.items():
        path = inputs / filename
        if dataset != missing_dataset:
            path.write_text("*i,ii,ctt,wst\ngas-CC_r_fsa,gas-CC,r,fsa\n")
        elif path.exists():
            path.unlink()
    config = ReEDSConfig(solve_year=2032, weather_year=2012)
    store = DataStore.from_plugin_config(config, path=run_path)
    parser = ReEDSParser.from_context(PluginContext(config=config, store=store))
    assert parser._ensure_config_assets().is_ok()
    assert parser._prepare_default_metadata().is_ok()

    result = parser._prepare_generator_datasets()

    assert result.is_err()
    assert result.unwrap_err() == (
        f"Required cooling dataset '{missing_dataset}' is unavailable with GSw_WaterMain=1"
    )


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
        for generator in matched:
            assert isinstance(generator, ReEDSThermalGenerator | ReEDSHydroGenerator)
            assert generator.ramp_rate == expected
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
        for generator in selected[technology]:
            assert isinstance(generator, ReEDSThermalGenerator | ReEDSHydroGenerator)
            assert generator.ramp_rate == expected
