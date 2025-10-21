import pytest
from infrasys import System

from r2x_reeds.models.components import ReEDSEmission, ReEDSGenerator, ReEDSRegion
from r2x_reeds.models.enums import EmissionType
from r2x_reeds.plugins.break_gens import break_generators


@pytest.fixture
def simple_region():
    """Create a simple ReEDS region."""
    return ReEDSRegion(
        name="test_region",
        max_active_power=1000.0,
    )


@pytest.fixture
def simple_system_base(simple_region):
    """Create a basic system with a region."""
    system = System()
    system.add_component(simple_region)
    return system


@pytest.fixture
def system_with_storage_generators(simple_system_base, simple_region):
    """Create a system with storage generators for testing."""
    system = simple_system_base

    large_storage = ReEDSGenerator(
        name="large_storage_01",
        region=simple_region,
        technology="battery",
        capacity=200.0,
        category="storage",
        heat_rate=None,
        forced_outage_rate=0.05,
        planned_outage_rate=0.10,
        fuel_type=None,
        fuel_price=None,
        vom_cost=5.0,
        vintage="gen1",
    )
    system.add_component(large_storage)

    storage_emission = ReEDSEmission(
        emission_type=EmissionType.CO2,
        rate=0.0,
    )
    system.add_supplemental_attribute(large_storage, storage_emission)

    return system


@pytest.fixture
def system_with_mixed_generators(simple_system_base, simple_region):
    """Create a system with mixed generator types for testing."""
    system = simple_system_base

    generators = [
        # Storage generators
        ReEDSGenerator(
            name="storage_01",
            region=simple_region,
            technology="battery",
            capacity=200.0,
            category="storage",
            heat_rate=None,
            forced_outage_rate=0.05,
            planned_outage_rate=0.10,
            fuel_type=None,
            fuel_price=None,
            vom_cost=5.0,
            vintage="storage1",
        ),
        ReEDSGenerator(
            name="storage_02",
            region=simple_region,
            technology="battery",
            capacity=150.0,
            category="storage",
            heat_rate=None,
            forced_outage_rate=0.05,
            planned_outage_rate=0.10,
            fuel_type=None,
            fuel_price=None,
            vom_cost=5.0,
            vintage="storage2",
        ),
        # Thermal generators
        ReEDSGenerator(
            name="thermal_01",
            region=simple_region,
            technology="gas_cc",
            capacity=300.0,
            category="thermal",
            heat_rate=8.5,
            forced_outage_rate=0.08,
            planned_outage_rate=0.15,
            fuel_type="natural_gas",
            fuel_price=4.0,
            vom_cost=3.5,
            vintage="thermal1",
        ),
        # Solar generators
        ReEDSGenerator(
            name="solar_01",
            region=simple_region,
            technology="upv",
            capacity=100.0,
            category="solar",
            heat_rate=None,
            forced_outage_rate=0.02,
            planned_outage_rate=0.05,
            fuel_type=None,
            fuel_price=None,
            vom_cost=0.0,
            vintage="solar1",
        ),
    ]

    for gen in generators:
        system.add_component(gen)

        emission = ReEDSEmission(
            emission_type=EmissionType.CO2,
            rate=0.0 if gen.category in ["storage", "solar"] else 0.4,
        )
        system.add_supplemental_attribute(gen, emission)

    return system


def test_break_generators_basic(system_with_storage_generators):
    """Test basic generator breaking functionality."""
    system = system_with_storage_generators
    capacity_threshold = 10
    reference_generators = {
        "storage": {"avg_capacity_MW": 100},
    }

    original_count = len(list(system.get_components(ReEDSGenerator)))
    system = break_generators(system, reference_generators, capacity_threshold)

    updated_generators = list(system.get_components(ReEDSGenerator))
    # Should have more generators after breaking
    assert len(updated_generators) > original_count

    # Check that broken generators have the right capacity
    smaller_generators = [gen for gen in updated_generators if gen.capacity == 100]
    assert len(smaller_generators) > 0

    # Should have generators with original capacity reduced
    remaining_original = [
        gen for gen in updated_generators if gen.capacity == 100 and gen.name.startswith("large_storage")
    ]
    assert len(remaining_original) > 0


