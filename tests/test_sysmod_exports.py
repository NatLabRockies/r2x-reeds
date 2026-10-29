"""Tests for Canadian export time series."""

from datetime import datetime, timedelta
from pathlib import Path

import polars as pl
import pytest
from infrasys import SingleTimeSeries, System

from r2x_reeds.models.components import ReEDSDemand, ReEDSRegion
from r2x_reeds.sysmod.exports import ExportsConfig, add_exports

pytestmark = [pytest.mark.integration]


def _build_system() -> tuple[System, ReEDSDemand, ReEDSDemand]:
    system = System(name="test_exports")
    west = ReEDSRegion(name="west")
    east = ReEDSRegion(name="east")
    system.add_component(west)
    system.add_component(east)
    demands = []
    for region in (west, east):
        demand = ReEDSDemand(name=f"{region.name}_load", region=region, max_active_power=200.0)
        system.add_component(demand)
        time_series = SingleTimeSeries.from_array(
            data=[100.0, 110.0, 120.0, 130.0],
            name="max_active_power",
            initial_timestamp=datetime(2012, 1, 1),
            resolution=timedelta(hours=1),
        )
        system.add_time_series(time_series, demand)
        demands.append(demand)
    return system, demands[0], demands[1]


def _write_csv(path: Path, data: dict[str, list]) -> str:
    pl.DataFrame(data).write_csv(path)
    return str(path)


def _run_exports(system: System, **kwargs) -> System:
    result = add_exports(system, ExportsConfig(**kwargs))
    assert result.is_ok(), result.unwrap_err() if result.is_err() else ""
    return result.unwrap()


def _write_inputs(tmp_path: Path) -> dict[str, str]:
    return {
        "hour_map_fpath": _write_csv(
            tmp_path / "hmap_myr.csv",
            {
                "*timestamp": [
                    "2012-01-01 00:00:00-06:00",
                    "2012-01-01 01:00:00-06:00",
                    "2012-01-01 02:00:00-06:00",
                    "2012-01-01 03:00:00-06:00",
                ],
                "year": [2012, 2012, 2012, 2012],
                "h": ["h1", "h1", "h1", "h2"],
            },
        ),
        "canada_exports_h_frac_fpath": _write_csv(
            tmp_path / "can_exports_h_frac.csv",
            {"*h": ["h1", "h2"], "frac_weighted": [0.25, 0.75]},
        ),
        "canada_exports_fpath": _write_csv(
            tmp_path / "can_exports.csv",
            {"r": ["west", "east"], "2035": [4000.0, 8000.0], "2040": [2000.0, 6000.0]},
        ),
    }


def test_exports_select_year_and_region_and_expand_hourly_profile(tmp_path: Path) -> None:
    system, west_demand, east_demand = _build_system()
    inputs = _write_inputs(tmp_path)

    _run_exports(system, weather_year=2012, solve_year=2040, **inputs)

    west_series = system.get_time_series(west_demand, name="max_active_power")
    east_series = system.get_time_series(east_demand, name="max_active_power")
    assert west_series.initial_timestamp.year == 2012
    assert west_series.data.tolist() == pytest.approx(
        [100.0 + 2000 / 12, 110.0 + 2000 / 12, 120.0 + 2000 / 12, 1630.0]
    )
    assert east_series.data.tolist() == pytest.approx([100.0 + 500.0, 110.0 + 500.0, 120.0 + 500.0, 4630.0])
    assert sum(west_series.data.tolist()) - 460.0 == pytest.approx(2000.0)


def test_exports_accept_fraction_hours_from_other_mapped_years(tmp_path: Path) -> None:
    system, west_demand, _ = _build_system()
    inputs = _write_inputs(tmp_path)
    inputs["hour_map_fpath"] = _write_csv(
        tmp_path / "hmap_multi_year.csv",
        {
            "*timestamp": [
                "2011-01-01 00:00:00-06:00",
                "2012-01-01 00:00:00-06:00",
                "2012-01-01 01:00:00-06:00",
                "2012-01-01 02:00:00-06:00",
                "2012-01-01 03:00:00-06:00",
            ],
            "year": [2011, 2012, 2012, 2012, 2012],
            "h": ["h_other_year", "h1", "h1", "h1", "h2"],
        },
    )
    inputs["canada_exports_h_frac_fpath"] = _write_csv(
        tmp_path / "can_exports_h_frac_multi_year.csv",
        {"*h": ["h1", "h2", "h_other_year"], "frac_weighted": [0.25, 0.75, 0.5]},
    )

    _run_exports(system, weather_year=2012, solve_year=2040, **inputs)

    west_series = system.get_time_series(west_demand, name="max_active_power")
    assert west_series.data.tolist() == pytest.approx(
        [100.0 + 2000 / 12, 110.0 + 2000 / 12, 120.0 + 2000 / 12, 1630.0]
    )
    assert sum(west_series.data.tolist()) - 460.0 == pytest.approx(2000.0)


