"""ReEDS CSV ramp rates reach generator objects without capacity or time scaling."""

import json
import shutil
from importlib.resources import files

import pytest

from r2x_core import DataStore, PluginContext
from r2x_reeds import ReEDSConfig, ReEDSParser
from r2x_reeds.models import ReEDSThermalGenerator
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
