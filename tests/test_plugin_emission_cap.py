import polars as pl
import pytest
from infrasys import System

from r2x_core.store import DataStore
from r2x_reeds.config import ReEDSConfig
from r2x_reeds.models.components import ReEDSEmission, ReEDSGenerator, ReEDSRegion
from r2x_reeds.models.enums import EmissionType
from r2x_reeds.parser import ReEDSParser
from r2x_reeds.plugins.emission_cap import add_precombustion, update_system


@pytest.fixture
def simple_region():
    """Create a simple ReEDS region."""
    return ReEDSRegion(
        name="p10",
        max_active_power=1000.0,
    )


@pytest.fixture
def simple_config():
    """Create a simple ReEDS config."""
    return ReEDSConfig(
        name="TestEmissionCap",
        weather_year=2012,
        solve_year=2035,
    )


@pytest.fixture
def mock_data_store():
    """Create a mock data store."""
    return DataStore()


@pytest.fixture
def system_with_emissions(simple_region):
    """Create a system with generators that have emissions."""
    system = System()
    system.add_component(simple_region)

    # Add a thermal generator
    thermal_gen = ReEDSGenerator(
        name="biopower_init-2_p10",
        region=simple_region,
        technology="biopower",
        capacity=100.0,
        category="thermal",
        heat_rate=10.5,
        forced_outage_rate=0.08,
        planned_outage_rate=0.15,
        fuel_type="biomass",
        fuel_price=3.0,
        vom_cost=2.5,
        vintage="init-2",
    )
    system.add_component(thermal_gen)

    # Add CO2 emission
    co2_emission = ReEDSEmission(
        emission_type=EmissionType.CO2,
        rate=0.5,  # kg/MWh
    )
    system.add_supplemental_attribute(thermal_gen, co2_emission)

    # Add SO2 emission
    so2_emission = ReEDSEmission(
        emission_type=EmissionType.SO2,
        rate=0.000642,  # kg/MWh
    )
    system.add_supplemental_attribute(thermal_gen, so2_emission)

    return system


@pytest.fixture
def mock_parser_with_data(simple_config, mock_data_store):
    """Create a mock parser with required data."""
    parser = ReEDSParser(config=simple_config, data_store=mock_data_store)

    switches_data = pl.DataFrame([
        {"switch": "gsw_precombustion", "value": "false"},
        {"switch": "gsw_annualcapco2", "value": "false"},
    ])
    emission_rates_data = pl.DataFrame([
        {
            "emission_type": "co2",
            "emission_source": "combustion",
            "tech": "biopower",
            "region": "p10",
            "year": 2035,
            "tech_vintage": "init-2",
            "rate": 0.5,
        }
    ])

    co2_cap_data = pl.DataFrame([
        {"value": 1.14e9}  # tonnes
    ])

    parser.data = {
        "switches": switches_data,
        "emission_rates": emission_rates_data,
        "co2_cap": co2_cap_data,
    }

    return parser


def test_update_system_with_cap(simple_config, system_with_emissions, mock_parser_with_data):
    """Test basic emission cap functionality."""
    system = system_with_emissions
    parser = mock_parser_with_data

    new_system = update_system(
        config=simple_config,
        parser=parser,
        system=system
    )

    assert isinstance(new_system, System)
    assert new_system is not None


def test_update_system_with_custom_cap(simple_config, system_with_emissions):
    """Test emission cap with custom value."""
    system = system_with_emissions

    new_system = update_system(
        config=simple_config,
        parser=None,
        system=system,
        emission_cap=500000.0  # Custom cap
    )

    assert isinstance(new_system, System)
    assert new_system is not None


def test_no_emission_types(simple_config):
    """Test behavior when no emission types are found."""
    system = System()
    region = ReEDSRegion(name="test_region")
    system.add_component(region)

    gen = ReEDSGenerator(
        name="test_gen",
        region=region,
        technology="solar",
        capacity=100.0,
        category="renewable",
        vintage="solar1",
    )
    system.add_component(gen)

    new_system = update_system(
        config=simple_config,
        parser=None,
        system=system,
        emission_cap=1000.0
    )

    # Since there are no CO2 emissions in the system, it should return unchanged
    assert new_system == system


