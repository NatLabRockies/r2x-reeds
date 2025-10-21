import pytest
from infrasys import System

from r2x_core.store import DataStore
from r2x_reeds.config import ReEDSConfig
from r2x_reeds.models.base import FromTo_ToFrom
from r2x_reeds.models.components import ReEDSInterface, ReEDSRegion, ReEDSTransmissionLine
from r2x_reeds.parser import ReEDSParser
from r2x_reeds.plugins.hurdle_rate import update_system


@pytest.fixture
def simple_config():
    """Create a simple ReEDS config."""
    return ReEDSConfig(
        name="TestHurdleRate",
        weather_year=2012,
        solve_year=2035,
    )


@pytest.fixture
def mock_data_store():
    """Create a mock data store."""
    return DataStore()


@pytest.fixture
def system_with_transmission():
    """Create a system with transmission lines between regions."""
    system = System()

    # Create regions
    region_1 = ReEDSRegion(name="p1", max_active_power=1000.0)
    region_2 = ReEDSRegion(name="p2", max_active_power=1000.0)
    region_3 = ReEDSRegion(name="p3", max_active_power=1000.0)
    system.add_components(region_1, region_2, region_3)

    # Create interfaces
    interface_1_2 = ReEDSInterface(
        name="p1_to_p2",
        from_region=region_1,
        to_region=region_2,
    )
    interface_1_3 = ReEDSInterface(
        name="p1_to_p3",
        from_region=region_1,
        to_region=region_3,
    )
    interface_2_3 = ReEDSInterface(
        name="p2_to_p3",
        from_region=region_2,
        to_region=region_3,
    )
    system.add_components(interface_1_2, interface_1_3, interface_2_3)

    # Create transmission lines
    line_1_2 = ReEDSTransmissionLine(
        name="line_p1_p2",
        interface=interface_1_2,
        max_active_power=FromTo_ToFrom(from_to=500.0, to_from=500.0),
        hurdle_rate=0.001,
    )

    line_1_3 = ReEDSTransmissionLine(
        name="line_p1_p3",
        interface=interface_1_3,
        max_active_power=FromTo_ToFrom(from_to=300.0, to_from=300.0),
        hurdle_rate=0.002,
    )

    line_2_3 = ReEDSTransmissionLine(
        name="line_p2_p3",
        interface=interface_2_3,
        max_active_power=FromTo_ToFrom(from_to=400.0, to_from=400.0),
        hurdle_rate=None,
    )

    system.add_components(line_1_2, line_1_3, line_2_3)

    return system


def test_hurdle_rate_basic(simple_config, system_with_transmission):
    """Test basic hurdle rate functionality."""
    system = system_with_transmission
    hurdle_rate_value = 0.006

    new_system = update_system(
        config=simple_config,
        system=system,
        parser=None,
        hurdle_rate=hurdle_rate_value
    )

    assert isinstance(new_system, System)

    lines = list(new_system.get_components(ReEDSTransmissionLine))
    assert len(lines) == 3

    for line in lines:
        assert line.hurdle_rate == hurdle_rate_value


def test_hurdle_rate_preserves_existing_rates(simple_config, system_with_transmission):
    """Test that hurdle rate update preserves existing rates when no new rate provided."""
    system = system_with_transmission

    original_lines = {line.name: line.hurdle_rate for line in system.get_components(ReEDSTransmissionLine)}

    new_system = update_system(
        config=simple_config,
        system=system,
        parser=None,
        hurdle_rate=None
    )

    assert isinstance(new_system, System)

    # Check that original hurdle rates are preserved
    for line in new_system.get_components(ReEDSTransmissionLine):
        assert line.hurdle_rate == original_lines[line.name]


def test_hurdle_rate_with_parser(simple_config, system_with_transmission, mock_data_store):
    """Test hurdle rate functionality with parser data."""
    system = system_with_transmission

    parser = ReEDSParser(config=simple_config, data_store=mock_data_store)
    parser.data = {}

    hurdle_rate_value = 0.008

    new_system = update_system(
        config=simple_config,
        parser=parser,
        system=system,
        hurdle_rate=hurdle_rate_value
    )

    assert isinstance(new_system, System)

    # Verify all lines have the new hurdle rate
    for line in new_system.get_components(ReEDSTransmissionLine):
        assert line.hurdle_rate == hurdle_rate_value


