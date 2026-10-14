"""Basic ReEDS parser tests using r2x-core 0.1.1 API.

These tests verify basic parser instantiation and configuration using
a minimal test data set.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import h5py
import numpy as np
import polars as pl
import pytest
from rust_ok import Err, Ok

pytestmark = [pytest.mark.integration]

if TYPE_CHECKING:
    pass


def _build_parser(run_path: Path, *, use_degraded_capacity: bool = False):
    from r2x_core import DataStore, PluginContext
    from r2x_reeds import ReEDSConfig, ReEDSParser

    config = ReEDSConfig(
        solve_year=2032,
        weather_year=2012,
        case_name="test",
        scenario="base",
        use_degraded_capacity=use_degraded_capacity,
    )
    store = DataStore.from_plugin_config(config, path=run_path)
    ctx = PluginContext(config=config, store=store)
    return ReEDSParser.from_context(ctx)


def _write_minimal_outputs_h5_from_fuel_price(csv_path: Path, h5_path: Path) -> None:
    """Create a minimal outputs.h5 containing a fuel_price group."""
    fuel_price = pl.read_csv(csv_path)
    if "value" in fuel_price.columns:
        fuel_price = fuel_price.rename({"value": "Value"})

    with h5py.File(h5_path, "w") as h5_file:
        group = h5_file.create_group("fuel_price")
        columns = fuel_price.columns
        group.create_dataset("columns", data=np.array(columns, dtype="S"))

        for column in columns:
            values = fuel_price[column].to_list()
            if values and isinstance(values[0], str):
                dataset_values = np.array(values, dtype="S")
            else:
                dataset_values = np.array(values)
            group.create_dataset(column, data=dataset_values)


def _write_fuel2tech_outputs_h5(h5_path: Path) -> None:
    """Create a ReEDS-style fuel2tech group without generic table metadata."""
    with h5py.File(h5_path, "w") as h5_file:
        group = h5_file.create_group("fuel2tech")
        group.create_dataset("f", data=np.array(["ngas", "coal"], dtype="S"))
        group.create_dataset("i", data=np.array(["gas-cc", "coal"], dtype="S"))


def test_read_data_file_falls_back_to_legacy_outputs_csv(reeds_run_path: Path) -> None:
    """When outputs.h5 is absent, parser should still read legacy outputs CSV files."""
    parser = _build_parser(reeds_run_path)

    result = parser.read_data_file("fuel_price")

    assert result is not None
    df = result.collect()
    assert not df.is_empty()
    assert {"technology", "region", "year", "fuel_price"}.issubset(set(df.columns))


def test_read_data_file_uses_outputs_h5_and_not_csv(tmp_path: Path, reeds_run_path: Path) -> None:
    """Parser should read output datasets from outputs.h5 when available."""
    run_path = tmp_path / "test_Pacific"
    shutil.copytree(reeds_run_path, run_path)

    outputs_dir = run_path / "outputs"
    fuel_price_csv = outputs_dir / "fuel_price.csv"
    pl.DataFrame({"i": ["NGAS"], "r": ["P1"], "t": [2032], "value": [4.2]}).write_csv(fuel_price_csv)
    outputs_h5 = outputs_dir / "outputs.h5"

    _write_minimal_outputs_h5_from_fuel_price(fuel_price_csv, outputs_h5)
    fuel_price_csv.unlink()

    parser = _build_parser(run_path)
    result = parser.read_data_file("fuel_price")

    assert result is not None
    df = result.collect()
    assert not df.is_empty()
    assert {"technology", "region", "year", "fuel_price"}.issubset(set(df.columns))
    assert df.select("technology", "region").to_dict(as_series=False) == {
        "technology": ["ngas"],
        "region": ["p1"],
    }


def test_read_data_file_uses_degraded_capacity_from_outputs_h5(tmp_path: Path, reeds_run_path: Path) -> None:
    """Select degraded capacity and lowercase its technology and region identifiers."""
    run_path = tmp_path / "test_Pacific"
    shutil.copytree(reeds_run_path, run_path)

    outputs_h5 = run_path / "outputs" / "outputs.h5"
    with h5py.File(outputs_h5, "w") as h5_file:
        group = h5_file.create_group("cap_deg_ivrt")
        group.create_dataset("columns", data=np.array([b"i", b"r", b"t", b"v", b"value"]))
        group.create_dataset("i", data=np.array([b"WIND-ONS"]))
        group.create_dataset("r", data=np.array([b"P4"]))
        group.create_dataset("t", data=np.array([2032]))
        group.create_dataset("v", data=np.array([2020]))
        group.create_dataset("value", data=np.array([95.0]))

    parser = _build_parser(run_path, use_degraded_capacity=True)
    result = parser.read_data_file("online_capacity")

    assert result is not None
    assert result.collect().to_dict(as_series=False) == {
        "technology": ["wind-ons"],
        "region": ["p4"],
        "year": [2032],
        "vintage": [2020],
        "capacity": [95.0],
    }


def test_read_data_file_uses_degraded_capacity_csv_fallback(tmp_path: Path, reeds_run_path: Path) -> None:
    """The degraded-capacity flag falls back to outputs/cap_deg_ivrt.csv."""
    run_path = tmp_path / "test_Pacific"
    shutil.copytree(reeds_run_path, run_path)

    outputs_dir = run_path / "outputs"
    with h5py.File(outputs_dir / "outputs.h5", "w"):
        pass
    pl.DataFrame(
        {
            "i": ["wind-ons"],
            "r": ["p4"],
            "t": [2032],
            "v": [2020],
            "Value": [95.0],
        }
    ).write_csv(outputs_dir / "cap_deg_ivrt.csv")

    parser = _build_parser(run_path, use_degraded_capacity=True)
    result = parser.read_data_file("online_capacity")

    assert result is not None
    assert result.collect().to_dict(as_series=False)["capacity"] == [95.0]


def test_read_data_file_reports_missing_degraded_capacity(tmp_path: Path, reeds_run_path: Path) -> None:
    """Missing degraded capacity must identify cap_deg_ivrt instead of returning None."""
    run_path = tmp_path / "test_Pacific"
    shutil.copytree(reeds_run_path, run_path)

    with h5py.File(run_path / "outputs" / "outputs.h5", "w"):
        pass

    parser = _build_parser(run_path, use_degraded_capacity=True)
    with pytest.raises(FileNotFoundError, match="cap_deg_ivrt"):
        parser.read_data_file("online_capacity")


@pytest.mark.parametrize(
    "register_with_parser",
    [False, True],
    ids=["explicit-reader-registration", "parser-context"],
)
def test_modeled_years_mapping_reads_headerless_csv(tmp_path: Path, register_with_parser: bool) -> None:
    import json

    from r2x_core import DataFile, DataStore, PluginContext
    from r2x_reeds import ReEDSConfig, ReEDSParser, register_modeled_years_reader

    input_case = tmp_path / "inputs_case"
    input_case.mkdir()
    (input_case / "modeledyears.csv").write_text("2010,2020,2030\n")
    mapping_path = Path(__file__).parents[1] / "src" / "r2x_reeds" / "config" / "file_mapping.json"
    records = json.loads(mapping_path.read_text())
    record = next(item for item in records if item["name"] == "modeled_years")
    data_file = DataFile.from_record(record, folder_path=tmp_path)
    store = DataStore(tmp_path)
    store.add_data([data_file])
    config = ReEDSConfig(
        solve_year=2032,
        weather_year=2012,
        case_name="test",
        scenario="base",
    )
    if register_with_parser:
        store = ReEDSParser.from_context(PluginContext(config=config, store=store)).store
    else:
        register_modeled_years_reader(store)

    result = store.read_data("modeled_years").collect()

    assert result.schema["modeled_years"] == pl.Int32
    assert result.to_dicts() == [
        {"modeled_years": 2010},
        {"modeled_years": 2020},
        {"modeled_years": 2030},
    ]


def test_read_fuel_tech_map_uses_reeds_mapping_nodes(tmp_path: Path, reeds_run_path: Path) -> None:
    """The ReEDS fuel2tech group uses f/i nodes without a value column."""
    run_path = tmp_path / "test_Pacific"
    shutil.copytree(reeds_run_path, run_path)

    outputs_h5 = run_path / "outputs" / "outputs.h5"
    _write_fuel2tech_outputs_h5(outputs_h5)

    parser = _build_parser(run_path)
    result = parser.read_data_file("fuel_tech_map")

    assert result is not None
    assert result.collect().to_dict(as_series=False) == {
        "fuel_type": ["ngas", "coal"],
        "technology": ["gas-cc", "coal"],
    }


def test_read_data_file_uses_store_for_non_outputs_dataset(reeds_run_path: Path) -> None:
    """Non-output mappings should still be read through DataStore directly."""
    parser = _build_parser(reeds_run_path)

    result = parser.read_data_file("hierarchy")

    assert result is not None
    df = result.collect()
    assert not df.is_empty()
    assert "region_id" in df.columns


@pytest.mark.parametrize("technology_column", ["i", "*i"])
def test_read_existing_capacity_with_technology_column(tmp_path: Path, technology_column: str) -> None:
    """Existing capacity inputs support plain and domain-marked technology columns."""
    import json

    from r2x_core import DataFile, DataStore
    from r2x_reeds.data_readers import register_gams_header_readers

    inputs_case = tmp_path / "inputs_case"
    inputs_case.mkdir()
    (inputs_case / "capnonrsc.csv").write_text(f"{technology_column},r,value\nsolar,p1,100.0\n")

    mapping_path = Path(__file__).parents[1] / "src" / "r2x_reeds" / "config" / "file_mapping.json"
    records = json.loads(mapping_path.read_text())
    record = next(item for item in records if item["name"] == "existing_capacity")
    store = DataStore(path=tmp_path)
    store.add_data([DataFile.from_record(record, folder_path=tmp_path)])
    register_gams_header_readers(store)

    result = store.read_data("existing_capacity")

    assert result.collect().to_dicts() == [{"technology": "solar", "region": "p1", "capacity": 100.0}]


@pytest.mark.parametrize("from_region_column", ["r", "*r"])
def test_read_existing_transmission_capacity_with_region_column(
    tmp_path: Path, from_region_column: str
) -> None:
    """Initial transmission capacity inputs support plain and domain-marked regions."""
    import json

    from r2x_core import DataFile, DataStore
    from r2x_reeds.data_readers import register_gams_header_readers

    inputs_case = tmp_path / "inputs_case"
    inputs_case.mkdir()
    (inputs_case / "trancap_init_energy.csv").write_text(
        f"{from_region_column},rr,trtype,MW\np1,p2,AC,10.7\n"
    )

    mapping_path = Path(__file__).parents[1] / "src" / "r2x_reeds" / "config" / "file_mapping.json"
    records = json.loads(mapping_path.read_text())
    record = next(item for item in records if item["name"] == "existing_transmission_capacity")
    store = DataStore(path=tmp_path)
    store.add_data([DataFile.from_record(record, folder_path=tmp_path)])
    register_gams_header_readers(store)

    result = store.read_data("existing_transmission_capacity")

    assert result.collect().to_dicts() == [
        {"from_region": "p1", "to_region": "p2", "trtype": "ac", "capacity": 10.7}
    ]


@pytest.mark.parametrize("technology_column", ["i", "*i"])
def test_read_renewable_supply_curves_with_technology_column(tmp_path: Path, technology_column: str) -> None:
    """Renewable supply curves support plain and domain-marked technology columns."""
    import json

    from r2x_core import DataFile, DataStore
    from r2x_reeds.data_readers import register_gams_header_readers

    inputs_case = tmp_path / "inputs_case"
    inputs_case.mkdir()
    (inputs_case / "caprsc.csv").write_text(f"{technology_column},r,value\nupv,p1,10.0\n")

    mapping_path = Path(__file__).parents[1] / "src" / "r2x_reeds" / "config" / "file_mapping.json"
    records = json.loads(mapping_path.read_text())
    record = next(item for item in records if item["name"] == "renewable_supply_curves")
    store = DataStore(path=tmp_path)
    store.add_data([DataFile.from_record(record, folder_path=tmp_path)])
    register_gams_header_readers(store)

    result = store.read_data("renewable_supply_curves")

    assert result.collect().to_dicts() == [{"technology": "upv", "region": "p1", "capacity": 10.0}]


def test_read_original_hierarchy_with_r_column(tmp_path: Path) -> None:
    """Current original hierarchy inputs use 'r' instead of 'ba' and 'aggreg'."""
    import json

    from r2x_core import DataFile, DataStore

    inputs_case = tmp_path / "inputs_case"
    inputs_case.mkdir()
    (inputs_case / "hierarchy_original.csv").write_text(
        "r,st,interconnect,transgrp,transreg,nercr,hurdlereg,country,cendiv,"
        "usda_region,h2ptcreg,gasreg,offshore\n"
        "p1,wa,western,northerngrid_west,northerngrid,wecc_nw,bonneville,usa,"
        "pacific,pacific,northwest,northwest,0\n"
    )

    mapping_path = Path(__file__).parents[1] / "src" / "r2x_reeds" / "config" / "file_mapping.json"
    records = json.loads(mapping_path.read_text())
    record = next(item for item in records if item["name"] == "hierarchy_original")
    store = DataStore(path=tmp_path)
    store.add_data([DataFile.from_record(record, folder_path=tmp_path)])

    result = store.read_data("hierarchy_original")

    assert result.collect().to_dicts() == [
        {
            "r": "p1",
            "state": "wa",
            "interconnect": "western",
            "transmission_group": "northerngrid_west",
            "transmission_region": "northerngrid",
            "nerc_region": "wecc_nw",
            "hurdle_region": "bonneville",
            "country": "usa",
            "cendiv": "pacific",
            "usda_region": "pacific",
            "h2ptc_region": "northwest",
            "gasreg": "northwest",
            "offshore": 0,
        }
    ]


def test_is_outputs_h5_mapped_matches_expected_datasets(reeds_run_path: Path) -> None:
    """Outputs bundle detector should classify outputs and non-outputs correctly."""
    parser = _build_parser(reeds_run_path)

    assert parser._is_outputs_h5_mapped("fuel_price") is True
    assert parser._is_outputs_h5_mapped("hierarchy") is False


def test_read_outputs_h5_group_missing_file_returns_none(tmp_path: Path, reeds_run_path: Path) -> None:
    """Missing outputs.h5 should be handled as no data available."""
    parser = _build_parser(reeds_run_path)

    result = parser._read_outputs_h5_group(tmp_path / "missing.h5", "fuel_price")

    assert result is None


def test_read_outputs_h5_group_missing_dataset_returns_none(tmp_path: Path, reeds_run_path: Path) -> None:
    """Missing dataset groups in outputs.h5 should return None."""
    parser = _build_parser(reeds_run_path)
    h5_path = tmp_path / "outputs.h5"
    with h5py.File(h5_path, "w") as h5_file:
        h5_file.create_group("some_other_group")

    result = parser._read_outputs_h5_group(h5_path, "fuel_price")

    assert result is None


def test_read_outputs_h5_group_non_group_node_returns_none(tmp_path: Path, reeds_run_path: Path) -> None:
    """Non-group H5 nodes should be rejected for dataset extraction."""
    parser = _build_parser(reeds_run_path)
    h5_path = tmp_path / "outputs.h5"
    with h5py.File(h5_path, "w") as h5_file:
        h5_file.create_dataset("fuel_price", data=np.array([1.0]))

    result = parser._read_outputs_h5_group(h5_path, "fuel_price")

    assert result is None


def test_read_outputs_h5_group_missing_columns_value_nodes_returns_none(
    tmp_path: Path, reeds_run_path: Path
) -> None:
    """Groups missing required columns/value nodes should be skipped."""
    parser = _build_parser(reeds_run_path)
    h5_path = tmp_path / "outputs.h5"
    with h5py.File(h5_path, "w") as h5_file:
        h5_file.create_group("fuel_price")

    result = parser._read_outputs_h5_group(h5_path, "fuel_price")

    assert result is None


def test_read_outputs_h5_group_missing_column_dataset_returns_none(
    tmp_path: Path, reeds_run_path: Path
) -> None:
    """If a column listed in 'columns' is absent as a dataset, parser skips the group."""
    parser = _build_parser(reeds_run_path)
    h5_path = tmp_path / "outputs.h5"
    with h5py.File(h5_path, "w") as h5_file:
        group = h5_file.create_group("fuel_price")
        group.create_dataset("columns", data=np.array([b"i", b"r", b"Value"]))
        group.create_dataset("Value", data=np.array([1.0, 2.0]))
        group.create_dataset("i", data=np.array([b"tech1", b"tech2"]))
        # Intentionally omit column dataset "r"

    result = parser._read_outputs_h5_group(h5_path, "fuel_price")

    assert result is None


def test_read_outputs_h5_group_lowercase_value_dataset(tmp_path: Path, reeds_run_path: Path) -> None:
    """H5 groups using lowercase 'value' (as declared in several file_mapping.json
    entries, e.g. online_capacity) must be read without falling back or dropping data."""
    parser = _build_parser(reeds_run_path)
    h5_path = tmp_path / "outputs.h5"
    with h5py.File(h5_path, "w") as h5_file:
        group = h5_file.create_group("online_capacity")
        # Mirrors what a ReEDS outputs.h5 group looks like when the measure column is
        # stored as lowercase 'value' rather than 'Value'.
        group.create_dataset("columns", data=np.array([b"i", b"r", b"value"]))
        group.create_dataset("value", data=np.array([10.0, 20.0]))
        group.create_dataset("i", data=np.array([b"wind-ons", b"upv"]))
        group.create_dataset("r", data=np.array([b"p4", b"p5"]))

    result = parser._read_outputs_h5_group(h5_path, "online_capacity")

    assert result is not None, "lowercase 'value' dataset should be accepted"
    df = result.collect()
    assert not df.is_empty()
    assert "value" in df.columns
    assert list(df["value"].to_list()) == pytest.approx([10.0, 20.0])


def test_read_outputs_h5_group_uses_cache_for_repeat_reads(tmp_path: Path, reeds_run_path: Path) -> None:
    """Repeated reads should return the cached LazyFrame for a dataset key."""
    parser = _build_parser(reeds_run_path)
    h5_path = tmp_path / "outputs.h5"
    with h5py.File(h5_path, "w") as h5_file:
        group = h5_file.create_group("fuel_price")
        group.create_dataset("columns", data=np.array([b"i", b"r", b"Value"]))
        group.create_dataset("Value", data=np.array([1.0, 2.0]))
        group.create_dataset("i", data=np.array([b"tech1", b"tech2"]))
        group.create_dataset("r", data=np.array([b"p1", b"p2"]))

    first = parser._read_outputs_h5_group(h5_path, "fuel_price")
    second = parser._read_outputs_h5_group(h5_path, "fuel_price")

    assert first is not None
    assert second is first


def test_read_outputs_dataset_processing_error_raises(monkeypatch, reeds_run_path: Path) -> None:
    """Processing failures should surface as ValueError from the parser wrapper."""
    import r2x_reeds.parser as parser_module

    parser = _build_parser(reeds_run_path)

    monkeypatch.setattr(
        parser,
        "_read_outputs_h5_group",
        lambda outputs_h5, dataset_key: pl.DataFrame({"i": ["tech"], "r": ["p1"], "Value": [1.0]}).lazy(),
    )
    monkeypatch.setattr(
        parser_module,
        "apply_processing",
        lambda data, data_file, proc_spec, placeholders: Err(ValueError("boom")),
    )

    with pytest.raises(ValueError, match="boom"):
        parser._read_outputs_dataset("fuel_price", {"solve_year": 2032, "weather_year": 2012})


def test_read_outputs_dataset_none_processed_returns_none(monkeypatch, reeds_run_path: Path) -> None:
    """None payload from processing should be returned unchanged."""
    import r2x_reeds.parser as parser_module

    parser = _build_parser(reeds_run_path)
    monkeypatch.setattr(
        parser,
        "_read_outputs_h5_group",
        lambda outputs_h5, dataset_key: pl.DataFrame({"i": ["tech"], "r": ["p1"], "Value": [1.0]}).lazy(),
    )
    monkeypatch.setattr(
        parser_module,
        "apply_processing",
        lambda data, data_file, proc_spec, placeholders: Ok(None),
    )

    result = parser._read_outputs_dataset("fuel_price", {"solve_year": 2032, "weather_year": 2012})
    assert result is None


def test_read_outputs_csv_fallback_optional_missing_returns_none(
    tmp_path: Path, reeds_run_path: Path
) -> None:
    """Optional output datasets should return None when CSV fallback is absent."""
    parser = _build_parser(reeds_run_path)
    outputs_h5 = tmp_path / "outputs.h5"
    outputs_h5.touch()

    result = parser._read_outputs_csv_fallback(
        name="fuel_price",
        data_file_fpath=outputs_h5,
        dataset_key="fuel_price",
        placeholders={"solve_year": 2032, "weather_year": 2012},
    )

    assert result is None


def test_read_outputs_csv_fallback_required_missing_raises(tmp_path: Path, reeds_run_path: Path) -> None:
    """Required output datasets should raise when neither H5 nor CSV is available."""
    from r2x_core.datafile import DataFile, FileInfo

    parser = _build_parser(reeds_run_path)
    outputs_h5 = tmp_path / "outputs.h5"
    outputs_h5.touch()

    parser.store._cache["required_out"] = DataFile(
        name="required_out",
        fpath=outputs_h5,
        info=FileInfo(description="required", is_input=False, is_optional=False),
    )

    with pytest.raises(FileNotFoundError):
        parser._read_outputs_csv_fallback(
            name="required_out",
            data_file_fpath=outputs_h5,
            dataset_key="required_out",
            placeholders={"solve_year": 2032, "weather_year": 2012},
        )


def test_decode_h5_scalar_and_close_handle(tmp_path: Path, reeds_run_path: Path) -> None:
    """Scalar decoding and explicit handle close should clean parser H5 state."""
    parser = _build_parser(reeds_run_path)
    h5_path = tmp_path / "outputs.h5"
    with h5py.File(h5_path, "w") as h5_file:
        group = h5_file.create_group("fuel_price")
        group.create_dataset("columns", data=np.array([b"i", b"r", b"Value"]))
        group.create_dataset("Value", data=np.array([1.0]))
        group.create_dataset("i", data=np.array([b"tech1"]))
        group.create_dataset("r", data=np.array([b"p1"]))

    assert parser._decode_h5_scalar(b"abc") == "abc"
    assert parser._decode_h5_scalar(np.bytes_(b"xyz")) == "xyz"
    assert parser._decode_h5_scalar(123) == 123

    assert parser._read_outputs_h5_group(h5_path, "fuel_price") is not None
    assert parser._outputs_h5_handle is not None
    assert parser._outputs_h5_cache

    parser._close_outputs_h5()

    assert parser._outputs_h5_handle is None
    assert parser._outputs_h5_cache == {}
