import pytest

from r2x_reeds.upgrader.data_upgrader import ReEDSUpgrader


@pytest.fixture
def upgraded_system(reeds_run_upgrader, example_reeds_config, caplog):
    from r2x_core import DataStore
    from r2x_reeds.parser import ReEDSParser

    # Create upgrader but don't pass it to DataStore
    # DataStore.from_plugin_config doesn't accept upgrader argument
    store = DataStore.from_plugin_config(example_reeds_config, path=reeds_run_upgrader)

    parser = ReEDSParser(example_reeds_config, store=store, system_name="Upgraded System")
    return parser.build_system()


def test_reeds_upgrader(reeds_run_upgrader):
    upgrader = ReEDSUpgrader(reeds_run_upgrader)

    # Verify upgrader is initialized with folder path and steps
    assert upgrader.path == reeds_run_upgrader
    assert isinstance(upgrader.steps, list)


def test_upgraded_system(upgraded_system):
    from r2x_core import System

    assert isinstance(upgraded_system, System)