def test_hurdle_rate_zero_value(simple_config, system_with_transmission):
    """Test hurdle rate with zero value."""
    system = system_with_transmission
    hurdle_rate_value = 0.0

    new_system = update_system(
        config=simple_config,
        system=system,
        parser=None,
        hurdle_rate=hurdle_rate_value
    )

    assert isinstance(new_system, System)

    for line in new_system.get_components(ReEDSTransmissionLine):
        assert line.hurdle_rate == 0.0


def test_hurdle_rate_no_transmission_lines(simple_config):
    """Test hurdle rate functionality when no transmission lines exist."""
    system = System()

    # Add regions but no transmission lines
    region_1 = ReEDSRegion(name="p1", max_active_power=1000.0)
    region_2 = ReEDSRegion(name="p2", max_active_power=1000.0)
    system.add_components(region_1, region_2)

    hurdle_rate_value = 0.005

    new_system = update_system(
        config=simple_config,
        system=system,
        parser=None,
        hurdle_rate=hurdle_rate_value
    )

    assert isinstance(new_system, System)
    assert len(list(new_system.get_components(ReEDSTransmissionLine))) == 0


def test_hurdle_rate_selective_update(simple_config):
    """Test hurdle rate update on specific transmission lines."""
    system = System()

    # Create regions with different hurdle_region attributes
    region_1 = ReEDSRegion(name="p1", hurdle_region="hurdle_zone_1")
    region_2 = ReEDSRegion(name="p2", hurdle_region="hurdle_zone_1")
    region_3 = ReEDSRegion(name="p3", hurdle_region="hurdle_zone_2")
    system.add_components(region_1, region_2, region_3)

    # Create interfaces
    interface_same_zone = ReEDSInterface(
        name="same_zone",
        from_region=region_1,
        to_region=region_2,
    )
    interface_diff_zone = ReEDSInterface(
        name="diff_zone",
        from_region=region_1,
        to_region=region_3,
    )
    system.add_components(interface_same_zone, interface_diff_zone)

    # Create transmission lines
    line_same_zone = ReEDSTransmissionLine(
        name="line_same_zone",
        interface=interface_same_zone,
        max_active_power=FromTo_ToFrom(from_to=500.0, to_from=500.0),
        hurdle_rate=0.001,
    )

    line_diff_zone = ReEDSTransmissionLine(
        name="line_diff_zone",
        interface=interface_diff_zone,
        max_active_power=FromTo_ToFrom(from_to=300.0, to_from=300.0),
        hurdle_rate=0.001,
    )

    system.add_components(line_same_zone, line_diff_zone)

    hurdle_rate_value = 0.010

    new_system = update_system(
        config=simple_config,
        system=system,
        parser=None,
        hurdle_rate=hurdle_rate_value
    )

    assert isinstance(new_system, System)

    # Both lines should have the new hurdle rate since we're applying globally
    for line in new_system.get_components(ReEDSTransmissionLine):
        assert line.hurdle_rate == hurdle_rate_value


def test_hurdle_rate_large_value(simple_config, system_with_transmission):
    """Test hurdle rate with large value."""
    system = system_with_transmission
    hurdle_rate_value = 100.0  # Large hurdle rate

    new_system = update_system(
        config=simple_config,
        system=system,
        parser=None,
        hurdle_rate=hurdle_rate_value
    )

    assert isinstance(new_system, System)

    # Check that all transmission lines have the large hurdle rate
    for line in new_system.get_components(ReEDSTransmissionLine):
        assert line.hurdle_rate == hurdle_rate_value


def test_hurdle_rate_system_modification(simple_config, system_with_transmission):
    """Test that the system is modified in place (expected behavior)."""
    system = system_with_transmission
    hurdle_rate_value = 0.015

    original_rates = {line.name: line.hurdle_rate for line in system.get_components(ReEDSTransmissionLine)}

    new_system = update_system(
        config=simple_config,
        system=system,
        parser=None,
        hurdle_rate=hurdle_rate_value
    )

    assert new_system is system

    for line in system.get_components(ReEDSTransmissionLine):
        assert line.hurdle_rate == hurdle_rate_value
        if original_rates[line.name] is not None:
            assert line.hurdle_rate != original_rates[line.name]

    for line in new_system.get_components(ReEDSTransmissionLine):
        assert line.hurdle_rate == hurdle_rate_value