def test_no_emission_cap_provided(simple_config, system_with_emissions):
    """Test behavior when no emission cap is provided."""
    system = system_with_emissions

    new_system = update_system(
        config=simple_config,
        parser=None,
        system=system,
        emission_cap=None
    )

    # Since no emission cap is provided, it should return unchanged
    assert new_system == system


def test_add_precombustion_success(system_with_emissions):
    """Test successful addition of precombustion emissions."""
    system = system_with_emissions

    emission_rates = pl.DataFrame([
        {"generator_name": "biopower_init-2_p10", "emission_type": "SO2", "rate": 10.0}
    ])

    result = add_precombustion(system, emission_rates)
    assert result is True

    # Check that emission rate was updated
    generator = system.get_component(ReEDSGenerator, "biopower_init-2_p10")
    so2_emissions = system.get_supplemental_attributes_with_component(
        generator, ReEDSEmission, filter_func=lambda attr: attr.emission_type == EmissionType.SO2
    )

    assert len(so2_emissions) == 1
    # Original rate (0.000642) + precombustion rate (10.0) = 10.000642
    assert abs(so2_emissions[0].rate - 10.000642) < 1e-6


def test_add_precombustion_generator_not_found():
    """Test precombustion addition when generator is not found."""
    system = System()

    emission_rates = pl.DataFrame([
        {"generator_name": "nonexistent_gen", "emission_type": "CO2", "rate": 10.0}
    ])

    result = add_precombustion(system, emission_rates)
    # Should return False when no generators are processed
    assert result is False


def test_add_precombustion_no_emission_attribute(simple_region):
    """Test precombustion addition when generator has no emission attributes."""
    system = System()
    system.add_component(simple_region)

    # Add generator without emission attributes
    gen = ReEDSGenerator(
        name="test_gen",
        region=simple_region,
        technology="solar",
        capacity=100.0,
        category="renewable",
        vintage="solar1",
    )
    system.add_component(gen)

    emission_rates = pl.DataFrame([
        {"generator_name": "test_gen", "emission_type": "CO2", "rate": 10.0}
    ])

    result = add_precombustion(system, emission_rates)
    # Should return False when no emission attributes are found
    assert result is False


def test_add_precombustion_multiple_emissions_error(simple_region):
    """Test error when multiple emissions of same type exist."""
    system = System()
    system.add_component(simple_region)

    gen = ReEDSGenerator(
        name="test_gen",
        region=simple_region,
        technology="gas_cc",
        capacity=100.0,
        category="thermal",
        vintage="thermal1",
    )
    system.add_component(gen)

    # Add two CO2 emissions (this should not happen in practice)
    co2_emission1 = ReEDSEmission(emission_type=EmissionType.CO2, rate=0.5)
    co2_emission2 = ReEDSEmission(emission_type=EmissionType.CO2, rate=0.6)
    system.add_supplemental_attribute(gen, co2_emission1)
    system.add_supplemental_attribute(gen, co2_emission2)

    emission_rates = pl.DataFrame([
        {"generator_name": "test_gen", "emission_type": "CO2", "rate": 10.0}
    ])

    with pytest.raises(ValueError, match="Multiple emission of the same type"):
        add_precombustion(system, emission_rates)


def test_update_system_with_precombustion(simple_config, system_with_emissions, mock_data_store):
    """Test system update with precombustion emissions enabled."""
    system = system_with_emissions

    # Create parser with precombustion enabled
    parser = ReEDSParser(config=simple_config, data_store=mock_data_store)
    switches_data = pl.DataFrame([
        {"switch": "gsw_precombustion", "value": "true"},
    ])

    emission_rates_data = pl.DataFrame([
        {
            "emission_type": "so2",
            "emission_source": "precombustion",
            "tech": "biopower",
            "region": "p10",
            "year": 2035,
            "tech_vintage": "init-2",
            "rate": -0.000642,  # Negative to cancel out existing emission
        }
    ])

    co2_cap_data = pl.DataFrame([{"value": 1000000.0}])

    parser.data = {
        "switches": switches_data,
        "emission_rates": emission_rates_data,
        "co2_cap": co2_cap_data,
    }

    new_system = update_system(
        config=simple_config,
        parser=parser,
        system=system
    )

    # Check that SO2 emissions were updated
    generator = new_system.get_component(ReEDSGenerator, "biopower_init-2_p10")
    so2_emissions = new_system.get_supplemental_attributes_with_component(
        generator, ReEDSEmission, filter_func=lambda attr: attr.emission_type == EmissionType.SO2
    )

    assert len(so2_emissions) == 1
    # Original rate (0.000642) + precombustion rate (-0.000642) = 0
    assert abs(so2_emissions[0].rate) < 1e-6


