"""Data path fixtures with override capability."""

import json
import shutil
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from loguru import logger

if TYPE_CHECKING:
    from r2x_core import DataStore
    from r2x_reeds import ReEDSConfig, ReEDSParser


def package_file_mapping() -> dict[str, Any]:
    """Load the packaged file mapping for format-specific reader tests."""
    mapping_path = Path(__file__).parents[2] / "src" / "r2x_reeds" / "config" / "file_mapping.json"
    mapping: dict[str, Any] = json.loads(mapping_path.read_text())
    return mapping


def csv_file_mapping() -> dict[str, Any]:
    """Return an explicit CSV mapping for the unpacked ReEDS test archive."""
    mapping = package_file_mapping()
    for data_file in mapping["files"]:
        if data_file["fpath"] == "outputs/outputs.h5":
            reader = data_file.pop("reader")
            group_key = reader["kwargs"]["group_key"]
            data_file["fpath"] = f"outputs/{group_key}.csv"
    return mapping


@pytest.fixture(scope="session")
def fixed_om_inputs(test_data_path: Path) -> Path:
    """Tracked inputs omitted from the reduced run archives."""
    return test_data_path / "test_Upgrader" / "inputs_case"


@pytest.fixture(scope="session")
def test_data_path() -> Path:
    """Default test data directory."""
    return Path(__file__).parent.parent / "data"


@pytest.fixture(scope="session")
def reeds_run_path(
    reeds_data_path_override: Path | None, tmp_path_factory, test_data_path: Path, fixed_om_inputs: Path
) -> Path:
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
    for name in (
        "plantcharout",
        "hyd_fom",
        "scalars",
        "switches",
        "hintage_data",
        "upgrade_link",
        "unitspec_upgrades",
        "tech-subset-table",
    ):
        shutil.copyfile(fixed_om_inputs / f"{name}.csv", run_path / "inputs_case" / f"{name}.csv")
    logger.debug("Unpacked test data to: {}", run_path)
    return run_path


@pytest.fixture(scope="session")
def reeds_run_upgrader(tmp_path_factory, test_data_path: Path, fixed_om_inputs: Path) -> Path:
    """ReEDS upgrader test data - unpacks test_Upgrader.zip."""
    base_tmp = tmp_path_factory.mktemp("reeds_run_upgrader")
    archive_run = test_data_path / "test_Upgrader.zip"

    if not archive_run.exists():
        pytest.fail(f"Test data archive not found: {archive_run}")

    with zipfile.ZipFile(archive_run, "r") as zip_ref:
        zip_ref.extractall(base_tmp)

    run_path = base_tmp / "test_Upgrader"
    shutil.copyfile(fixed_om_inputs / "plantcharout.csv", run_path / "inputs_case" / "plantcharout.csv")
    logger.debug("Unpacked upgrader test data to: {}", run_path)
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
        asset_overrides={"file_mapping": csv_file_mapping()},
    )


@pytest.fixture(scope="session")
def data_store(reeds_run_path: Path, reeds_config: "ReEDSConfig") -> "DataStore":
    """DataStore from file mapping."""
    from r2x_core import DataStore

    return DataStore.from_plugin_config(reeds_config, path=reeds_run_path)


@pytest.fixture(scope="session")
def parser(reeds_config: "ReEDSConfig", data_store: "DataStore") -> "ReEDSParser":
    """ReEDS parser instance (initialized with context)."""
    from r2x_core import PluginContext
    from r2x_reeds import ReEDSParser

    ctx = PluginContext(config=reeds_config, store=data_store)
    return ReEDSParser.from_context(ctx)


# Backward compatibility aliases for tests using old fixture names
@pytest.fixture(scope="session")
def example_reeds_config(reeds_config: "ReEDSConfig") -> "ReEDSConfig":
    """Alias for reeds_config (backward compatibility)."""
    return reeds_config


@pytest.fixture(scope="session")
def example_data_store(data_store: "DataStore") -> "DataStore":
    """Alias for the configured ReEDS data store."""
    return data_store


@pytest.fixture(scope="session")
def example_parser(parser: "ReEDSParser") -> "ReEDSParser":
    """Alias for parser (backward compatibility)."""
    return parser
