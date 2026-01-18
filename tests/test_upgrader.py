import pytest

from r2x_reeds.upgrader.data_upgrader import ReEDSUpgrader

pytestmark = [pytest.mark.integration]


@pytest.fixture
def upgraded_system(reeds_run_upgrader, example_reeds_config, caplog):
    from typing import cast

    from r2x_core import DataStore, PluginContext
    from r2x_reeds.parser import ReEDSParser

    store = DataStore.from_plugin_config(example_reeds_config, path=reeds_run_upgrader)

    ctx = PluginContext(config=example_reeds_config, store=store)
    parser = cast(ReEDSParser, ReEDSParser.from_context(ctx))
    result_ctx = parser.run()
    system = result_ctx.system
    assert system is not None
    return system


def test_reeds_upgrader(reeds_run_upgrader):
    upgrader = ReEDSUpgrader(reeds_run_upgrader)

    # Verify upgrader is initialized with folder path and steps
    assert upgrader.path == reeds_run_upgrader
    assert isinstance(upgrader.steps, list)


def test_upgraded_system(upgraded_system):
    from r2x_core import System

    assert isinstance(upgraded_system, System)
