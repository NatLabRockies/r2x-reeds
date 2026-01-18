"""Tests for input validation."""

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

    from typing import cast

    data_store = DataStore.from_plugin_config(config, path=reeds_run_path)
    ctx = PluginContext(config=config, store=data_store)
    parser = cast(ReEDSParser, ReEDSParser.from_context(ctx))

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

    from typing import cast

    data_store = DataStore.from_plugin_config(config, path=reeds_run_path)
    ctx = PluginContext(config=config, store=data_store)
    parser = cast(ReEDSParser, ReEDSParser.from_context(ctx))

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

    from typing import cast

    data_store = DataStore.from_plugin_config(config, path=reeds_run_path)
    ctx = PluginContext(config=config, store=data_store)
    parser = cast(ReEDSParser, ReEDSParser.from_context(ctx))

    result = parser.on_validate()
    assert result.is_ok()
