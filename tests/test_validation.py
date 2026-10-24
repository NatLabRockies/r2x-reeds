"""Tests for input validation."""

import shutil
from pathlib import Path

import pytest

from tests.fixtures.data_fixtures import current_data_store

pytestmark = [pytest.mark.integration]


def test_invalid_solve_year_raises_error(reeds_run_path):
    """The public parser rejects a requested solve/weather pair with no load rows."""
    from r2x_core import PluginContext, PluginError
    from r2x_core.exceptions import ReaderError
    from r2x_reeds import ReEDSConfig, ReEDSParser

    config = ReEDSConfig(
        solve_year=[2050],
        weather_year=[2012],
        scenario="test",
        case_name="test",
    )
    parser = ReEDSParser.from_context(PluginContext(config=config, store=current_data_store(reeds_run_path)))

    with pytest.raises(PluginError, match="Every requested solve-year/weather-year pair") as captured:
        parser.run()

    assert isinstance(captured.value.__cause__, ReaderError)
    assert isinstance(captured.value.__cause__.__cause__, ValueError)


def test_invalid_weather_year_raises_error(reeds_run_path):
    """The public parser rejects a requested solve/weather pair with no load rows."""
    from r2x_core import PluginContext, PluginError
    from r2x_core.exceptions import ReaderError
    from r2x_reeds import ReEDSConfig, ReEDSParser

    config = ReEDSConfig(
        solve_year=[2032],
        weather_year=[2050],
        scenario="test",
        case_name="test",
    )
    parser = ReEDSParser.from_context(PluginContext(config=config, store=current_data_store(reeds_run_path)))

    with pytest.raises(PluginError, match="Every requested solve-year/weather-year pair") as captured:
        parser.run()

    assert isinstance(captured.value.__cause__, ReaderError)
    assert isinstance(captured.value.__cause__.__cause__, ValueError)


def test_valid_years_build_a_system(reeds_run_path):
    """Valid configured years build through the public parser lifecycle."""
    from r2x_core import PluginContext
    from r2x_reeds import ReEDSConfig, ReEDSParser

    config = ReEDSConfig(
        solve_year=[2032],
        weather_year=[2012],
        scenario="test",
        case_name="test",
    )
    parser = ReEDSParser.from_context(PluginContext(config=config, store=current_data_store(reeds_run_path)))

    assert parser.run().system is not None


def test_missing_deprecated_agglevels_file_still_builds(tmp_path: Path, reeds_run_path: Path) -> None:
    """The public parser accepts an absent optional agglevels.csv."""
    from r2x_core import PluginContext
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

    parser = ReEDSParser.from_context(PluginContext(config=config, store=current_data_store(run_path)))

    assert parser.run().system is not None