def test_break_generators_with_non_break_techs(system_with_mixed_generators):
    """Test that generators in non_break_techs are not broken."""
    system = system_with_mixed_generators
    capacity_threshold = 10
    reference_generators = {
        "storage": {"avg_capacity_MW": 100},
        "thermal": {"avg_capacity_MW": 150},
    }
    non_break_techs = ["storage"]

    original_storage_generators = [
        gen for gen in system.get_components(ReEDSGenerator) if gen.category == "storage"
    ]
    original_storage_capacities = [gen.capacity for gen in original_storage_generators]

    system = break_generators(system, reference_generators, capacity_threshold, non_break_techs)

    storage_generators = [gen for gen in system.get_components(ReEDSGenerator) if gen.category == "storage"]
    current_storage_capacities = [gen.capacity for gen in storage_generators]

    # Original storage capacities should be preserved
    assert original_storage_capacities == current_storage_capacities


def test_break_generators_capacity_threshold(system_with_mixed_generators):
    """Test that generators below capacity threshold are dropped."""
    system = system_with_mixed_generators
    capacity_threshold = 80  # High threshold
    reference_generators = {
        "solar": {"avg_capacity_MW": 50},  # Will create remainder of 50 < threshold
    }

    original_count = len(list(system.get_components(ReEDSGenerator)))
    system = break_generators(system, reference_generators, capacity_threshold)

    updated_generators = list(system.get_components(ReEDSGenerator))
    # Some generators might be dropped due to small remainder
    assert len(updated_generators) <= original_count + 1


def test_break_generators_multiple_categories(system_with_mixed_generators):
    """Test breaking generators across multiple categories."""
    system = system_with_mixed_generators
    capacity_threshold = 10
    reference_generators = {
        "storage": {"avg_capacity_MW": 75},
        "thermal": {"avg_capacity_MW": 100},
        "solar": {"avg_capacity_MW": 50},
    }

    original_count = len(list(system.get_components(ReEDSGenerator)))
    system = break_generators(system, reference_generators, capacity_threshold)

    updated_generators = list(system.get_components(ReEDSGenerator))
    # Should have significantly more generators after breaking multiple categories
    assert len(updated_generators) > original_count

    # Check that generators with reference capacities exist
    ref_capacity_generators = [
        gen
        for gen in updated_generators
        if gen.capacity in [75, 100, 50]  # Reference capacities
    ]
    assert len(ref_capacity_generators) > 0


def test_break_generators_emissions_copied(system_with_storage_generators):
    """Test that emission attributes are copied to broken generators."""
    system = system_with_storage_generators
    capacity_threshold = 10
    reference_generators = {
        "storage": {"avg_capacity_MW": 100},
    }

    system = break_generators(system, reference_generators, capacity_threshold)

    # All generators should have emission attributes
    all_generators = list(system.get_components(ReEDSGenerator))

    for gen in all_generators:
        emissions = system.get_supplemental_attributes_with_component(gen, ReEDSEmission)
        assert len(emissions) > 0

        for emission in emissions:
            assert emission.emission_type == EmissionType.CO2


def test_break_generators_no_matching_reference():
    """Test behavior when no reference generators match."""
    system = System()
    region = ReEDSRegion(name="test_region")
    system.add_component(region)

    gen = ReEDSGenerator(
        name="unknown_tech",
        region=region,
        technology="unknown",
        capacity=200.0,
        category="unknown",
        heat_rate=None,
        forced_outage_rate=0.05,
        planned_outage_rate=0.10,
        fuel_type=None,
        fuel_price=None,
        vom_cost=5.0,
        vintage="gen1",
    )
    system.add_component(gen)

    capacity_threshold = 10
    reference_generators = {
        "storage": {"avg_capacity_MW": 100},
    }

    original_count = len(list(system.get_components(ReEDSGenerator)))
    system = break_generators(system, reference_generators, capacity_threshold)

    updated_generators = list(system.get_components(ReEDSGenerator))
    assert len(updated_generators) == original_count
