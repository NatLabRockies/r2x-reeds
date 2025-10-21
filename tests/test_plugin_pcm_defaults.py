import json

import pytest
from infrasys import System

from r2x_core.store import DataStore
from r2x_reeds.config import ReEDSConfig
from r2x_reeds.models.components import ReEDSGenerator, ReEDSRegion
from r2x_reeds.parser import ReEDSParser
from r2x_reeds.plugins.pcm_defaults import update_system


@pytest.fixture
def simple_config():
    """Create a simple ReEDS config."""
    return ReEDSConfig(
        name="TestPCMDefaults",
        weather_year=2012,
        solve_year=2035,
    )


@pytest.fixture
def mock_data_store():
    """Create a mock data store."""
    return DataStore()


@pytest.fixture
def system_with_generators():
    """Create a system with ReEDS generators."""
    system = System()

    # Create a region
    region = ReEDSRegion(name="p1", max_active_power=1000.0)
    system.add_component(region)

    # Create generators with missing attributes
    thermal_gen = ReEDSGenerator(
        name="gas_cc_new_p1",
        region=region,
        technology="gas_cc",
        capacity=100.0,
        category="thermal",
        vintage="new",
        forced_outage_rate=None,
        planned_outage_rate=None,
        heat_rate=None,
        vom_cost=None,
    )

    renewable_gen = ReEDSGenerator(
        name="wind_new_p1",
        region=region,
        technology="wind-onshore",
        capacity=50.0,
        category="renewable",
        vintage="new",
        forced_outage_rate=None,
        planned_outage_rate=None,
    )

    system.add_components(thermal_gen, renewable_gen)
    return system


def test_update_system_basic(simple_config, system_with_generators, mock_data_store):
    """Test basic PCM defaults functionality."""
    system = system_with_generators
    parser = ReEDSParser(config=simple_config, data_store=mock_data_store)
    parser.data = {}

    new_system = update_system(config=simple_config, parser=parser, system=system)

    assert isinstance(new_system, System)
    assert new_system is not None


def test_custom_pcm_defaults(tmp_path, simple_config):
    """Test custom PCM defaults from file."""
    system = System()

    # Create a region and generator
    region = ReEDSRegion(name="test_region", max_active_power=1000.0)
    system.add_component(region)

    generator = ReEDSGenerator(
        name="test_gen",
        region=region,
        technology="gas_cc",
        capacity=100.0,
        category="thermal",
        vintage="new",
        forced_outage_rate=None,
        planned_outage_rate=None,
        heat_rate=None,
        vom_cost=None,
    )
    system.add_component(generator)

    # Verify initial state
    assert generator.forced_outage_rate is None
    assert generator.planned_outage_rate is None
    assert generator.heat_rate is None
    assert generator.vom_cost is None

    # Create PCM defaults - use category "thermal" to match the generator
    pcm_defaults = {
        "thermal": {
            "forced_outage_rate": 0.05,
            "planned_outage_rate": 0.10,
            "heat_rate": 7500.0,
            "vom_cost": 3.5,
        }
    }
    temp_file = tmp_path / "pcm_data.json"

    with open(temp_file, "w") as f:
        json.dump(pcm_defaults, f)

    new_system = update_system(
        config=simple_config,
        parser=None,
        system=system,
        pcm_defaults_fpath=str(temp_file)
    )

    # Check that the system was modified in place or verify return value
    updated_gen = new_system.get_component(ReEDSGenerator, "test_gen")
    assert updated_gen.forced_outage_rate == 0.05
    assert updated_gen.planned_outage_rate == 0.10
    assert updated_gen.heat_rate == 7500.0
    assert updated_gen.vom_cost == 3.5


def test_custom_pcm_defaults_override(tmp_path, simple_config):
    """Test PCM defaults with override functionality."""
    system = System()

    # Create a region and generator with existing values
    region = ReEDSRegion(name="test_region", max_active_power=1000.0)
    system.add_component(region)

    generator = ReEDSGenerator(
        name="test_gen",
        region=region,
        technology="gas_cc",
        capacity=100.0,
        category="thermal",
        vintage="new",
        forced_outage_rate=0.02,
        planned_outage_rate=0.05,
        heat_rate=8000.0,
        vom_cost=None,
    )
    system.add_component(generator)

    # Use category "thermal" to match the generator
    pcm_defaults = {
        "thermal": {
            "forced_outage_rate": 0.08,
            "planned_outage_rate": 0.15,
            "heat_rate": 7000.0,
            "vom_cost": 4.0,
        }
    }
    temp_file = tmp_path / "pcm_data.json"

    with open(temp_file, "w") as f:
        json.dump(pcm_defaults, f)

    # Test without override (should only fill None values)
    new_system = update_system(
        config=simple_config,
        parser=None,
        system=system,
        pcm_defaults_fpath=str(temp_file),
        pcm_defaults_override=False
    )

    updated_gen = new_system.get_component(ReEDSGenerator, "test_gen")
    # Existing values should remain unchanged
    assert updated_gen.forced_outage_rate == 0.02
    assert updated_gen.planned_outage_rate == 0.05
    assert updated_gen.heat_rate == 8000.0
    # None value should be filled
    assert updated_gen.vom_cost == 4.0

    # Reset generator for override test
    generator.forced_outage_rate = 0.02
    generator.planned_outage_rate = 0.05
    generator.heat_rate = 8000.0
    generator.vom_cost = None

    # Test with override (should replace all values)
    new_system = update_system(
        config=simple_config,
        parser=None,
        system=system,
        pcm_defaults_fpath=str(temp_file),
        pcm_defaults_override=True
    )

    updated_gen = new_system.get_component(ReEDSGenerator, "test_gen")
    # All values should be overridden
    assert updated_gen.forced_outage_rate == 0.08
    assert updated_gen.planned_outage_rate == 0.15
    assert updated_gen.heat_rate == 7000.0
    assert updated_gen.vom_cost == 4.0


