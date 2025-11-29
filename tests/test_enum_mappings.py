"""Tests for enum_mappings module.

Tests verify that enum mapping functions correctly:
- Map valid string values to their enum counterparts
- Handle case-insensitive matching where appropriate
- Return errors for unknown values
- Apply special logic (like keyword matching for emission sources)
- Provide sensible defaults (like COMBUSTION for None)
"""

from __future__ import annotations

import pytest


@pytest.mark.unit
def test_map_reserve_type_spinning() -> None:
    from r2x_reeds.enum_mappings import map_reserve_type
    from r2x_reeds.models.enums import ReserveType

    result = map_reserve_type("SPINNING")
    assert result.is_ok()
    assert result.ok() == ReserveType.SPINNING


@pytest.mark.unit
def test_map_reserve_type_flexibility() -> None:
    from r2x_reeds.enum_mappings import map_reserve_type
    from r2x_reeds.models.enums import ReserveType

    result = map_reserve_type("FLEXIBILITY")
    assert result.is_ok()
    assert result.ok() == ReserveType.FLEXIBILITY


@pytest.mark.unit
def test_map_reserve_type_regulation() -> None:
    from r2x_reeds.enum_mappings import map_reserve_type
    from r2x_reeds.models.enums import ReserveType

    result = map_reserve_type("REGULATION")
    assert result.is_ok()
    assert result.ok() == ReserveType.REGULATION


@pytest.mark.unit
def test_map_reserve_type_case_insensitive() -> None:
    from r2x_reeds.enum_mappings import map_reserve_type
    from r2x_reeds.models.enums import ReserveType

    for variant in ["spinning", "Spinning", "SPINNING", "sPiNnInG"]:
        result = map_reserve_type(variant)
        assert result.is_ok()
        assert result.ok() == ReserveType.SPINNING


@pytest.mark.unit
def test_map_reserve_type_unknown() -> None:
    from r2x_reeds.enum_mappings import map_reserve_type

    result = map_reserve_type("UNKNOWN_TYPE")
    assert result.is_err()
    assert "Unknown reserve type" in str(result.err())


@pytest.mark.unit
def test_map_reserve_type_empty_string() -> None:
    from r2x_reeds.enum_mappings import map_reserve_type

    result = map_reserve_type("")
    assert result.is_err()


@pytest.mark.unit
def test_map_reserve_direction_up() -> None:
    from r2x_reeds.enum_mappings import map_reserve_direction
    from r2x_reeds.models.enums import ReserveDirection

    result = map_reserve_direction("up")
    assert result.is_ok()
    assert result.ok() == ReserveDirection.UP


@pytest.mark.unit
def test_map_reserve_direction_down() -> None:
    from r2x_reeds.enum_mappings import map_reserve_direction
    from r2x_reeds.models.enums import ReserveDirection

    result = map_reserve_direction("down")
    assert result.is_ok()
    assert result.ok() == ReserveDirection.DOWN


@pytest.mark.unit
def test_map_reserve_direction_case_insensitive() -> None:
    from r2x_reeds.enum_mappings import map_reserve_direction
    from r2x_reeds.models.enums import ReserveDirection

    for variant in ["up", "Up", "UP", "uP"]:
        result = map_reserve_direction(variant)
        assert result.is_ok()
        assert result.ok() == ReserveDirection.UP


@pytest.mark.unit
def test_map_reserve_direction_unknown() -> None:
    from r2x_reeds.enum_mappings import map_reserve_direction

    result = map_reserve_direction("left")
    assert result.is_err()
    assert "Unknown direction" in str(result.err())


@pytest.mark.unit
def test_map_emission_type_co2() -> None:
    from r2x_reeds.enum_mappings import map_emission_type
    from r2x_reeds.models.enums import EmissionType

    result = map_emission_type("CO2")
    assert result.is_ok()
    assert result.ok() == EmissionType.CO2


@pytest.mark.unit
def test_map_emission_type_case_insensitive() -> None:
    from r2x_reeds.enum_mappings import map_emission_type
    from r2x_reeds.models.enums import EmissionType

    for variant in ["co2", "Co2", "CO2", "cO2"]:
        result = map_emission_type(variant)
        assert result.is_ok()
        assert result.ok() == EmissionType.CO2


@pytest.mark.unit
def test_map_emission_type_with_whitespace() -> None:
    from r2x_reeds.enum_mappings import map_emission_type
    from r2x_reeds.models.enums import EmissionType

    result = map_emission_type("  CO2  ")
    assert result.is_ok()
    assert result.ok() == EmissionType.CO2


