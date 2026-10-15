"""Tests for ReEDS-specific reader registration."""

from pathlib import Path

import polars as pl
import pytest

from r2x_core import DataFile, DataStore, ReaderConfig
from r2x_reeds.data_readers import register_gams_header_readers


@pytest.mark.parametrize(
    "name", ["cost_fom", "existing_capacity", "existing_transmission_capacity", "renewable_supply_curves"]
)
@pytest.mark.parametrize("marker", ["", "*"])
def test_gams_header_reader_preserves_csv_options(tmp_path: Path, name: str, marker: str) -> None:
    """CSV options survive registration and still allow header normalization."""
    path = tmp_path / "capacity.csv"
    path.write_text(f"{marker}i;value\nsolar;10.7\nwind;NA\n")
    reader = ReaderConfig(kwargs={"separator": ";", "null_values": ["NA"]})
    data_file = DataFile(name=name, fpath=path, reader=reader)
    store = DataStore(path=tmp_path)
    store.add_data([data_file])

    register_gams_header_readers(store)
    register_gams_header_readers(store)

    result = store.read_data(name).collect()
    assert result.to_dicts() == [{"i": "solar", "value": 10.7}, {"i": "wind", "value": None}]
    assert result.schema["value"] == pl.Float64
    registered_reader = store[name].reader
    assert registered_reader is not None
    assert registered_reader.kwargs == reader.kwargs
    assert data_file.reader is reader
    assert reader.function is None


@pytest.mark.parametrize(
    "name", ["cost_fom", "existing_capacity", "existing_transmission_capacity", "renewable_supply_curves"]
)
def test_gams_header_registration_preserves_custom_reader(tmp_path: Path, name: str) -> None:
    """An explicit reader keeps control of its output and keyword arguments."""
    path = tmp_path / "capacity.csv"
    path.touch()

    def read_capacity(fpath: Path, *, capacity: float = 0.0) -> pl.LazyFrame:
        assert fpath == path
        return pl.LazyFrame({"custom_capacity": [capacity]})

    reader = ReaderConfig(kwargs={"capacity": 42.0}, function=read_capacity)
    data_file = DataFile(name=name, fpath=path, reader=reader)
    store = DataStore(path=tmp_path)
    store.add_data([data_file])

    register_gams_header_readers(store)

    assert store[name].reader is reader
    assert store.read_data(name).collect().to_dicts() == [{"custom_capacity": 42.0}]


def test_gams_header_registration_preserves_multirow_reader(tmp_path: Path) -> None:
    """Multi-row CSV headers retain the built-in reader's semantics."""
    path = tmp_path / "capacity.csv"
    path.write_text("technology,capacity\nname,MW\nsolar,10.7\n")
    reader = ReaderConfig(kwargs={}, header_rows=2, header_separator="_")
    store = DataStore(path=tmp_path)
    store.add_data([DataFile(name="existing_capacity", fpath=path, reader=reader)])

    register_gams_header_readers(store)

    assert store["existing_capacity"].reader is reader
    assert store.read_data("existing_capacity").collect().to_dicts() == [
        {"technology_name": "solar", "capacity_MW": 10.7}
    ]


def test_gams_header_registration_ignores_missing_datasets(tmp_path: Path) -> None:
    """No ReEDS compatibility datasets need to be present."""
    store = DataStore(path=tmp_path)

    register_gams_header_readers(store)

    assert store.list_data() == []
