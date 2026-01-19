from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest
from infrasys import System

from r2x_reeds.models.components import ReEDSGenerator, ReEDSRegion
from r2x_reeds.sysmod import imports

pytestmark = [pytest.mark.integration]


def _build_generator() -> tuple[System, ReEDSGenerator]:
    system = System(name="test_imports")
    region = ReEDSRegion(name="west")
    system.add_component(region)
    generator = ReEDSGenerator(
        name="can-imports_west",
        region=region,
        capacity=50.0,
        technology="canada_import",
        category="imports",
    )
    system.add_component(generator)
    return system, generator


def _write_csv(path: Path, data: dict[str, list]) -> str:
    pl.DataFrame(data).write_csv(path)
    return str(path)


def _run_imports(system: System, **kwargs) -> System:
    result = imports.add_imports(system, imports.ImportsConfig(**kwargs))
    assert result.is_ok()
    return result.unwrap()


def test_imports_scope_full_flow(tmp_path: Path) -> None:
    """Canadian imports plugin attaches hydro budget time series."""
    system, generator = _build_generator()

    hour_map_path = _write_csv(
        tmp_path / "hour_map.csv",
        {
            "hour": [1, 2, 3],
            "time_index": ["2024-01-01T00:00:00", "2024-01-02T00:00:00", "2024-01-03T00:00:00"],
            "season": ["winter", "winter", "spring"],
        },
    )
    szn_frac_path = _write_csv(
        tmp_path / "szn_frac.csv",
        {
            "season": ["winter", "spring"],
            "value": [0.6, 0.4],
        },
    )
    imports_path = _write_csv(
        tmp_path / "imports.csv",
        {"r": ["west"], "value": [2000.0]},
    )

    _run_imports(
        system,
        weather_year=2024,
        canada_imports_fpath=imports_path,
        canada_szn_frac_fpath=szn_frac_path,
        hour_map_fpath=hour_map_path,
    )

    assert system.has_time_series(generator)
    ts_values = system.get_time_series(generator).data.tolist()
    assert len(ts_values) == 2
    assert all(val > 0 for val in ts_values)


def test_imports_scope_missing_weather_year(caplog) -> None:
    """Weather year is required to build imports time series."""
    system, _ = _build_generator()

    _run_imports(system, weather_year=None)

    assert "Weather year not specified" in caplog.text


def test_imports_scope_missing_files(caplog) -> None:
    """All file paths must be provided."""
    system, _ = _build_generator()

    _run_imports(system, weather_year=2024, canada_imports_fpath=None)

    assert "Missing required file paths for imports plugin" in caplog.text


def test_imports_scope_missing_region(tmp_path: Path, caplog) -> None:
    """Regions without import data emit a warning and skip time series."""
    system, generator = _build_generator()

    hour_map_path = _write_csv(
        tmp_path / "hour_map.csv",
        {"hour": [1], "time_index": ["2024-01-01T00:00:00"], "season": ["winter"]},
    )
    szn_frac_path = _write_csv(tmp_path / "szn_frac.csv", {"season": ["winter"], "value": [1.0]})
    imports_path = _write_csv(tmp_path / "imports.csv", {"r": ["other"], "value": [1000.0]})

    _run_imports(
        system,
        weather_year=2024,
        canada_imports_fpath=imports_path,
        canada_szn_frac_fpath=szn_frac_path,
        hour_map_fpath=hour_map_path,
    )

    assert "No import data found for region" in caplog.text
    assert system.has_time_series(generator) is False


def test_imports_scope_empty_join(tmp_path: Path, caplog) -> None:
    """Empty hourly join logs a warning and skips adding time series."""
    system, generator = _build_generator()

    hour_map_path = _write_csv(tmp_path / "hour_map_empty.csv", {"hour": [], "time_index": [], "season": []})
    szn_frac_path = _write_csv(
        tmp_path / "szn_frac.csv",
        {"season": ["winter"], "value": [1.0]},
    )
    imports_path = _write_csv(tmp_path / "imports.csv", {"r": ["west"], "value": [1000.0]})

    caplog.set_level("WARNING", logger="r2x_reeds.sysmod.imports")
    _run_imports(
        system,
        weather_year=2024,
        canada_imports_fpath=imports_path,
        canada_szn_frac_fpath=szn_frac_path,
        hour_map_fpath=hour_map_path,
    )

    assert "empty time series" in caplog.text.lower()
    assert system.has_time_series(generator) is False


def test_imports_scope_exception_logs(tmp_path: Path, caplog) -> None:
    """Missing fraction values cause errors that are logged."""
    system, _ = _build_generator()

    hour_map_path = _write_csv(
        tmp_path / "hour_map.csv",
        {
            "hour": [1, 2],
            "time_index": ["2024-01-01T00:00:00", "2024-01-02T00:00:00"],
            "season": ["winter", "winter"],
        },
    )
    szn_frac_path = _write_csv(tmp_path / "szn_frac.csv", {"season": ["winter"]})
    imports_path = _write_csv(tmp_path / "imports.csv", {"r": ["west"], "value": [1000.0]})

    caplog.set_level("ERROR", logger="r2x_reeds.sysmod.imports")
    result = imports.add_imports(
        system,
        imports.ImportsConfig(
            weather_year=2024,
            canada_imports_fpath=imports_path,
            canada_szn_frac_fpath=szn_frac_path,
            hour_map_fpath=hour_map_path,
        ),
    )

    assert result.is_err()
    assert "error in imports plugin" in caplog.text.lower()
