"""Data path fixtures with override capability."""

import json
import shutil
import zipfile
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

import h5py
import numpy as np
import polars as pl
import pytest
from loguru import logger

from r2x_core.types import JSONValue

if TYPE_CHECKING:
    from r2x_core import DataStore
    from r2x_reeds import ReEDSConfig, ReEDSParser


def write_unitspec_upgrades_h5(path: Path, technologies: list[str]) -> None:
    """Write the required ReEDS HDF5 unitspec_upgrades set."""
    path.parent.mkdir(parents=True, exist_ok=True)
    string_dtype = h5py.string_dtype(encoding="utf-8")
    with h5py.File(path, mode="w") as h5_file:
        group = h5_file.create_group("unitspec_upgrades")
        group.create_dataset("columns", data=np.asarray(["i"], dtype=string_dtype))
        group.create_dataset("i", data=np.asarray(technologies, dtype=string_dtype))


def package_file_mapping() -> list[dict[str, Any]]:
    """Load the packaged current-core DataFile mapping."""
    mapping_path = Path(__file__).parents[2] / "src" / "r2x_reeds" / "config" / "file_mapping.json"
    mapping: list[dict[str, Any]] = json.loads(mapping_path.read_text())
    return mapping


def csv_file_mapping() -> list[dict[str, Any]]:
    """Return current DataFiles pointing at equivalent CSV fixture outputs."""
    mapping = package_file_mapping()
    for data_file in mapping:
        if data_file.get("relative_fpath") == "outputs/outputs.h5":
            group_key = data_file["reader"]["options"]["group_key"]
            data_file["relative_fpath"] = f"outputs/{group_key}.csv"
            data_file["reader"] = {"format": "csv"}
    return mapping


def current_data_store(path: Path, *, data_files: list[dict[str, Any]] | None = None) -> "DataStore":
    """Create a current-core store from validated test input declarations."""
    from pydantic import TypeAdapter

    from r2x_core import DataFile, DataStore

    store = DataStore(path=path)
    store.add_data(TypeAdapter(list[DataFile]).validate_python(data_files or csv_file_mapping()))
    return store


def read_source_frame(
    store: "DataStore", name: str, *, placeholders: Mapping[str, JSONValue] | None = None
) -> pl.DataFrame:
    """Read one named tabular source through its public record-access methods."""
    from r2x_core import DataReader, TabularSource

    sources = DataReader().read_data_files(
        [store[name]],
        folder_path=store.folder,
        placeholders=placeholders,
    )
    source = sources[name]
    if not isinstance(source, TabularSource):
        msg = f"Source {name!r} is not a tabular source"
        raise TypeError(msg)
    if not isinstance(source.data, pl.LazyFrame):
        msg = f"Source {name!r} does not contain a Polars LazyFrame"
        raise TypeError(msg)
    return source.data.collect()


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
    )


@pytest.fixture(scope="session")
def data_store(reeds_run_path: Path, reeds_config: "ReEDSConfig") -> "DataStore":
    """DataStore from file mapping."""
    return current_data_store(reeds_run_path)


@pytest.fixture(scope="session")
def parser(reeds_config: "ReEDSConfig", data_store: "DataStore") -> "ReEDSParser":
    """ReEDS parser instance (initialized with context)."""
    from r2x_core import PluginContext
    from r2x_reeds import ReEDSParser

    ctx = PluginContext(config=reeds_config, store=data_store)
    return ReEDSParser.from_context(ctx)