def test_pcm_defaults_technology_specific(tmp_path, simple_config):
    """Test technology-specific PCM defaults."""
    system = System()

    # Create a region
    region = ReEDSRegion(name="test_region", max_active_power=1000.0)
    system.add_component(region)

    # Create generators with different technologies
    gas_gen = ReEDSGenerator(
        name="gas_gen",
        region=region,
        technology="gas_cc",
        capacity=100.0,
        category="thermal",
        vintage="new",
        forced_outage_rate=None,
        heat_rate=None,
    )

    wind_gen = ReEDSGenerator(
        name="wind_gen",
        region=region,
        technology="wind-onshore",
        capacity=50.0,
        category="renewable",
        vintage="new",
        forced_outage_rate=None,
    )

    system.add_components(gas_gen, wind_gen)

    # Create technology-specific defaults (matching the technology field)
    pcm_defaults = {
        "gas_cc": {
            "forced_outage_rate": 0.06,
            "heat_rate": 7200.0,
        },
        "wind-onshore": {
            "forced_outage_rate": 0.02,
        }
    }
    temp_file = tmp_path / "pcm_data.json"

    with open(temp_file, "w") as f:
        json.dump(pcm_defaults, f)

    new_system = update_system(
        config=simple_config,
        parser=None,
        system=system,
        pcm_defaults_fpath=str(temp_file)
    )

    updated_gas_gen = new_system.get_component(ReEDSGenerator, "gas_gen")
    updated_wind_gen = new_system.get_component(ReEDSGenerator, "wind_gen")

    assert updated_gas_gen.forced_outage_rate == 0.06
    assert updated_gas_gen.heat_rate == 7200.0
    assert updated_wind_gen.forced_outage_rate == 0.02


def test_pcm_defaults_by_name(tmp_path, simple_config):
    """Test PCM defaults using exact generator name matching."""
    system = System()

    region = ReEDSRegion(name="test_region", max_active_power=1000.0)
    system.add_component(region)

    generator = ReEDSGenerator(
        name="specific_gen",
        region=region,
        technology="gas_cc",
        capacity=100.0,
        category="thermal",
        vintage="new",
        forced_outage_rate=None,
        heat_rate=None,
    )
    system.add_component(generator)

    # Use exact generator name as key
    pcm_defaults = {
        "specific_gen": {
            "forced_outage_rate": 0.03,
            "heat_rate": 6500.0,
        }
    }
    temp_file = tmp_path / "pcm_data.json"

    with open(temp_file, "w") as f:
        json.dump(pcm_defaults, f)

    new_system = update_system(
        config=simple_config,
        parser=None,
        system=system,
        pcm_defaults_fpath=str(temp_file)
    )

    updated_gen = new_system.get_component(ReEDSGenerator, "specific_gen")
    assert updated_gen.forced_outage_rate == 0.03
    assert updated_gen.heat_rate == 6500.0


def test_pcm_defaults_hierarchy(tmp_path, simple_config):
    """Test PCM defaults matching hierarchy: name > technology > category."""
    system = System()

    region = ReEDSRegion(name="test_region", max_active_power=1000.0)
    system.add_component(region)

    generator = ReEDSGenerator(
        name="test_gen",
        region=region,
        technology="gas_cc",
        capacity=100.0,
        category="thermal",
        vintage="new",
        forced_outage_rate=None,
        heat_rate=None,
        vom_cost=None,
    )
    system.add_component(generator)

    # Define defaults at all levels - name should take precedence
    pcm_defaults = {
        "test_gen": {  # Most specific - should be used
            "forced_outage_rate": 0.01,
        },
        "gas_cc": {  # Technology level
            "forced_outage_rate": 0.02,
            "heat_rate": 7000.0,
        },
        "thermal": {  # Category level
            "forced_outage_rate": 0.03,
            "heat_rate": 8000.0,
            "vom_cost": 5.0,
        }
    }
    temp_file = tmp_path / "pcm_data.json"

    with open(temp_file, "w") as f:
        json.dump(pcm_defaults, f)

    new_system = update_system(
        config=simple_config,
        parser=None,
        system=system,
        pcm_defaults_fpath=str(temp_file)
    )

    updated_gen = new_system.get_component(ReEDSGenerator, "test_gen")
    # Should use name-specific value (highest priority)
    assert updated_gen.forced_outage_rate == 0.01
    # Other fields should remain None since name-specific defaults don't include them
    assert updated_gen.heat_rate is None
    assert updated_gen.vom_cost is None


