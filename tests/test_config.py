"""Tests for ReEDS configuration."""

import pytest

from r2x_reeds import ReEDSConfig

pytestmark = [pytest.mark.unit]


def test_reeds_config_creation_single_year():
    """Test creating a ReEDS config with single year parameters."""
    config = ReEDSConfig(
        solve_year=2030,
        weather_year=2012,
    )
    assert config.solve_year == 2030
    assert config.weather_year == 2012


def test_reeds_config_creation_multiple_years():
    """Test creating a ReEDS config with multiple years."""
    config = ReEDSConfig(
        solve_year=[2030, 2040, 2050],
        weather_year=[2007, 2012],
    )
    assert config.solve_year == [2030, 2040, 2050]
    assert config.weather_year == [2007, 2012]


def test_reeds_config_case_name():
    """Test case name field."""
    config = ReEDSConfig(
        solve_year=2030,
        weather_year=2012,
        case_name="HighRenewable",
    )
    assert config.case_name == "HighRenewable"


def test_reeds_config_default_scenario():
    """Test default scenario."""
    config = ReEDSConfig(
        solve_year=2030,
        weather_year=2012,
    )
    assert config.scenario == "base"


def test_reeds_config_defaults_to_non_degraded_capacity():
    """The parser retains cap_ivrt behavior unless explicitly configured otherwise."""
    config = ReEDSConfig(
        solve_year=2030,
        weather_year=2012,
    )
    assert config.use_degraded_capacity is False


def test_reeds_config_can_use_degraded_capacity():
    """The parser can opt into degradation-adjusted generator capacity."""
    config = ReEDSConfig(
        solve_year=2030,
        weather_year=2012,
        use_degraded_capacity=True,
    )
    assert config.use_degraded_capacity is True


def test_reeds_config_generator_capacity_threshold_defaults_to_zero():
    config = ReEDSConfig(solve_year=2030, weather_year=2012)
    assert config.drop_gen_capacity_threshold == 0.0


def test_reeds_config_accepts_generator_capacity_threshold():
    config = ReEDSConfig(
        solve_year=2030,
        weather_year=2012,
        drop_gen_capacity_threshold=5.0,
    )
    assert config.drop_gen_capacity_threshold == 5.0


def test_reeds_config_rejects_negative_generator_capacity_threshold():
    with pytest.raises(ValueError):
        ReEDSConfig(
            solve_year=2030,
            weather_year=2012,
            drop_gen_capacity_threshold=-1.0,
        )


def test_reeds_config_scenario_field():
    """Test scenario field."""
    config = ReEDSConfig(
        solve_year=2030,
        weather_year=2012,
        scenario="high_renewable",
    )
    assert config.scenario == "high_renewable"


def test_reeds_config_primary_solve_year():
    """Test primary_solve_year property returns first year."""
    config = ReEDSConfig(
        solve_year=[2030, 2040, 2050],
        weather_year=2012,
    )
    assert config.primary_solve_year == 2030


def test_reeds_config_primary_weather_year():
    """Test primary_weather_year property returns first year."""
    config = ReEDSConfig(
        solve_year=2030,
        weather_year=[2007, 2012],
    )
    assert config.primary_weather_year == 2007


def test_reeds_config_default_case_name():
    """Test default case name."""
    config = ReEDSConfig(
        solve_year=2030,
        weather_year=2012,
    )
    assert config.case_name is None


def test_reeds_config_load_defaults_classmethod(reeds_config):
    """Test loading defaults using classmethod."""
    defaults = reeds_config.load_config()
    assert isinstance(defaults, dict)
    assert len(defaults) == 5, "Missing some of the asset keys."
