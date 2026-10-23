from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np
import polars as pl
import pytest
from infrasys import System

from r2x_reeds.models.components import (
    ReEDSDataCenterDemand,
    ReEDSElectrolyzerDemand,
    ReEDSRegion,
    ReEDSSteamMethaneReformingDemand,
)
from r2x_reeds.sysmod import purchaser_load

pytestmark = [pytest.mark.integration, pytest.mark.polars]


def _build_system() -> tuple[System, ReEDSRegion, ReEDSRegion]:
    system = System(name="test_purchaser_load")
    p4 = ReEDSRegion(name="p4")
    p5 = ReEDSRegion(name="p5")
    system.add_component(p4)
    system.add_component(p5)
    return system, p4, p5


def _write_csv(path: Path, data: dict[str, list]) -> str:
    pl.DataFrame(data).write_csv(path)
    return str(path)


def _run_modifier(system: System, **kwargs) -> System:
    result = purchaser_load.add_purchaser_load(system, purchaser_load.PurchaserLoadConfig(**kwargs))
    assert result.is_ok()
    return result.unwrap()


def test_datastore_mapped_purchaser_columns_are_supported() -> None:
    capacity = pl.DataFrame(
        {"technology": ["electrolyzer"], "region": ["p4"], "year": [2032], "capacity": [1.0]}
    )
    consume_char = pl.DataFrame(
        {
            "technology": ["electrolyzer"],
            "year": [2032],
            "parameter": ["electricity_efficiency"],
            "value": [1.0],
        }
    )
    profile = pl.DataFrame(
        {
            "technology": ["electrolyzer"],
            "region": ["p4"],
            "hour_period": ["h1"],
            "year": [2032],
            "value": [1.0],
        }
    )
    annual = pl.DataFrame({"technology": ["electrolyzer"], "region": ["p4"], "year": [2032], "value": [1.0]})

    assert purchaser_load._rename_existing_columns(capacity, {"i": "technology", "r": "region"}).equals(
        capacity
    )
    assert purchaser_load._rename_existing_columns(consume_char, {"*i": "technology", "t": "year"}).equals(
        consume_char
    )
    assert purchaser_load._rename_existing_columns(
        profile, {"i": "technology", "r": "region", "allh": "hour_period", "Value": "value", "t": "year"}
    ).equals(profile)
    assert purchaser_load._rename_existing_columns(
        annual, {"i": "technology", "r": "region", "Value": "value", "t": "year"}
    ).equals(annual)


def test_purchaser_load_reads_reeds_outputs_h5_groups(tmp_path: Path) -> None:
    outputs_h5 = tmp_path / "outputs.h5"
    with h5py.File(outputs_h5, "w") as h5_file:
        group = h5_file.create_group("cap")
        group.create_dataset("columns", data=np.array([b"i", b"r", b"t", b"Value"]))
        group.create_dataset("i", data=np.array([b"electrolyzer"]))
        group.create_dataset("r", data=np.array([b"p4"]))
        group.create_dataset("t", data=np.array([2032]))
        group.create_dataset("Value", data=np.array([120.0]))

    frame = purchaser_load._read_optional_frame(outputs_h5, "hydrogen_production_capacity")

    assert frame is not None
    assert frame.to_dict(as_series=False) == {
        "i": ["electrolyzer"],
        "r": ["p4"],
        "t": [2032],
        "Value": [120.0],
    }