@pytest.mark.unit
def test_map_emission_type_unknown() -> None:
    from r2x_reeds.enum_mappings import map_emission_type

    result = map_emission_type("UNKNOWN_EMISSION")
    assert result.is_err()
    assert "Unknown emission type" in str(result.err())


@pytest.mark.unit
def test_map_emission_source_combustion() -> None:
    from r2x_reeds.enum_mappings import map_emission_source
    from r2x_reeds.models.enums import EmissionSource

    result = map_emission_source("COMBUSTION")
    assert result.is_ok()
    assert result.ok() == EmissionSource.COMBUSTION


@pytest.mark.unit
def test_map_emission_source_precombustion() -> None:
    from r2x_reeds.enum_mappings import map_emission_source
    from r2x_reeds.models.enums import EmissionSource

    result = map_emission_source("PRECOMBUSTION")
    assert result.is_ok()
    assert result.ok() == EmissionSource.PRECOMBUSTION


@pytest.mark.unit
def test_map_emission_source_process() -> None:
    from r2x_reeds.enum_mappings import map_emission_source
    from r2x_reeds.models.enums import EmissionSource

    result = map_emission_source("PROCESS")
    assert result.is_ok()
    assert result.ok() == EmissionSource.PRECOMBUSTION


@pytest.mark.unit
def test_map_emission_source_upstream() -> None:
    from r2x_reeds.enum_mappings import map_emission_source
    from r2x_reeds.models.enums import EmissionSource

    result = map_emission_source("UPSTREAM")
    assert result.is_ok()
    assert result.ok() == EmissionSource.PRECOMBUSTION


@pytest.mark.unit
def test_map_emission_source_case_insensitive() -> None:
    from r2x_reeds.enum_mappings import map_emission_source
    from r2x_reeds.models.enums import EmissionSource

    for variant in ["combustion", "Combustion", "COMBUSTION", "coMBUstion"]:
        result = map_emission_source(variant)
        assert result.is_ok()
        assert result.ok() == EmissionSource.COMBUSTION


@pytest.mark.unit
def test_map_emission_source_with_whitespace() -> None:
    from r2x_reeds.enum_mappings import map_emission_source
    from r2x_reeds.models.enums import EmissionSource

    result = map_emission_source("  COMBUSTION  ")
    assert result.is_ok()
    assert result.ok() == EmissionSource.COMBUSTION


@pytest.mark.unit
def test_map_emission_source_none_defaults_to_combustion() -> None:
    from r2x_reeds.enum_mappings import map_emission_source
    from r2x_reeds.models.enums import EmissionSource

    result = map_emission_source(None)
    assert result.is_ok()
    assert result.ok() == EmissionSource.COMBUSTION


@pytest.mark.unit
def test_map_emission_source_unknown() -> None:
    from r2x_reeds.enum_mappings import map_emission_source

    result = map_emission_source("UNKNOWN_SOURCE")
    assert result.is_err()
    assert "Unknown emission source" in str(result.err())


@pytest.mark.unit
def test_map_emission_source_partial_match_combustion() -> None:
    from r2x_reeds.enum_mappings import map_emission_source
    from r2x_reeds.models.enums import EmissionSource

    result = map_emission_source("my_combustion_value")
    assert result.is_ok()
    assert result.ok() == EmissionSource.COMBUSTION


@pytest.mark.unit
def test_map_emission_source_partial_match_precombustion() -> None:
    from r2x_reeds.enum_mappings import map_emission_source
    from r2x_reeds.models.enums import EmissionSource

    result = map_emission_source("precombustion_stage")
    assert result.is_ok()
    assert result.ok() == EmissionSource.PRECOMBUSTION


@pytest.mark.unit
@pytest.mark.parametrize(
    "reserve_type,expected_error",
    [
        ("", "Unknown reserve type"),
        ("INVALID", "Unknown reserve type"),
        ("spinning_reserve", "Unknown reserve type"),
    ],
)
def test_map_reserve_type_various_failures(reserve_type: str, expected_error: str) -> None:
    from r2x_reeds.enum_mappings import map_reserve_type

    result = map_reserve_type(reserve_type)
    assert result.is_err()
    assert expected_error in str(result.err())


@pytest.mark.unit
@pytest.mark.parametrize(
    "direction,expected_error",
    [
        ("", "Unknown direction"),
        ("LEFT", "Unknown direction"),
        ("sideways", "Unknown direction"),
    ],
)
def test_map_reserve_direction_various_failures(direction: str, expected_error: str) -> None:
    from r2x_reeds.enum_mappings import map_reserve_direction

    result = map_reserve_direction(direction)
    assert result.is_err()
    assert expected_error in str(result.err())
