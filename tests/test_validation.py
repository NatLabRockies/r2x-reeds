"""Tests for input validation."""

import shutil
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration]


def test_invalid_solve_year_raises_error(reeds_run_path):
    """Test that an invalid solve year returns validation error."""
    from r2x_core import DataStore, PluginContext
    from r2x_reeds import ReEDSConfig, ReEDSParser

    config = ReEDSConfig(
        solve_year=[2050],
        weather_year=[2012],
        scenario="test",
        case_name="test",
    )

    data_store = DataStore.from_plugin_config(config, path=reeds_run_path)
    ctx = PluginContext(config=config, store=data_store)
    parser = ReEDSParser.from_context(ctx)

    result = parser.on_validate()
    assert result.is_err()
    assert "Solve year" in str(result.err())


def test_invalid_weather_year_raises_error(reeds_run_path):
    """Test that an invalid weather year returns validation error."""
    from r2x_core import DataStore, PluginContext
    from r2x_reeds import ReEDSConfig, ReEDSParser

    config = ReEDSConfig(
        solve_year=[2032],
        weather_year=[2050],
        scenario="test",
        case_name="test",
    )

    data_store = DataStore.from_plugin_config(config, path=reeds_run_path)
    ctx = PluginContext(config=config, store=data_store)
    parser = ReEDSParser.from_context(ctx)

    result = parser.on_validate()
    assert result.is_err()
    assert "Weather year" in str(result.err())


def test_valid_years_pass_validation(reeds_run_path):
    """Test that valid years pass validation without errors."""
    from r2x_core import DataStore, PluginContext
    from r2x_reeds import ReEDSConfig, ReEDSParser

    config = ReEDSConfig(
        solve_year=[2032],
        weather_year=[2012],
        scenario="test",
        case_name="test",
    )

    data_store = DataStore.from_plugin_config(config, path=reeds_run_path)
    ctx = PluginContext(config=config, store=data_store)
    parser = ReEDSParser.from_context(ctx)

    result = parser.on_validate()
    assert result.is_ok()


def test_missing_deprecated_agglevels_file_still_validates(tmp_path: Path, reeds_run_path: Path) -> None:
    """Parser validation should allow runs without deprecated agglevels.csv."""

    from r2x_core import DataStore, PluginContext
    from r2x_reeds import ReEDSConfig, ReEDSParser

    run_path = tmp_path / "test_Pacific"
    shutil.copytree(reeds_run_path, run_path)
    agglevels_path = run_path / "inputs_case" / "agglevels.csv"
    if agglevels_path.exists():
        agglevels_path.unlink()

    config = ReEDSConfig(
        solve_year=[2032],
        weather_year=[2012],
        scenario="test",
        case_name="test",
    )

    data_store = DataStore.from_plugin_config(config, path=run_path)
    ctx = PluginContext(config=config, store=data_store)
    parser = ReEDSParser.from_context(ctx)

    result = parser.on_validate()
    assert result.is_ok()