def test_purchaser_load_scope_full_flow(tmp_path: Path) -> None:
    system, _, _ = _build_system()

    hour_map_myr_path = _write_csv(
        tmp_path / "hmap_myr.csv",
        {
            "yearhour": [1, 2, 3],
            "h": ["h1", "h2", "h3"],
        },
    )
    hydrogen_production_capacity_path = _write_csv(
        tmp_path / "cap.csv",
        {
            "i": ["electrolyzer"],
            "r": ["p4"],
            "t": [2032],
            "Value": [120.0],
        },
    )
    consume_char_path = _write_csv(
        tmp_path / "consume_char.csv",
        {
            "*i": ["electrolyzer"],
            "t": [2032],
            "parameter": ["electricity_efficiency"],
            "value": [1.25],
        },
    )
    hydrogen_production_load_path = _write_csv(
        tmp_path / "prod_load.csv",
        {
            "i": ["electrolyzer", "electrolyzer", "electrolyzer"],
            "r": ["p4", "p4", "p4"],
            "allh": ["h1", "h2", "h3"],
            "t": [2032, 2032, 2032],
            "Value": [50.0, 40.0, 30.0],
        },
    )
    hydrogen_production_annual_load_path = _write_csv(
        tmp_path / "prod_load_ann.csv",
        {
            "i": ["electrolyzer"],
            "r": ["p4"],
            "t": [2032],
            "Value": [360.0],
        },
    )
    loadsite_op_path = _write_csv(
        tmp_path / "loadsite_op.csv",
        {
            "r": ["p4", "p4", "p4", "p5", "p5", "p5", "p4"],
            "allh": ["h1", "h2", "h3", "h1", "h2", "h3", "h1"],
            "t": [2032, 2032, 2032, 2032, 2032, 2032, 2040],
            "Value": [500.0, 500.0, 500.0, 300.0, 300.0, 300.0, 999.0],
        },
    )

    _run_modifier(
        system,
        solve_year=2032,
        weather_year=2012,
        hour_map_myr_fpath=hour_map_myr_path,
        hydrogen_production_capacity_fpath=hydrogen_production_capacity_path,
        consume_characteristics_fpath=consume_char_path,
        hydrogen_production_load_fpath=hydrogen_production_load_path,
        hydrogen_production_annual_load_fpath=hydrogen_production_annual_load_path,
        loadsite_op_fpath=loadsite_op_path,
    )

    electrolyzer_demand = system.get_component(ReEDSElectrolyzerDemand, "p4_electrolyzer_demand")
    assert electrolyzer_demand.capacity == pytest.approx(120.0)
    assert electrolyzer_demand.electricity_efficiency == pytest.approx(1.25)

    data_center_p4 = system.get_component(ReEDSDataCenterDemand, "p4_data_center_demand")
    data_center_p5 = system.get_component(ReEDSDataCenterDemand, "p5_data_center_demand")
    assert data_center_p4.capacity == pytest.approx(500.0)
    assert data_center_p5.capacity == pytest.approx(300.0)

    electrolyzer_ts = system.get_time_series(electrolyzer_demand).data
    # Profile [50, 40, 30] scaled so annual total equals 360.
    np.testing.assert_allclose(electrolyzer_ts, np.array([150.0, 120.0, 90.0]), rtol=1e-5)

    p4_ts = system.get_time_series(data_center_p4).data
    p5_ts = system.get_time_series(data_center_p5).data
    np.testing.assert_allclose(p4_ts, np.array([500.0, 500.0, 500.0]), rtol=1e-5)
    np.testing.assert_allclose(p5_ts, np.array([300.0, 300.0, 300.0]), rtol=1e-5)


def test_purchaser_load_creates_smr_purchasers_with_profiles(tmp_path: Path) -> None:
    """ReEDS capacity and production load create profiled SMR purchasers."""
    system, _, _ = _build_system()
    hour_map_myr_path = _write_csv(
        tmp_path / "hmap_myr.csv",
        {"yearhour": [1, 2, 3], "h": ["h1", "h2", "h3"]},
    )
    hydrogen_production_capacity_path = _write_csv(
        tmp_path / "cap.csv",
        {
            "i": ["smr", "smr_ccs"],
            "r": ["p4", "p4"],
            "t": [2032, 2032],
            "Value": [100.0, 25.0],
        },
    )
    consume_char_path = _write_csv(
        tmp_path / "consume_char.csv",
        {
            "*i": ["smr", "smr_ccs"],
            "t": [2032, 2032],
            "parameter": ["electricity_efficiency", "electricity_efficiency"],
            "value": [0.88, 1.9],
        },
    )
    hydrogen_production_load_path = _write_csv(
        tmp_path / "prod_load.csv",
        {
            "i": ["smr", "smr", "smr", "smr_ccs", "smr_ccs", "smr_ccs"],
            "r": ["p4", "p4", "p4", "p4", "p4", "p4"],
            "allh": ["h1", "h2", "h3", "h1", "h2", "h3"],
            "t": [2032, 2032, 2032, 2032, 2032, 2032],
            "Value": [10.0, 20.0, 30.0, 5.0, 5.0, 10.0],
        },
    )
    hydrogen_production_annual_load_path = _write_csv(
        tmp_path / "prod_load_ann.csv",
        {
            "i": ["smr", "smr_ccs"],
            "r": ["p4", "p4"],
            "t": [2032, 2032],
            "Value": [120.0, 40.0],
        },
    )

    _run_modifier(
        system,
        solve_year=2032,
        hour_map_myr_fpath=hour_map_myr_path,
        hydrogen_production_capacity_fpath=hydrogen_production_capacity_path,
        consume_characteristics_fpath=consume_char_path,
        hydrogen_production_load_fpath=hydrogen_production_load_path,
        hydrogen_production_annual_load_fpath=hydrogen_production_annual_load_path,
    )

    smr = system.get_component(ReEDSSteamMethaneReformingDemand, "p4_smr_demand")
    smr_ccs = system.get_component(ReEDSSteamMethaneReformingDemand, "p4_smr_ccs_demand")
    assert smr.technology == "smr"
    assert smr.capacity == pytest.approx(100.0)
    assert smr.electricity_efficiency == pytest.approx(0.88)
    assert smr_ccs.technology == "smr_ccs"
    assert smr_ccs.capacity == pytest.approx(25.0)
    assert smr_ccs.electricity_efficiency == pytest.approx(1.9)
    np.testing.assert_allclose(system.get_time_series(smr).data, np.array([20.0, 40.0, 60.0]))
    np.testing.assert_allclose(system.get_time_series(smr_ccs).data, np.array([10.0, 10.0, 20.0]))