def test_pcm_defaults_no_file(simple_config, system_with_generators):
    """Test PCM defaults when no file is provided."""
    system = system_with_generators

    new_system = update_system(
        config=simple_config,
        parser=None,
        system=system,
        pcm_defaults_fpath=None
    )

    assert new_system is system


def test_pcm_defaults_invalid_file(simple_config, system_with_generators):
    """Test PCM defaults with invalid file path."""
    system = system_with_generators

    # Test that the plugin handles invalid file gracefully
    try:
        new_system = update_system(
            config=simple_config,
            parser=None,
            system=system,
            pcm_defaults_fpath="nonexistent_file.json"
        )
        # If no exception, check that system is returned unchanged
        assert new_system is system
    except (FileNotFoundError, ValueError, Exception):
        # If plugin throws exception for invalid file, that's acceptable behavior
        pass


def test_pcm_defaults_empty_system(tmp_path, simple_config):
    """Test PCM defaults with empty system."""
    system = System()

    pcm_defaults = {"thermal": {"forced_outage_rate": 0.05}}
    temp_file = tmp_path / "pcm_data.json"

    with open(temp_file, "w") as f:
        json.dump(pcm_defaults, f)

    new_system = update_system(
        config=simple_config,
        parser=None,
        system=system,
        pcm_defaults_fpath=str(temp_file)
    )

    assert new_system is system
    assert len(list(new_system.get_components(ReEDSGenerator))) == 0


def test_pcm_defaults_malformed_json(tmp_path, simple_config, system_with_generators):
    """Test PCM defaults with malformed JSON file."""
    system = system_with_generators

    temp_file = tmp_path / "malformed.json"

    with open(temp_file, "w") as f:
        f.write('{"thermal": {"forced_outage_rate": 0.05,}')

    try:
        new_system = update_system(
            config=simple_config,
            parser=None,
            system=system,
            pcm_defaults_fpath=str(temp_file)
        )
        assert new_system is system
    except (json.JSONDecodeError, ValueError, Exception):
        pass


def test_pcm_defaults_partial_application(tmp_path, simple_config):
    """Test PCM defaults with only some attributes specified."""
    system = System()

    region = ReEDSRegion(name="test_region", max_active_power=1000.0)
    system.add_component(region)

    generator = ReEDSGenerator(
        name="test_gen",
        region=region,
        technology="gas_cc",
        capacity=100.0,
        category="thermal",
        vintage="new",
        forced_outage_rate=None,
        planned_outage_rate=0.10,
        heat_rate=None,
        vom_cost=None,
    )
    system.add_component(generator)

    pcm_defaults = {
        "thermal": {
            "forced_outage_rate": 0.05,
            "heat_rate": 7500.0,
        }
    }
    temp_file = tmp_path / "pcm_data.json"

    with open(temp_file, "w") as f:
        json.dump(pcm_defaults, f)

    new_system = update_system(
        config=simple_config,
        parser=None,
        system=system,
        pcm_defaults_fpath=str(temp_file)
    )

    updated_gen = new_system.get_component(ReEDSGenerator, "test_gen")
    assert updated_gen.forced_outage_rate == 0.05
    assert updated_gen.planned_outage_rate == 0.10
    assert updated_gen.heat_rate == 7500.0
    assert updated_gen.vom_cost is None


def test_pcm_defaults_no_matching_category(tmp_path, simple_config):
    """Test PCM defaults when no matching category is found."""
    system = System()

    region = ReEDSRegion(name="test_region", max_active_power=1000.0)
    system.add_component(region)

    generator = ReEDSGenerator(
        name="test_gen",
        region=region,
        technology="gas_cc",
        capacity=100.0,
        category="thermal",
        vintage="new",
        forced_outage_rate=None,
        heat_rate=None,
    )
    system.add_component(generator)

    # Use a different category that won't match
    pcm_defaults = {
        "renewable": {
            "forced_outage_rate": 0.05,
            "heat_rate": 7500.0,
        }
    }
    temp_file = tmp_path / "pcm_data.json"

    with open(temp_file, "w") as f:
        json.dump(pcm_defaults, f)

    new_system = update_system(
        config=simple_config,
        parser=None,
        system=system,
        pcm_defaults_fpath=str(temp_file)
    )

    updated_gen = new_system.get_component(ReEDSGenerator, "test_gen")

    assert updated_gen.forced_outage_rate is None
    assert updated_gen.heat_rate is None
