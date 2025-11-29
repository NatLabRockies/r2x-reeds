import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from loguru import logger

if TYPE_CHECKING:
    from r2x_core import DataStore, System
    from r2x_reeds import ReEDSConfig, ReEDSParser

pytest_plugins = [
    "tests.fixtures.data_fixtures",
    "tests.fixtures.component_fixtures",
]


@pytest.fixture
def caplog(caplog):
    from r2x_core.logger import setup_logging

    setup_logging(level="DEBUG", tracing=True, enable_console_log=False)
    handler_id = logger.add(caplog.handler, format="{message}")
    try:
        yield caplog
    finally:
        logger.remove(handler_id)


@pytest.fixture(scope="function")
def empty_file(tmp_path) -> Path:
    empty_fpath = tmp_path / "test.csv"
    empty_fpath.write_text("")
    yield empty_fpath
    empty_fpath.unlink()


@pytest.fixture(scope="session")
def data_path() -> Path:
    """Path to test data directory."""
    return Path(__file__).parent / "data"


@pytest.fixture(scope="session")
def reeds_run_path(tmp_path_factory, data_path: Path) -> Path:
    """Copy the entire data_path folder into a fresh session tmp directory and return the copied dir."""
    base_tmp = tmp_path_factory.mktemp("reeds_run")
    archive_run = data_path / "test_Pacific.zip"
    with zipfile.ZipFile(archive_run, "r") as zip_ref:
        zip_ref.extractall(base_tmp)
    return base_tmp / "test_Pacific"


@pytest.fixture(scope="session")
def reeds_run_upgrader(tmp_path_factory, data_path: Path) -> Path:
    """Copy the entire data_path folder into a fresh session tmp directory and return the copied dir."""
    base_tmp = tmp_path_factory.mktemp("reeds_run")
    archive_run = data_path / "test_Upgrader.zip"
    with zipfile.ZipFile(archive_run, "r") as zip_ref:
        zip_ref.extractall(base_tmp)
    return base_tmp / "test_Upgrader"


@pytest.fixture(scope="session")
def example_reeds_config() -> "ReEDSConfig":
    """Create ReEDS configuration for testing."""
    from r2x_reeds import ReEDSConfig

    return ReEDSConfig(solve_year=2032, weather_year=2012, case_name="test", scenario="base")


@pytest.fixture(scope="session")
def example_data_store(reeds_run_path: Path, example_reeds_config: "ReEDSConfig") -> "DataStore":
    """Create DataStore from file mapping."""

    from r2x_core import DataStore

    return DataStore.from_plugin_config(example_reeds_config, path=reeds_run_path)


@pytest.fixture(scope="session")
def example_parser(example_reeds_config: "ReEDSConfig", example_data_store: "DataStore") -> "ReEDSParser":
    """Create ReEDS parser instance."""
    from r2x_reeds import ReEDSParser

    return ReEDSParser(config=example_reeds_config, data_store=example_data_store, name="test_system")


@pytest.fixture(scope="session")
def example_system(example_parser: "ReEDSParser") -> "System":
    """Build and return the system (shared fixture for all tests)."""
    return example_parser.build_system()