def test_purchaser_load_scope_missing_hour_map(tmp_path: Path, caplog) -> None:
    system, _, _ = _build_system()
    loadsite_op_path = _write_csv(
        tmp_path / "loadsite_op.csv",
        {
            "r": ["p4"],
            "allh": ["h1"],
            "t": [2032],
            "Value": [500.0],
        },
    )

    _run_modifier(system, solve_year=2032, loadsite_op_fpath=loadsite_op_path, hour_map_myr_fpath=None)

    assert "Missing hour_map_myr input" in caplog.text
    assert not list(system.get_components(ReEDSDataCenterDemand))


def test_purchaser_load_skips_electrolyzer_creation_when_existing(tmp_path: Path) -> None:
    """Per-region duplicate check skips cap.csv creation when that exact component already exists."""
    system, p4, _ = _build_system()

    existing = ReEDSElectrolyzerDemand(
        name="p4_electrolyzer_demand",
        region=p4,
        technology="electrolyzer",
        capacity=200.0,
        electricity_efficiency=1.0,
    )
    system.add_component(existing)

    hour_map_myr_path = _write_csv(
        tmp_path / "hmap_myr.csv",
        {
            "yearhour": [1, 2, 3],
            "h": ["h1", "h2", "h3"],
        },
    )
    hydrogen_production_capacity_path = _write_csv(
        tmp_path / "cap.csv",
        {
            "i": ["electrolyzer"],
            "r": ["p4"],
            "t": [2032],
            "Value": [120.0],
        },
    )
    hydrogen_production_load_path = _write_csv(
        tmp_path / "prod_load.csv",
        {
            "i": ["electrolyzer", "electrolyzer", "electrolyzer"],
            "r": ["p4", "p4", "p4"],
            "allh": ["h1", "h2", "h3"],
            "t": [2032, 2032, 2032],
            "Value": [10.0, 20.0, 30.0],
        },
    )

    _run_modifier(
        system,
        solve_year=2032,
        weather_year=2012,
        hour_map_myr_fpath=hour_map_myr_path,
        hydrogen_production_capacity_fpath=hydrogen_production_capacity_path,
        hydrogen_production_load_fpath=hydrogen_production_load_path,
    )

    electrolyzers = list(system.get_components(ReEDSElectrolyzerDemand))
    assert len(electrolyzers) == 1
    assert electrolyzers[0].name == "p4_electrolyzer_demand"
    # Pre-existing capacity must be unchanged (cap.csv row was skipped).
    assert electrolyzers[0].capacity == pytest.approx(200.0)

    ts = system.get_time_series(electrolyzers[0]).data
    np.testing.assert_allclose(ts, np.array([10.0, 20.0, 30.0]), rtol=1e-5)


def test_purchaser_load_creates_missing_region_when_other_exists(tmp_path: Path) -> None:
    """Regression: an existing p4 electrolyzer must not prevent p5 from being created.

    The old implementation skipped *all* cap.csv-based creation as soon as any
    ReEDSElectrolyzerDemand was found in the system.  This test would have
    failed under that logic because p5_electrolyzer_demand would never be added.
    """
    system, p4, _ = _build_system()

    existing_p4 = ReEDSElectrolyzerDemand(
        name="p4_electrolyzer_demand",
        region=p4,
        technology="electrolyzer",
        capacity=200.0,
        electricity_efficiency=1.0,
    )
    system.add_component(existing_p4)

    hour_map_myr_path = _write_csv(
        tmp_path / "hmap_myr.csv",
        {
            "yearhour": [1, 2, 3],
            "h": ["h1", "h2", "h3"],
        },
    )
    # cap.csv lists both p4 (already exists) and p5 (new).
    hydrogen_production_capacity_path = _write_csv(
        tmp_path / "cap.csv",
        {
            "i": ["electrolyzer", "electrolyzer"],
            "r": ["p4", "p5"],
            "t": [2032, 2032],
            "Value": [120.0, 80.0],
        },
    )

    _run_modifier(
        system,
        solve_year=2032,
        weather_year=2012,
        hour_map_myr_fpath=hour_map_myr_path,
        hydrogen_production_capacity_fpath=hydrogen_production_capacity_path,
    )

    electrolyzers = {c.name: c for c in system.get_components(ReEDSElectrolyzerDemand)}
    assert len(electrolyzers) == 2, "Both p4 and p5 demand components should exist"

    # Pre-existing p4 component must be unchanged.
    assert electrolyzers["p4_electrolyzer_demand"].capacity == pytest.approx(200.0)

    # New p5 component must have been created from cap.csv.
    assert "p5_electrolyzer_demand" in electrolyzers
    assert electrolyzers["p5_electrolyzer_demand"].capacity == pytest.approx(80.0)
