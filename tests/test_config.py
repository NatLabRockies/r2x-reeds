"""Tests for ReEDS configuration."""

import pytest
from pydantic import TypeAdapter, ValidationError

from r2x_core import DataFile
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


def test_reeds_config_rejects_removed_or_unknown_settings() -> None:
    with pytest.raises(ValidationError, match="use_degraded_capacity"):
        ReEDSConfig(solve_year=2030, weather_year=2012, use_degraded_capacity=True)

    with pytest.raises(ValidationError, match="asset_overrides"):
        ReEDSConfig(solve_year=2030, weather_year=2012, asset_overrides={})


def test_reeds_config_selects_generator_capacity_source() -> None:
    config = ReEDSConfig(solve_year=2030, weather_year=2012, generator_capacity_source="degraded")

    assert config.generator_capacity_source == "degraded"


def test_generator_classification_overrides_are_optional_and_typed() -> None:
    config = ReEDSConfig(
        solve_year=2030,
        weather_year=2012,
        generator_classification_overrides=[{"technology": "Gas-CC", "category": "wind"}],
    )

    assert config.generator_classification_overrides[0].technology == "Gas-CC"
    assert config.generator_classification_overrides[0].category == "wind"
    assert ReEDSConfig(solve_year=2030, weather_year=2012).generator_classification_overrides == []

    with pytest.raises(ValidationError, match="each technology once"):
        ReEDSConfig(
            solve_year=2030,
            weather_year=2012,
            generator_classification_overrides=[
                {"technology": "Gas-CC", "category": "thermal"},
                {"technology": "gas-cc", "category": "wind"},
            ],
        )


def test_packaged_file_mapping_validates_with_deferred_capacity_source() -> None:
    config = ReEDSConfig(solve_year=2030, weather_year=2012)

    data_files = TypeAdapter(list[DataFile]).validate_json(config.fmap_path.read_bytes())
    selected = next(data_file for data_file in data_files if data_file.name == "generator_capacity_selected")

    assert selected.source == "{generator_capacity_source_name}"


def test_reeds_config_scenario_field():
    """Test scenario field."""
    config = ReEDSConfig(
        solve_year=2030,
        weather_year=2012,
        scenario="high_renewable",
    )
    assert config.scenario == "high_renewable"


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
