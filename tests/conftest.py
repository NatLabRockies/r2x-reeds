import shutil
import tarfile
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from loguru import logger

if TYPE_CHECKING:
    from r2x_core import DataStore, System
    from r2x_reeds import ReEDSConfig, ReEDSParser


@pytest.fixture
def caplog(caplog):
    logger.enable("r2x_core")
    logger.enable("r2x_reeds")
    handler_id = logger.add(caplog.handler, format="{message}")
    yield caplog
    logger.remove(handler_id)


@pytest.fixture(scope="function")
def empty_file(tmp_path) -> Path:
    empty_fpath = tmp_path / "test.csv"
    empty_fpath.write_text("")
    yield empty_fpath
    empty_fpath.unlink()


@pytest.fixture(scope="session", autouse=True)
def _extract_test_data(tmp_path_factory) -> None:
    """Automatically extract compressed test data to temp folder.

    This fixture extracts test_Pacific.tar.gz and test_Upgrader.tar.gz
    to a temporary directory before any tests run, then creates symlinks
    in the tests/data folder to make them accessible to test fixtures.
    """
    data_dir = Path(__file__).parent / "data"
    temp_dir = tmp_path_factory.mktemp("test_data_extracted")

    # Extract and symlink test_Pacific
    pacific_archive = data_dir / "test_Pacific.tar.gz"
    pacific_dir = data_dir / "test_Pacific"
    if pacific_archive.exists():
        logger.info("Extracting test_Pacific.tar.gz to temporary folder...")
        with tarfile.open(pacific_archive, "r:gz") as tar:
            tar.extractall(path=temp_dir, filter="data")  # type: ignore

        # Create symlink if directory doesn't exist
        if not pacific_dir.exists():
            pacific_dir.symlink_to(temp_dir / "test_Pacific")
        logger.info("✓ test_Pacific ready")

    # Extract and symlink test_Upgrader
    upgrader_archive = data_dir / "test_Upgrader.tar.gz"
    upgrader_dir = data_dir / "test_Upgrader"
    if upgrader_archive.exists():
        logger.info("Extracting test_Upgrader.tar.gz to temporary folder...")
        with tarfile.open(upgrader_archive, "r:gz") as tar:
            tar.extractall(path=temp_dir, filter="data")  # type: ignore

        # Create symlink if directory doesn't exist
        if not upgrader_dir.exists():
            upgrader_dir.symlink_to(temp_dir / "test_Upgrader")
        logger.info("✓ test_Upgrader ready")


@pytest.fixture(scope="session")
def data_path() -> Path:
    """Path to test data directory."""
    return Path(__file__).parent / "data" / "test_Pacific"


@pytest.fixture(scope="session")
def upgrader_run_path() -> Path:
    """Path to test data directory."""
    return Path(__file__).parent / "data" / "test_Upgrader"


@pytest.fixture(scope="session")
def reeds_run_path(tmp_path_factory, data_path: Path) -> Path:
    """Copy the entire data_path folder into a fresh session tmp directory and return the copied dir."""
    base_tmp = tmp_path_factory.mktemp("reeds_run")
    dst = base_tmp / data_path.name
    shutil.copytree(data_path, dst)
    return dst


@pytest.fixture(scope="session")
def reeds_run_upgrader(tmp_path_factory, upgrader_run_path: Path) -> Path:
    """Copy the entire data_path folder into a fresh session tmp directory and return the copied dir."""
    base_tmp = tmp_path_factory.mktemp("reeds_run")
    dst = base_tmp / upgrader_run_path.name
    shutil.copytree(upgrader_run_path, dst)
    return dst


@pytest.fixture(scope="session")
def example_reeds_config() -> "ReEDSConfig":
    """Create ReEDS configuration for testing."""
    from r2x_reeds import ReEDSConfig

    return ReEDSConfig(solve_year=2032, weather_year=2012, case_name="test", scenario="base")


@pytest.fixture(scope="session")
def example_data_store(reeds_run_path: Path, example_reeds_config: "ReEDSConfig") -> "DataStore":
    """Create DataStore from file mapping."""

    from r2x_core import DataStore

    return DataStore.from_plugin_config(example_reeds_config, folder_path=reeds_run_path)


@pytest.fixture(scope="session")
def example_parser(example_reeds_config: "ReEDSConfig", example_data_store: "DataStore") -> "ReEDSParser":
    """Create ReEDS parser instance."""
    from r2x_reeds import ReEDSParser

    return ReEDSParser(config=example_reeds_config, data_store=example_data_store, name="test_system")


@pytest.fixture(scope="session")
def example_system(example_parser: "ReEDSParser") -> "System":
    """Build and return the system (shared fixture for all tests)."""
    return example_parser.build_system()
