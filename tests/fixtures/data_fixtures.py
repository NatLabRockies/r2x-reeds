"""Data path fixtures with override capability."""

import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from loguru import logger

if TYPE_CHECKING:
    from r2x_core import DataStore
    from r2x_reeds import ReEDSConfig, ReEDSParser


@pytest.fixture(scope="session")
def test_data_path() -> Path:
    """Default test data directory."""
    return Path(__file__).parent.parent / "data"


@pytest.fixture(scope="session")
def reeds_run_path(reeds_data_path_override: Path | None, tmp_path_factory, test_data_path: Path) -> Path:
    """ReEDS run path - uses override if provided, otherwise unpacks test data."""
    if reeds_data_path_override:
        logger.info("Using override ReEDS data path: {}", reeds_data_path_override)
        return reeds_data_path_override

    base_tmp = tmp_path_factory.mktemp("reeds_run")
    archive_run = test_data_path / "test_Pacific.zip"

    if not archive_run.exists():
        pytest.fail(f"Test data archive not found: {archive_run}")

    with zipfile.ZipFile(archive_run, "r") as zip_ref:
        zip_ref.extractall(base_tmp)

    run_path = base_tmp / "test_Pacific"
    logger.debug("Unpacked test data to: {}", run_path)
    return run_path


@pytest.fixture(scope="session")
def reeds_config(reeds_run_path: Path) -> "ReEDSConfig":
    """ReEDS configuration for testing."""
    from r2x_reeds import ReEDSConfig

    return ReEDSConfig(
        solve_year=2032,
        weather_year=2012,
        case_name="test",
        scenario="base",
    )


@pytest.fixture(scope="session")
def data_store(reeds_run_path: Path, reeds_config: "ReEDSConfig") -> "DataStore":
    """DataStore from file mapping."""
    from r2x_core import DataStore

    return DataStore.from_plugin_config(reeds_config, path=reeds_run_path)


@pytest.fixture(scope="session")
def parser(reeds_config: "ReEDSConfig", data_store: "DataStore") -> "ReEDSParser":
    """ReEDS parser instance."""
    from r2x_reeds import ReEDSParser

    return ReEDSParser(config=reeds_config, data_store=data_store, name="test_system")
