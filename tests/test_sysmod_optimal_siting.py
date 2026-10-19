from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
import pytest
from infrasys import SingleTimeSeries, System
from rust_ok import Err, Ok

from r2x_reeds.models.components import ReEDSDemand, ReEDSRegion
from r2x_reeds.sysmod import optimal_siting

pytestmark = [pytest.mark.integration]


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


def test_optimal_siting_returns_err_when_expand_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system, _, _ = _build_system_with_loads()

    loadsite_path = _write_csv(
        tmp_path / "loadsite_op.csv",
        {
            "r": ["p4"],
            "allh": ["h1"],
            "t": [2032],
            "Value": [1.0],
        },
    )
    hour_map_path = _write_csv(
        tmp_path / "hmap_myr.csv",
        {
            "yearhour": [1],
            "h": ["h1"],
        },
    )

    def _boom_expand(values: pl.DataFrame, grid: pl.DataFrame, **kwargs: Any):
        del values, grid, kwargs
        return Err(ValueError("failed to expand"))

    monkeypatch.setattr(optimal_siting, "expand_keyed_grid", _boom_expand)

    result = optimal_siting.add_optimal_siting(
        system,
        optimal_siting.OptimalSitingConfig(
            loadsite_op_fpath=loadsite_path,
            hour_map_myr_fpath=hour_map_path,
            solve_year=2032,
        ),
    )

    assert result.is_err()
    assert "failed to expand" in str(result.unwrap_err())


def test_optimal_siting_handles_exception_from_data_store(monkeypatch: pytest.MonkeyPatch) -> None:
    system, _, _ = _build_system_with_loads()

    def _raise_load_file(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise RuntimeError("store exploded")

    monkeypatch.setattr(optimal_siting.DataStore, "load_file", _raise_load_file)

    result = optimal_siting.add_optimal_siting(
        system,
        optimal_siting.OptimalSitingConfig(
            loadsite_op_fpath="fake.csv",
            hour_map_myr_fpath="fake2.csv",
            solve_year=2032,
        ),
    )

    assert result.is_err()
    assert "store exploded" in str(result.unwrap_err())


def test_load_and_prepare_frames_handles_lazy_frames(monkeypatch: pytest.MonkeyPatch) -> None:
    loadsite_df = pl.DataFrame({"r": ["p4"], "allh": ["h1"], "t": [2032], "Value": [10.0]})
    hour_map_df = pl.DataFrame({"yearhour": [1], "h": ["h1"]})

    calls = [loadsite_df.lazy(), hour_map_df.lazy()]

    def _mock_load_file(*args: Any, **kwargs: Any) -> pl.LazyFrame:
        del args, kwargs
        return calls.pop(0)

    monkeypatch.setattr(optimal_siting.DataStore, "load_file", _mock_load_file)

    config = optimal_siting.OptimalSitingConfig(
        loadsite_op_fpath="load.csv",
        hour_map_myr_fpath="hmap.csv",
        solve_year=[2032],
    )
    prepared = optimal_siting._load_and_prepare_frames(config)

    assert prepared is not None
    loadsite, hour_map = prepared
    assert loadsite.columns == ["region", "hour_period", "year", "value"]
    assert hour_map.columns == ["sequential_hour", "hour_period"]


def test_load_and_prepare_frames_returns_none_when_filtered_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    loadsite_df = pl.DataFrame({"r": ["p4"], "allh": ["h1"], "t": [2040], "Value": [10.0]})
    hour_map_df = pl.DataFrame({"yearhour": [1], "h": ["h1"]})

    calls = [loadsite_df, hour_map_df]

    def _mock_load_file(*args: Any, **kwargs: Any) -> pl.DataFrame:
        del args, kwargs
        return calls.pop(0)

    monkeypatch.setattr(optimal_siting.DataStore, "load_file", _mock_load_file)

    config = optimal_siting.OptimalSitingConfig(
        loadsite_op_fpath="load.csv",
        hour_map_myr_fpath="hmap.csv",
        solve_year=2032,
    )
    assert optimal_siting._load_and_prepare_frames(config) is None


def test_load_and_prepare_frames_returns_none_on_empty_frames(monkeypatch: pytest.MonkeyPatch) -> None:
    empty = pl.DataFrame({"r": [], "allh": [], "t": [], "Value": []}, schema_overrides={"r": pl.String})
    hour_map_df = pl.DataFrame({"yearhour": [1], "h": ["h1"]})

    calls = [empty, hour_map_df]

    def _mock_load_file(*args: Any, **kwargs: Any) -> pl.DataFrame:
        del args, kwargs
        return calls.pop(0)

    monkeypatch.setattr(optimal_siting.DataStore, "load_file", _mock_load_file)

    config = optimal_siting.OptimalSitingConfig(
        loadsite_op_fpath="load.csv",
        hour_map_myr_fpath="hmap.csv",
    )
    assert optimal_siting._load_and_prepare_frames(config) is None


def test_build_region_increments_empty_expand(monkeypatch: pytest.MonkeyPatch) -> None:
    def _mock_expand(values: pl.DataFrame, grid: pl.DataFrame, **kwargs: Any):
        del values, grid, kwargs
        return Ok(pl.DataFrame({"region": [], "sequential_hour": [], "value": []}))

    monkeypatch.setattr(optimal_siting, "expand_keyed_grid", _mock_expand)

    result = optimal_siting._build_region_increments(pl.DataFrame(), pl.DataFrame())
    assert result.is_ok()
    assert result.unwrap() == {}


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
