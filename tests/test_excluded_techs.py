"""Tests for excluded_techs functionality."""


def test_excluded_techs_empty_list_default(reeds_config, reeds_run_path):
    from r2x_core import DataStore
    from r2x_reeds import ReEDSParser
    from r2x_reeds.models import ReEDSGenerator

    # Use classmethod API per migration: pass config_path explicitly
    config_dicts = reeds_config.load_config()
    assert config_dicts["defaults"].get("excluded_techs") == ["can-imports", "electrolyzer"]

    data_store = DataStore.from_plugin_config(reeds_config, path=reeds_run_path)
    parser = ReEDSParser(reeds_config, data_store=data_store)
    system = parser.build_system()
    generators = list(system.get_components(ReEDSGenerator))

    assert len(generators) > 0