def test_unknown_emission_type():
    """Test handling of unknown emission types."""
    system = System()

    emission_rates = pl.DataFrame([
        {"generator_name": "test_gen", "emission_type": "UNKNOWN", "rate": 10.0}
    ])

    result = add_precombustion(system, emission_rates)
    # Should return False when unknown emission types are encountered
    assert result is False


def test_emission_constraint_storage_with_ext(simple_config, system_with_emissions):
    """Test that emission constraints are stored correctly when system has ext."""
    system = system_with_emissions

    # Mock system.ext if it exists
    if not hasattr(system, 'ext'):
        system.ext = {}

    new_system = update_system(
        config=simple_config,
        parser=None,
        system=system,
        emission_cap=1000000.0
    )

    # Check constraint storage
    if hasattr(new_system, 'ext') and "emission_constraints" in new_system.ext:
        constraints = new_system.ext["emission_constraints"]
        assert len(constraints) > 0
        constraint_name = next(iter(constraints.keys()))
        assert constraints[constraint_name]["rhs_value"] == 1000000.0
    elif hasattr(new_system, '_emission_constraints'):
        constraints = new_system._emission_constraints
        assert len(constraints) > 0
        constraint_name = next(iter(constraints.keys()))
        assert constraints[constraint_name]["rhs_value"] == 1000000.0


def test_emission_constraint_storage_without_ext(simple_config, system_with_emissions):
    """Test that emission constraints are stored correctly when system doesn't have ext."""
    system = system_with_emissions

    # Ensure system doesn't have ext
    if hasattr(system, 'ext'):
        delattr(system, 'ext')

    new_system = update_system(
        config=simple_config,
        parser=None,
        system=system,
        emission_cap=500000.0
    )

    # Check that constraint was stored in _emission_constraints
    assert hasattr(new_system, '_emission_constraints')
    constraints = new_system._emission_constraints
    assert len(constraints) > 0
    constraint_name = next(iter(constraints.keys()))
    assert constraints[constraint_name]["rhs_value"] == 500000.0
    assert constraints[constraint_name]["emission_type"] == EmissionType.CO2


def test_precombustion_switches_conversion(simple_config, system_with_emissions, mock_data_store):
    """Test switches conversion from DataFrame to dictionary."""
    system = system_with_emissions

    parser = ReEDSParser(config=simple_config, data_store=mock_data_store)

    # Test with DataFrame format
    switches_data = pl.DataFrame([
        {"switch": "gsw_precombustion", "value": "true"},
        {"switch": "other_switch", "value": "false"},
    ])

    emission_rates_data = pl.DataFrame([
        {
            "emission_type": "so2",
            "emission_source": "precombustion",
            "tech": "biopower",
            "region": "p10",
            "year": 2035,
            "tech_vintage": "init-2",
            "rate": 5.0,
        }
    ])

    co2_cap_data = pl.DataFrame([{"value": 100000.0}])

    parser.data = {
        "switches": switches_data,
        "emission_rates": emission_rates_data,
        "co2_cap": co2_cap_data,
    }

    new_system = update_system(
        config=simple_config,
        parser=parser,
        system=system
    )

    # Verify the system was updated (precombustion was applied)
    generator = new_system.get_component(ReEDSGenerator, "biopower_init-2_p10")
    so2_emissions = new_system.get_supplemental_attributes_with_component(
        generator, ReEDSEmission, filter_func=lambda attr: attr.emission_type == EmissionType.SO2
    )

    assert len(so2_emissions) == 1
    # Original rate (0.000642) + precombustion rate (5.0) = 5.000642
    assert abs(so2_emissions[0].rate - 5.000642) < 1e-6
