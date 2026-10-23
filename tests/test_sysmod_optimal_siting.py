from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import numpy as np
import polars as pl
import pytest
from infrasys import SingleTimeSeries, System
from r2x_reeds.models.components import ReEDSDemand, ReEDSRegion
from r2x_reeds.sysmod import optimal_siting

pytestmark = [pytest.mark.integration, pytest.mark.polars]


def _build_system_with_loads() -> tuple[System, dict[str, ReEDSDemand], np.ndarray]:
    system = System(name="test_optimal_siting")
    base_profile = np.array([100.0, 110.0, 120.0], dtype=np.float64)

    demands: dict[str, ReEDSDemand] = {}
    for region_name in ("p1", "p4", "p5"):
        region = ReEDSRegion(name=region_name)
        system.add_component(region)
        demand = ReEDSDemand(name=f"{region_name}_load", region=region, max_active_power=200.0)
        system.add_component(demand)

        ts = SingleTimeSeries.from_array(
            data=base_profile.copy(),
            name="max_active_power",
            initial_timestamp=datetime(2012, 1, 1),
            resolution=timedelta(hours=1),
        )
        system.add_time_series(ts, demand)
        demands[region_name] = demand

    return system, demands, base_profile


def _write_csv(path: Path, data: dict[str, list]) -> str:
    pl.DataFrame(data).write_csv(path)
    return str(path)


def _run_optimal_siting(system: System, **kwargs) -> System:
    result = optimal_siting.add_optimal_siting(system, optimal_siting.OptimalSitingConfig(**kwargs))
    assert result.is_ok()
    return result.unwrap()


def test_optimal_siting_applies_increments_with_solve_year_filter(tmp_path: Path) -> None:
    system, demands, base_profile = _build_system_with_loads()

    loadsite_path = _write_csv(
        tmp_path / "loadsite_op.csv",
        {
            "r": ["p4", "p4", "p4", "p5", "p5", "p5", "p4", "p4", "p4"],
            "allh": ["h1", "h2", "h3", "h1", "h2", "h3", "h1", "h2", "h3"],
            "t": [2032, 2032, 2032, 2032, 2032, 2032, 2040, 2040, 2040],
            "Value": [500.0, 500.0, 500.0, 300.0, 300.0, 300.0, 999.0, 999.0, 999.0],
        },
    )
    hour_map_path = _write_csv(
        tmp_path / "hmap_myr.csv",
        {
            "yearhour": [1, 2, 3],
            "h": ["h1", "h2", "h3"],
        },
    )

    _run_optimal_siting(
        system,
        loadsite_op_fpath=loadsite_path,
        hour_map_myr_fpath=hour_map_path,
        solve_year=2032,
    )

    p4_profile = system.get_time_series(demands["p4"]).data
    p5_profile = system.get_time_series(demands["p5"]).data
    p1_profile = system.get_time_series(demands["p1"]).data

    np.testing.assert_allclose(p4_profile, base_profile + 500.0, atol=1e-6)
    np.testing.assert_allclose(p5_profile, base_profile + 300.0, atol=1e-6)
    np.testing.assert_allclose(p1_profile, base_profile, atol=1e-6)


def test_optimal_siting_skips_when_paths_missing(caplog) -> None:
    system, demands, base_profile = _build_system_with_loads()

    _run_optimal_siting(system)

    np.testing.assert_allclose(system.get_time_series(demands["p4"]).data, base_profile, atol=1e-6)
    assert "Missing loadsite_op_fpath or hour_map_myr_fpath" in caplog.text


def test_optimal_siting_returns_missing_configured_file_error(tmp_path: Path) -> None:
    system, _, _ = _build_system_with_loads()

    result = optimal_siting.add_optimal_siting(
        system,
        optimal_siting.OptimalSitingConfig(
            loadsite_op_fpath=tmp_path / "missing-loadsite.csv",
            hour_map_myr_fpath=tmp_path / "missing-hour-map.csv",
        ),
    )

    assert result.is_err()
    assert isinstance(result.unwrap_err(), FileNotFoundError)
    assert str(result.unwrap_err()).endswith("missing-loadsite.csv")


def test_optimal_siting_skips_load_without_time_series(tmp_path: Path) -> None:
    system = System(name="test_optimal_siting_missing_ts")
    region = ReEDSRegion(name="p4")
    system.add_component(region)
    demand = ReEDSDemand(name="p4_load", region=region, max_active_power=100.0)
    system.add_component(demand)

    loadsite_path = _write_csv(
        tmp_path / "loadsite_op.csv",
        {
            "r": ["p4"],
            "allh": ["h1"],
            "t": [2032],
            "Value": [500.0],
        },
    )
    hour_map_path = _write_csv(
        tmp_path / "hmap_myr.csv",
        {
            "yearhour": [1],
            "h": ["h1"],
        },
    )

    result = optimal_siting.add_optimal_siting(
        system,
        optimal_siting.OptimalSitingConfig(
            loadsite_op_fpath=loadsite_path,
            hour_map_myr_fpath=hour_map_path,
            solve_year=2032,
        ),
    )
    assert result.is_ok()
    assert system.has_time_series(demand) is False


