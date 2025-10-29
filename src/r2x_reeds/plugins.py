"""R2X-core plugin discovery."""

from r2x_core.plugins import PluginManager
from r2x_reeds.config import ReEDSConfig
from r2x_reeds.parser import ReEDSParser
from r2x_reeds.upgrader.data_upgrader import ReEDSUpgrader


def register_plugin() -> str | None:
    """Register the ReEDS plugin with the R2X plugin manager.

    This function is called automatically when the plugin is discovered
    via entry points. It registers the ReEDS parser, config, and optionally
    an exporter with the PluginManager.
    """

    PluginManager.register_model_plugin(
        name="reeds",
        config=ReEDSConfig,
        parser=ReEDSParser,
        upgrader=ReEDSUpgrader,  # Steps already registered via decorators
    )

    return None
