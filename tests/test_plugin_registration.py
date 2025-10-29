from r2x_core import PluginManager
from r2x_reeds.parser import ReEDSParser
from r2x_reeds.plugins import register_plugin


def test_reeds_plugin_registration():
    pm = PluginManager()

    register_plugin()

    assert "reeds" in pm.registered_parsers
    assert pm.load_parser(name="reeds") == ReEDSParser