def test_exports_require_solve_year_for_wide_input(tmp_path: Path) -> None:
    system, _, _ = _build_system()
    inputs = _write_inputs(tmp_path)

    result = add_exports(system, ExportsConfig(weather_year=2012, **inputs))

    assert result.is_err()
    assert "Solve year is required" in result.unwrap_err()


def test_exports_reject_missing_solve_year_column(tmp_path: Path) -> None:
    system, _, _ = _build_system()
    inputs = _write_inputs(tmp_path)

    result = add_exports(system, ExportsConfig(weather_year=2012, solve_year=2045, **inputs))

    assert result.is_err()
    assert "does not contain a column for year 2045" in result.unwrap_err()


def test_exports_reject_duplicate_annual_region_rows(tmp_path: Path) -> None:
    system, _, _ = _build_system()
    inputs = _write_inputs(tmp_path)
    inputs["canada_exports_fpath"] = _write_csv(
        tmp_path / "can_exports_duplicate.csv",
        {"r": ["west", "west"], "2040": [2000.0, 1000.0]},
    )

    result = add_exports(system, ExportsConfig(weather_year=2012, solve_year=2040, **inputs))

    assert result.is_err()
    assert "multiple rows for region west" in result.unwrap_err()


def test_exports_reject_duplicate_demand_components(tmp_path: Path) -> None:
    system, west_demand, _ = _build_system()
    system.add_component(
        ReEDSDemand(name="west_duplicate_load", region=west_demand.region, max_active_power=200.0)
    )
    inputs = _write_inputs(tmp_path)

    result = add_exports(system, ExportsConfig(weather_year=2012, solve_year=2040, **inputs))

    assert result.is_err()
    assert "Multiple demand components found for region west" in result.unwrap_err()


def test_exports_ignore_electrolyzer_demand_in_same_region(tmp_path: Path) -> None:
    system, west_demand, _ = _build_system()
    electrolyzer_demand = ReEDSDemand(
        name="west_electrolyzer",
        region=west_demand.region,
        max_active_power=50.0,
        category="electrolyzer",
    )
    system.add_component(electrolyzer_demand)
    inputs = _write_inputs(tmp_path)

    _run_exports(system, weather_year=2012, solve_year=2040, **inputs)

    west_series = system.get_time_series(west_demand, name="max_active_power")
    assert sum(west_series.data.tolist()) - 460.0 == pytest.approx(2000.0)
    assert not system.has_time_series(electrolyzer_demand)


def test_exports_skip_regions_without_demand_components(tmp_path: Path, caplog) -> None:
    system = System(name="test_exports_without_demands")
    inputs = _write_inputs(tmp_path)

    _run_exports(system, weather_year=2012, solve_year=2040, **inputs)

    assert "No demand component found for export region west" in caplog.text
    assert "No demand component found for export region east" in caplog.text


def test_exports_skip_demand_without_existing_load_profile(tmp_path: Path, caplog) -> None:
    system, west_demand, east_demand = _build_system()
    system.remove_time_series(west_demand, name="max_active_power")
    unrelated_series = SingleTimeSeries.from_array(
        data=[1.0, 2.0, 3.0, 4.0],
        name="other_profile",
        initial_timestamp=datetime(2012, 1, 1),
        resolution=timedelta(hours=1),
    )
    system.add_time_series(unrelated_series, west_demand)
    inputs = _write_inputs(tmp_path)

    _run_exports(system, weather_year=2012, solve_year=2040, **inputs)

    assert "Demand component for export region west has no load profile" in caplog.text
    assert system.has_time_series(west_demand, name="other_profile")
    assert not system.has_time_series(west_demand, name="max_active_power")
    assert system.has_time_series(east_demand)