def test_optimal_siting_returns_err_for_duplicate_region_hour_keys(tmp_path: Path) -> None:
    system, _, _ = _build_system_with_loads()
    loadsite_path = _write_csv(
        tmp_path / "loadsite_op.csv",
        {"r": ["p4", "p4"], "allh": ["h1", "h1"], "t": [2032, 2032], "Value": [1.0, 2.0]},
    )
    hour_map_path = _write_csv(tmp_path / "hmap_myr.csv", {"yearhour": [1], "h": ["h1"]})

    result = optimal_siting.add_optimal_siting(
        system,
        optimal_siting.OptimalSitingConfig(
            loadsite_op_fpath=loadsite_path,
            hour_map_myr_fpath=hour_map_path,
            solve_year=2032,
        ),
    )

    assert result.is_err()
    assert isinstance(result.unwrap_err(), ValueError)
    assert "duplicate region/hour-period keys" in str(result.unwrap_err())


def test_optimal_siting_returns_original_error_for_malformed_csv(tmp_path: Path) -> None:
    system, _, _ = _build_system_with_loads()
    loadsite_path = _write_csv(tmp_path / "loadsite_op.csv", {"unexpected": [1]})
    hour_map_path = _write_csv(tmp_path / "hmap_myr.csv", {"yearhour": [1], "h": ["h1"]})

    result = optimal_siting.add_optimal_siting(
        system,
        optimal_siting.OptimalSitingConfig(
            loadsite_op_fpath=loadsite_path,
            hour_map_myr_fpath=hour_map_path,
            solve_year=2032,
        ),
    )

    assert result.is_err()
    assert isinstance(result.unwrap_err(), pl.exceptions.PolarsError)


def test_load_and_prepare_frames_reads_csv_sources(tmp_path: Path) -> None:
    loadsite_path = _write_csv(
        tmp_path / "load.csv", {"r": ["p4"], "allh": ["h1"], "t": [2032], "Value": [10.0]}
    )
    hour_map_path = _write_csv(tmp_path / "hmap.csv", {"yearhour": [1], "h": ["h1"]})
    config = optimal_siting.OptimalSitingConfig(
        loadsite_op_fpath=loadsite_path,
        hour_map_myr_fpath=hour_map_path,
        solve_year=[2032],
    )

    prepared = optimal_siting._load_and_prepare_frames(config)

    assert prepared is not None
    loadsite, hour_map = prepared
    assert loadsite.columns == ["region", "hour_period", "year", "value"]
    assert hour_map.columns == ["sequential_hour", "hour_period"]


def test_load_and_prepare_frames_returns_none_when_filtered_empty(tmp_path: Path) -> None:
    loadsite_path = _write_csv(
        tmp_path / "load.csv", {"r": ["p4"], "allh": ["h1"], "t": [2040], "Value": [10.0]}
    )
    hour_map_path = _write_csv(tmp_path / "hmap.csv", {"yearhour": [1], "h": ["h1"]})
    config = optimal_siting.OptimalSitingConfig(
        loadsite_op_fpath=loadsite_path,
        hour_map_myr_fpath=hour_map_path,
        solve_year=2032,
    )

    assert optimal_siting._load_and_prepare_frames(config) is None


def test_load_and_prepare_frames_returns_none_on_empty_file(tmp_path: Path) -> None:
    loadsite_path = tmp_path / "load.csv"
    loadsite_path.write_text("r,allh,t,Value\\n", encoding="utf-8")
    hour_map_path = _write_csv(tmp_path / "hmap.csv", {"yearhour": [1], "h": ["h1"]})
    config = optimal_siting.OptimalSitingConfig(
        loadsite_op_fpath=loadsite_path,
        hour_map_myr_fpath=hour_map_path,
    )

    assert optimal_siting._load_and_prepare_frames(config) is None


def test_build_region_increments_returns_empty_for_empty_sources() -> None:
    loadsite = pl.DataFrame(
        schema={"region": pl.String, "hour_period": pl.String, "value": pl.Float64}
    )
    hour_map = pl.DataFrame(schema={"sequential_hour": pl.Int64, "hour_period": pl.String})

    assert optimal_siting._build_region_increments(loadsite, hour_map) == {}


def test_apply_increments_handles_min_len_zero() -> None:
    system = System(name="test_optimal_siting_zero_len")
    region = ReEDSRegion(name="p4")
    system.add_component(region)
    demand = ReEDSDemand(name="p4_load", region=region, max_active_power=10.0)
    system.add_component(demand)

    ts = SingleTimeSeries.from_array(
        data=np.array([10.0, 11.0], dtype=np.float64),
        name="max_active_power",
        initial_timestamp=datetime(2012, 1, 1),
        resolution=timedelta(hours=1),
    )
    system.add_time_series(ts, demand)

    updated = optimal_siting._apply_increments_to_demands(system, {"p4": np.array([], dtype=np.float64)})
    assert updated == 0


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ([], None),
        ([2035], 2035),
        (2036, 2036),
    ],
)
def test_resolve_solve_year(value: int | list[int] | None, expected: int | None) -> None:
    assert optimal_siting._resolve_solve_year(value) == expected
