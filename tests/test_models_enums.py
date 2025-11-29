"""Tests for ReEDS model enumerations."""

from r2x_reeds.models.enums import EmissionType, ReserveDirection, ReserveType


def test_emission_type_co2_exists():
    """Test that CO2 emission type exists."""
    assert EmissionType.CO2 == "CO2"


def test_emission_type_nox_exists():
    """Test that NOx emission type exists."""
    assert EmissionType.NOX == "NOx"


def test_emission_type_is_string_enum():
    """Test that EmissionType values are strings."""
    assert isinstance(EmissionType.CO2.value, str)


def test_reserve_type_regulation_exists():
    """Test that Regulation reserve type exists."""
    assert ReserveType.REGULATION == "REGULATION"


def test_reserve_type_spinning_exists():
    """Test that Spinning reserve type exists."""
    assert ReserveType.SPINNING == "SPINNING"


def test_reserve_direction_up_exists():
    """Test that Up reserve direction exists."""
    assert ReserveDirection.UP == "Up"


def test_reserve_direction_down_exists():
    """Test that Down reserve direction exists."""
    assert ReserveDirection.DOWN == "Down"


def test_all_emission_types_are_valid():
    """Test that all EmissionType enum members have valid string values."""
    for emission_type in EmissionType:
        assert isinstance(emission_type.value, str)
        assert len(emission_type.value) > 0


def test_all_reserve_types_are_valid():
    """Test that all ReserveType enum members have valid string values."""
    for reserve_type in ReserveType:
        assert isinstance(reserve_type.value, str)
        assert len(reserve_type.value) > 0


def test_all_reserve_directions_are_valid():
    """Test that all ReserveDirection enum members have valid string values."""
    for direction in ReserveDirection:
        assert isinstance(direction.value, str)
        assert len(direction.value) > 0
