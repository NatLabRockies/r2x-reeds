# Plugin registration tests are no longer needed as PluginManager was refactored out
# from r2x_core. The plugin registration is now handled directly by entry points.

import pytest


@pytest.mark.skip(reason="PluginManager no longer exists")
def test_reeds_plugin_registration():
    pass
