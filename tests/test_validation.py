"""Tests for input validation."""


def test_invalid_solve_year_raises_error(reeds_run_path):
    """Test that an invalid solve year raises a ValueError."""
    from r2x_core import DataStore, ValidationError
    from r2x_reeds import ReEDSConfig, ReEDSParser

    config = ReEDSConfig(
        solve_year=[2050],
        weather_year=[2012],
        scenario="test",
        case_name="test",
    )

    data_store = DataStore.from_plugin_config(config, path=reeds_run_path)
    parser = ReEDSParser(config, data_store=data_store)

    result = parser.validate_inputs()
    assert result.is_err()
    assert isinstance(result.error, ValidationError)
    assert "Solve year" in result.error.args[0]


def test_invalid_weather_year_raises_error(reeds_run_path):
    """Test that an invalid weather year raises a ValueError."""
    from r2x_core import DataStore, ValidationError
    from r2x_reeds import ReEDSConfig, ReEDSParser

    config = ReEDSConfig(
        solve_year=[2032],
        weather_year=[2050],
        scenario="test",
        case_name="test",
    )

    data_store = DataStore.from_plugin_config(config, path=reeds_run_path)
    parser = ReEDSParser(config, data_store=data_store)
    result = parser.validate_inputs()
    assert result.is_err()
    assert isinstance(result.error, ValidationError)
    assert "Weather year" in result.error.args[0]


def test_valid_years_pass_validation(reeds_run_path):
    """Test that valid years pass validation without errors."""
    from r2x_core import DataStore
    from r2x_reeds import ReEDSConfig, ReEDSParser

    config = ReEDSConfig(
        solve_year=[2032],
        weather_year=[2012],
        scenario="test",
        case_name="test",
    )

    data_store = DataStore.from_plugin_config(config, path=reeds_run_path)
    parser = ReEDSParser(config, data_store=data_store, name="test_valid_years")

    result = parser.validate_inputs()
    assert result
