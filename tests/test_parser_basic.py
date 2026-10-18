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

from tests.fixtures.data_fixtures import package_file_mapping

pytestmark = [pytest.mark.integration]

if TYPE_CHECKING:
    pass


def build_parser(
    run_path: Path,
    *,
    use_degraded_capacity: bool = False,
    file_mapping: dict[str, object] | None = None,
):
    from r2x_core import DataStore, PluginContext
    from r2x_reeds import ReEDSConfig, ReEDSParser
    from tests.fixtures.data_fixtures import csv_file_mapping

    selected_mapping = csv_file_mapping() if file_mapping is None else file_mapping
    config = ReEDSConfig(
        solve_year=2032,
        weather_year=2012,
        case_name="test",
        scenario="base",
        use_degraded_capacity=use_degraded_capacity,
        asset_overrides={"file_mapping": selected_mapping},
    )
    store = DataStore.from_plugin_config(config, path=run_path)
    ctx = PluginContext(config=config, store=store)
    return ReEDSParser.from_context(ctx)


def write_minimal_outputs_h5_from_fuel_price(csv_path: Path, h5_path: Path) -> None:
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


def write_fuel2tech_outputs_h5(h5_path: Path) -> None:
    """Create a ReEDS-style fuel2tech group without generic table metadata."""
    with h5py.File(h5_path, "w") as h5_file:
        group = h5_file.create_group("fuel2tech")
        group.create_dataset("f", data=np.array(["ngas", "coal"], dtype="S"))
        group.create_dataset("i", data=np.array(["gas-cc", "coal"], dtype="S"))


def test_read_data_file_uses_explicit_csv_mapping(reeds_run_path: Path) -> None:
    """Explicit CSV file mappings read the CSV outputs in the unpacked test archive."""
    parser = build_parser(reeds_run_path)

    result = parser.read_data_file("fuel_price")

    assert result is not None
    df = result.collect()
    assert not df.is_empty()
    assert {"technology", "region", "year", "fuel_price"}.issubset(set(df.columns))


def test_datastore_reads_configured_h5_output_group(tmp_path: Path, reeds_run_path: Path) -> None:
    """File mapping HDF5 settings support direct DataStore reads."""
    run_path = tmp_path / "test_Pacific"
    shutil.copytree(reeds_run_path, run_path)

    outputs_dir = run_path / "outputs"
    fuel_price_csv = outputs_dir / "fuel_price.csv"
    pl.DataFrame({"i": ["NGAS"], "r": ["P1"], "t": [2032], "value": [4.2]}).write_csv(fuel_price_csv)
    outputs_h5 = outputs_dir / "outputs.h5"
    write_minimal_outputs_h5_from_fuel_price(fuel_price_csv, outputs_h5)
    fuel_price_csv.unlink()

    parser = build_parser(run_path, file_mapping=package_file_mapping())
    result = parser.store.read_data("fuel_price", placeholders={"solve_year": 2032, "weather_year": 2012})

    assert result is not None
    frame = result.collect()
    assert frame.select("technology", "region", "fuel_price").to_dict(as_series=False) == {
        "technology": ["ngas"],
        "region": ["p1"],
        "fuel_price": [4.2],
    }


def test_read_data_file_uses_outputs_h5_and_not_csv(tmp_path: Path, reeds_run_path: Path) -> None:
    """Parser should read output datasets from outputs.h5 when available."""
    run_path = tmp_path / "test_Pacific"
    shutil.copytree(reeds_run_path, run_path)

    outputs_dir = run_path / "outputs"
    fuel_price_csv = outputs_dir / "fuel_price.csv"
    pl.DataFrame({"i": ["NGAS"], "r": ["P1"], "t": [2032], "value": [4.2]}).write_csv(fuel_price_csv)
    outputs_h5 = outputs_dir / "outputs.h5"

    write_minimal_outputs_h5_from_fuel_price(fuel_price_csv, outputs_h5)
    fuel_price_csv.unlink()

    parser = build_parser(run_path, file_mapping=package_file_mapping())
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

    parser = build_parser(run_path, use_degraded_capacity=True, file_mapping=package_file_mapping())
    result = parser.read_data_file("online_capacity")

    assert result is not None
    assert result.collect().to_dict(as_series=False) == {
        "technology": ["wind-ons"],
        "region": ["p4"],
        "year": [2032],
        "vintage": [2020],
        "capacity": [95.0],
    }


def test_read_data_file_uses_explicit_degraded_capacity_csv_mapping(
    tmp_path: Path, reeds_run_path: Path
) -> None:
    """The degraded-capacity flag selects the configured cap_deg_ivrt.csv mapping."""
    run_path = tmp_path / "test_Pacific"
    shutil.copytree(reeds_run_path, run_path)

    outputs_dir = run_path / "outputs"
    pl.DataFrame(
        {
            "i": ["wind-ons"],
            "r": ["p4"],
            "t": [2032],
            "v": [2020],
            "Value": [95.0],
        }
    ).write_csv(outputs_dir / "cap_deg_ivrt.csv")

    parser = build_parser(run_path, use_degraded_capacity=True)
    result = parser.read_data_file("online_capacity")

    assert result is not None
    assert result.collect().to_dict(as_series=False)["capacity"] == [95.0]


def test_read_data_file_reports_missing_degraded_capacity(tmp_path: Path, reeds_run_path: Path) -> None:
    """Missing degraded capacity must identify cap_deg_ivrt instead of returning None."""
    run_path = tmp_path / "test_Pacific"
    shutil.copytree(reeds_run_path, run_path)

    parser = build_parser(run_path, use_degraded_capacity=True)
    with pytest.raises(FileNotFoundError, match="cap_deg_ivrt"):
        parser.read_data_file("online_capacity")


def test_modeled_years_mapping_reads_headerless_csv(tmp_path: Path) -> None:
    import json

    from r2x_core import DataStore
    from r2x_reeds import ReEDSConfig

    input_case = tmp_path / "inputs_case"
    input_case.mkdir()
    (input_case / "modeledyears.csv").write_text("2010,2020,2030\n")
    mapping_path = Path(__file__).parents[1] / "src" / "r2x_reeds" / "config" / "file_mapping.json"
    mapping = json.loads(mapping_path.read_text())
    modeled_years = next(item for item in mapping["files"] if item["name"] == "modeled_years")
    config = ReEDSConfig(
        solve_year=2032,
        weather_year=2012,
        case_name="test",
        scenario="base",
        asset_overrides={"file_mapping": {"files": [modeled_years], "tables": []}},
    )
    store = DataStore.from_plugin_config(config, path=tmp_path)

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
    write_fuel2tech_outputs_h5(outputs_h5)

    parser = build_parser(run_path, file_mapping=package_file_mapping())
    result = parser.read_data_file("fuel_tech_map")

    assert result is not None
    assert result.collect().to_dict(as_series=False) == {
        "fuel_type": ["ngas", "coal"],
        "technology": ["gas-cc", "coal"],
    }


def test_read_data_file_uses_store_for_non_outputs_dataset(reeds_run_path: Path) -> None:
    """Non-output mappings should still be read through DataStore directly."""
    parser = build_parser(reeds_run_path)

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
    records = json.loads(mapping_path.read_text())["files"]
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
    records = json.loads(mapping_path.read_text())["files"]
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
    records = json.loads(mapping_path.read_text())["files"]
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
    records = json.loads(mapping_path.read_text())["files"]
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
