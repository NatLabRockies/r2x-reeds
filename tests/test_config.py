"""Tests for ReEDS configuration."""

import json

import pytest

from r2x_reeds.config import ReEDSConfig


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


def test_reeds_config_load_defaults_classmethod():
    """Test loading defaults using classmethod."""
    defaults = ReEDSConfig.load_defaults()
    assert isinstance(defaults, dict)
    # Should load from the actual defaults.json file
    assert len(defaults) > 0


def test_reeds_config_load_defaults_with_overrides(tmp_path):
    """Test loading defaults with overrides."""
    # Create a test defaults file
    test_file = tmp_path / "defaults.json"
    test_data = {"excluded_techs": ["coal", "oil"], "include_solar": True}
    test_file.write_text(json.dumps(test_data))

    # Load defaults with overrides
    defaults = ReEDSConfig.load_defaults(
        config_path=tmp_path, overrides={"include_solar": False, "new_field": "new_value"}
    )

    assert defaults["excluded_techs"] == ["coal", "oil"]
    assert defaults["include_solar"] is False  # Override takes precedence
    assert defaults["new_field"] == "new_value"  # New field added


def test_reeds_config_load_defaults_list_merge(tmp_path):
    """Test that list values are merged and deduplicated."""
    # Create a test defaults file with a list
    test_file = tmp_path / "defaults.json"
    test_data = {"excluded_techs": ["coal", "oil"], "other": "value"}
    test_file.write_text(json.dumps(test_data))

    # Load with list override
    defaults = ReEDSConfig.load_defaults(
        config_path=tmp_path,
        overrides={"excluded_techs": ["oil", "nuclear"]},  # oil is duplicate
    )

    assert "coal" in defaults["excluded_techs"]
    assert "oil" in defaults["excluded_techs"]
    assert "nuclear" in defaults["excluded_techs"]
    # Check order is preserved and no duplicates
    assert defaults["excluded_techs"].count("oil") == 1


def test_reeds_config_load_defaults_nonexistent_file(tmp_path):
    """Test loading defaults when file doesn't exist returns empty dict or overrides."""
    defaults = ReEDSConfig.load_defaults(config_path=tmp_path)
    assert defaults == {}

    defaults_with_overrides = ReEDSConfig.load_defaults(config_path=tmp_path, overrides={"key": "value"})
    assert defaults_with_overrides == {"key": "value"}


def test_reeds_config_load_file_mapping_classmethod():
    """Test loading file mapping using classmethod."""
    mappings = ReEDSConfig.load_file_mapping()
    assert isinstance(mappings, list)
    # May be empty or have items depending on actual file_mapping.json


def test_reeds_config_load_file_mapping_with_overrides(tmp_path):
    """Test loading file mapping with path overrides."""
    # Create a test file mapping
    mapping_file = tmp_path / "file_mapping.json"
    test_mappings = [
        {"name": "data_file", "fpath": "*.csv", "optional": False},
        {"name": "config_file", "fpath": "*.config", "optional": True},
    ]
    mapping_file.write_text(json.dumps(test_mappings))

    # Load with overrides
    mappings = ReEDSConfig.load_file_mapping(
        config_path=tmp_path, file_overrides={"data_file": "/custom/path/data.csv"}
    )

    assert len(mappings) == 2
    assert mappings[0]["name"] == "data_file"
    assert mappings[0]["fpath"] == "/custom/path/data.csv"  # Override applied
    assert mappings[1]["name"] == "config_file"
    assert mappings[1]["fpath"] == "*.config"  # Not overridden


def test_reeds_config_load_file_mapping_nonexistent_file(tmp_path):
    """Test loading file mapping when file doesn't exist returns empty list."""
    mappings = ReEDSConfig.load_file_mapping(config_path=tmp_path)
    assert mappings == []


def test_reeds_config_load_file_mapping_invalid_json(tmp_path):
    """Test error handling for invalid JSON."""
    mapping_file = tmp_path / "file_mapping.json"
    mapping_file.write_text("{ invalid json }")

    with pytest.raises(json.JSONDecodeError):
        ReEDSConfig.load_file_mapping(config_path=tmp_path)


def test_reeds_config_load_defaults_invalid_json(tmp_path):
    """Test error handling for invalid defaults JSON."""
    defaults_file = tmp_path / "defaults.json"
    defaults_file.write_text("{ invalid json }")

    with pytest.raises(json.JSONDecodeError):
        ReEDSConfig.load_defaults(config_path=tmp_path)


def test_reeds_config_load_defaults_not_dict(tmp_path):
    """Test error handling when defaults.json is not a dict."""
    defaults_file = tmp_path / "defaults.json"
    defaults_file.write_text(json.dumps(["not", "a", "dict"]))

    with pytest.raises(TypeError, match="must contain a dict"):
        ReEDSConfig.load_defaults(config_path=tmp_path)


def test_reeds_config_load_file_mapping_not_list(tmp_path):
    """Test error handling when file_mapping.json is not a list."""
    mapping_file = tmp_path / "file_mapping.json"
    mapping_file.write_text(json.dumps({"not": "a list"}))

    with pytest.raises(ValueError, match="File mapping file must contain a list"):
        ReEDSConfig.load_file_mapping(config_path=tmp_path)
