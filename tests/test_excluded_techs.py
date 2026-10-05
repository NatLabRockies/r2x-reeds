"""Tests for excluded_techs functionality."""

import pytest

pytestmark = [pytest.mark.integration]


def test_excluded_techs_can_be_overridden(reeds_run_path):

    from r2x_core import DataStore, PluginContext
    from r2x_reeds import ReEDSConfig, ReEDSParser
    from r2x_reeds.models import ReEDSGenerator

    default_config = ReEDSConfig(
        solve_year=2032,
        weather_year=2012,
    )
    override_config = ReEDSConfig(
        solve_year=2032,
        weather_year=2012,
        excluded_techs=["electrolyzer", "smr", "smr_ccs"],
    )

    def parse_generators(config):
        data_store = DataStore.from_plugin_config(config, path=reeds_run_path)
        context = PluginContext(config=config, store=data_store)
        parser = ReEDSParser.from_context(context)
        result_ctx = parser.run()
        assert result_ctx.system is not None
        return list(result_ctx.system.get_components(ReEDSGenerator))

    default_generators = parse_generators(default_config)
    override_generators = parse_generators(override_config)

    assert not any(generator.technology == "can-imports" for generator in default_generators)
    import_generators = [
        generator for generator in override_generators if generator.technology == "can-imports"
    ]
    assert import_generators
    assert all(generator.heat_rate is None for generator in import_generators)


def test_excluded_techs_empty_list_default(reeds_config, reeds_run_path):
    from r2x_core import DataStore, PluginContext
    from r2x_reeds import ReEDSParser
    from r2x_reeds.models import ReEDSGenerator

    config_dicts = reeds_config.load_config()
    assert config_dicts["defaults"].get("excluded_techs") == [
        "can-imports",
        "electrolyzer",
        "smr",
        "smr_ccs",
    ]

    data_store = DataStore.from_plugin_config(reeds_config, path=reeds_run_path)
    ctx = PluginContext(config=reeds_config, store=data_store)
    parser = ReEDSParser.from_context(ctx)
    result_ctx = parser.run()

    system = result_ctx.system
    assert system is not None
    generators = list(system.get_components(ReEDSGenerator))

    assert len(generators) > 0