def test_exports_reject_different_load_and_export_profile_lengths(tmp_path: Path) -> None:
    system, west_demand, _ = _build_system()
    system.remove_time_series(west_demand, name="max_active_power")
    short_profile = SingleTimeSeries.from_array(
        data=[100.0, 110.0, 120.0],
        name="max_active_power",
        initial_timestamp=datetime(2012, 1, 1),
        resolution=timedelta(hours=1),
    )
    system.add_time_series(short_profile, west_demand)
    inputs = _write_inputs(tmp_path)

    result = add_exports(system, ExportsConfig(weather_year=2012, solve_year=2040, **inputs))

    assert result.is_err()
    assert "Load profile for region west has 3 hours" in result.unwrap_err()


def test_exports_reject_profile_hours_absent_from_hour_map(tmp_path: Path) -> None:
    system, _, _ = _build_system()
    inputs = _write_inputs(tmp_path)
    inputs["canada_exports_h_frac_fpath"] = _write_csv(
        tmp_path / "can_exports_h_frac_extra.csv",
        {"*h": ["h1", "h2", "unused"], "frac_weighted": [0.2, 0.3, 0.5]},
    )

    result = add_exports(system, ExportsConfig(weather_year=2012, solve_year=2040, **inputs))

    assert result.is_err()
    assert "hours absent from the hour map" in result.unwrap_err()


def test_exports_reject_negative_hourly_fraction(tmp_path: Path) -> None:
    system, _, _ = _build_system()
    inputs = _write_inputs(tmp_path)
    inputs["canada_exports_h_frac_fpath"] = _write_csv(
        tmp_path / "can_exports_h_frac_negative.csv",
        {"*h": ["h1", "h2"], "frac_weighted": [1.25, -0.25]},
    )

    result = add_exports(system, ExportsConfig(weather_year=2012, solve_year=2040, **inputs))

    assert result.is_err()
    assert "negative or non-finite values" in result.unwrap_err()


def test_exports_reject_negative_annual_energy(tmp_path: Path) -> None:
    system, _, _ = _build_system()
    inputs = _write_inputs(tmp_path)
    inputs["canada_exports_fpath"] = _write_csv(
        tmp_path / "can_exports_negative.csv",
        {"r": ["west"], "2040": [-1.0]},
    )

    result = add_exports(system, ExportsConfig(weather_year=2012, solve_year=2040, **inputs))

    assert result.is_err()
    assert "cannot be negative" in result.unwrap_err()


def test_exports_validation_error_does_not_partially_update_demands(tmp_path: Path) -> None:
    system, west_demand, east_demand = _build_system()
    west_before = system.get_time_series(west_demand, name="max_active_power").data.copy()
    east_before = system.get_time_series(east_demand, name="max_active_power").data.copy()
    inputs = _write_inputs(tmp_path)
    inputs["canada_exports_fpath"] = _write_csv(
        tmp_path / "can_exports_invalid_east.csv",
        {"r": ["west", "east"], "2040": [2000.0, -1.0]},
    )

    result = add_exports(system, ExportsConfig(weather_year=2012, solve_year=2040, **inputs))

    assert result.is_err()
    assert "Export energy for region east cannot be negative" in result.unwrap_err()
    assert system.get_time_series(west_demand, name="max_active_power").data.tolist() == west_before.tolist()
    assert system.get_time_series(east_demand, name="max_active_power").data.tolist() == east_before.tolist()


def test_exports_skip_when_required_files_are_missing(caplog) -> None:
    system, west_demand, _ = _build_system()

    _run_exports(system, weather_year=2012)

    assert "Missing required file paths for exports plugin" in caplog.text
    assert system.has_time_series(west_demand)


def test_exports_skip_regions_without_annual_data(tmp_path: Path, caplog) -> None:
    system, west_demand, east_demand = _build_system()
    inputs = _write_inputs(tmp_path)
    inputs["canada_exports_fpath"] = _write_csv(
        tmp_path / "can_exports_west_only.csv",
        {"r": ["west"], "2040": [2000.0]},
    )

    _run_exports(system, weather_year=2012, solve_year=2040, **inputs)

    assert system.has_time_series(west_demand)
    assert system.has_time_series(east_demand)
    assert system.get_time_series(east_demand, name="max_active_power").data.tolist() == pytest.approx(
        [100.0, 110.0, 120.0, 130.0]
    )


def test_exports_skip_when_weather_year_is_missing(caplog) -> None:
    system, _, _ = _build_system()

    _run_exports(system, weather_year=None)

    assert "Weather year not specified" in caplog.text


def test_exports_modifier_is_registered() -> None:
    from r2x_reeds.plugins import system_modifiers

    assert system_modifiers["add-exports"] is add_exports
