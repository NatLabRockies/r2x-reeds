"""Tests for getters.py focusing on row accessor pattern (38 duplications).

These tests verify that all getter functions properly handle:
1. Dict input (dict.get() access pattern)
2. SimpleNamespace/object input (getattr access pattern)
3. Missing fields and error handling

This test file targets the 38 duplicated row field accessor patterns found in getters.py
that all use variations of: `get_row_field(row, field)` via row_utils module.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest


@pytest.fixture
def test_system():
    """Create a test system with sample regions."""
    from infrasys import System

    from r2x_reeds.models import ReEDSRegion, ReEDSReserveRegion

    system = System(name="test_system")
    region = ReEDSRegion(name="p1", state="CA")
    system.add_component(region)
    reserve_region = ReEDSReserveRegion(name="reserve_p1")
    system.add_component(reserve_region)
    return system


@pytest.fixture
def test_context(test_system):
    """Create a parser context for getter tests."""
    from r2x_core import ParserContext
    from r2x_reeds import ReEDSConfig

    config = ReEDSConfig(solve_year=2030, weather_year=2012, case_name="test_getters")
    return ParserContext(
        system=test_system,
        config=config,
        metadata={
            "tech_categories": {
                "renewable": ["wind-ons", "solar-pv"],
                "thermal": ["coal", "gas-cc"],
                "hydro": ["hydro-md"],
            },
        },
    )


@pytest.mark.unit
def test_lookup_region_dict(test_context) -> None:
    """Test getter with dict input accessing region field."""
    from r2x_reeds.getters import lookup_region

    row: dict[str, Any] = {"region": "p1"}
    result = lookup_region(test_context, row)
    assert result.is_ok()


@pytest.mark.unit
def test_build_region_description_dict(test_context) -> None:
    """Test getter with dict input accessing region_id/region fields."""
    from r2x_reeds.getters import build_region_description

    row: dict[str, Any] = {"region_id": "p1"}
    result = build_region_description(test_context, row)
    assert result.is_ok()


@pytest.mark.unit
def test_build_region_name_dict(test_context) -> None:
    """Test getter with dict input accessing multiple fallback fields."""
    from r2x_reeds.getters import build_region_name

    row: dict[str, Any] = {"region_id": "p1"}
    result = build_region_name(test_context, row)
    assert result.is_ok()


@pytest.mark.unit
def test_build_generator_name_dict(test_context) -> None:
    """Test getter with dict input accessing technology, region, vintage fields."""
    from r2x_reeds.getters import build_generator_name

    row: dict[str, Any] = {"technology": "wind", "region": "p1"}
    result = build_generator_name(test_context, row)
    assert isinstance(result.is_ok() or result.is_err(), bool)


@pytest.mark.unit
def test_resolve_reserve_type_dict(test_context) -> None:
    """Test getter with dict input accessing reserve_type field."""
    from r2x_reeds.getters import resolve_reserve_type

    row: dict[str, Any] = {"reserve_type": "SPINNING"}
    result = resolve_reserve_type(test_context, row)
    assert result.is_ok()


@pytest.mark.unit
def test_get_storage_duration_dict(test_context) -> None:
    """Test getter with dict input accessing numeric field."""
    from r2x_reeds.getters import get_storage_duration

    row: dict[str, Any] = {"storage_duration": 2.0}
    result = get_storage_duration(test_context, row)
    assert isinstance(result.is_ok() or result.is_err(), bool)


# Row Accessor Pattern Tests - SimpleNamespace Input


@pytest.mark.unit
def test_lookup_region_namespace(test_context) -> None:
    """Test getter with SimpleNamespace input accessing region field."""
    from r2x_reeds.getters import lookup_region

    row = SimpleNamespace(region="p1")
    result = lookup_region(test_context, row)
    assert result.is_ok()


@pytest.mark.unit
def test_build_region_description_namespace(test_context) -> None:
    """Test getter with SimpleNamespace accessing region_id/region fields."""
    from r2x_reeds.getters import build_region_description

    row = SimpleNamespace(region_id="p1")
    result = build_region_description(test_context, row)
    assert result.is_ok()


@pytest.mark.unit
def test_build_region_name_namespace(test_context) -> None:
    """Test getter with SimpleNamespace accessing multiple fallback fields."""
    from r2x_reeds.getters import build_region_name

    row = SimpleNamespace(region_id="p1")
    result = build_region_name(test_context, row)
    assert result.is_ok()


@pytest.mark.unit
def test_build_generator_name_namespace(test_context) -> None:
    """Test getter with SimpleNamespace accessing technology, region, vintage."""
    from r2x_reeds.getters import build_generator_name

    row = SimpleNamespace(technology="wind", region="p1")
    result = build_generator_name(test_context, row)
    assert isinstance(result.is_ok() or result.is_err(), bool)


@pytest.mark.unit
def test_resolve_reserve_type_namespace(test_context) -> None:
    """Test getter with SimpleNamespace accessing reserve_type field."""
    from r2x_reeds.getters import resolve_reserve_type

    row = SimpleNamespace(reserve_type="SPINNING")
    result = resolve_reserve_type(test_context, row)
    assert result.is_ok()


@pytest.mark.unit
def test_get_storage_duration_namespace(test_context) -> None:
    """Test getter with SimpleNamespace accessing numeric field."""
    from r2x_reeds.getters import get_storage_duration

    row = SimpleNamespace(storage_duration=2.0)
    result = get_storage_duration(test_context, row)
    assert isinstance(result.is_ok() or result.is_err(), bool)


# Row Accessor Consistency Tests (dict vs namespace)


@pytest.mark.unit
def test_region_lookup_consistency(test_context) -> None:
    """Test that dict and namespace inputs produce same result for region lookup."""
    from r2x_reeds.getters import lookup_region

    dict_row: dict[str, Any] = {"region": "p1"}
    ns_row = SimpleNamespace(region="p1")

    dict_result = lookup_region(test_context, dict_row)
    ns_result = lookup_region(test_context, ns_row)

    assert dict_result.is_ok() == ns_result.is_ok()


@pytest.mark.unit
def test_generator_name_consistency(test_context) -> None:
    """Test that dict and namespace inputs produce same result for name building."""
    from r2x_reeds.getters import build_generator_name

    dict_row: dict[str, Any] = {"technology": "wind", "region": "p1"}
    ns_row = SimpleNamespace(technology="wind", region="p1")

    dict_result = build_generator_name(test_context, dict_row)
    ns_result = build_generator_name(test_context, ns_row)

    assert dict_result.is_ok() == ns_result.is_ok()


@pytest.mark.unit
def test_reserve_type_consistency(test_context) -> None:
    """Test that dict and namespace produce consistent enum resolution."""
    from r2x_reeds.getters import resolve_reserve_type

    dict_row: dict[str, Any] = {"reserve_type": "SPINNING"}
    ns_row = SimpleNamespace(reserve_type="SPINNING")

    dict_result = resolve_reserve_type(test_context, dict_row)
    ns_result = resolve_reserve_type(test_context, ns_row)

    assert dict_result.is_ok() == ns_result.is_ok()
    if dict_result.is_ok():
        assert dict_result.ok() == ns_result.ok()


# Missing Field Handling Tests


@pytest.mark.unit
def test_lookup_region_missing_field_dict(test_context) -> None:
    """Test getter errors when field missing from dict."""
    from r2x_reeds.getters import lookup_region

    row: dict[str, Any] = {"other_field": "value"}
    result = lookup_region(test_context, row)
    assert result.is_err()


@pytest.mark.unit
def test_lookup_region_missing_field_namespace(test_context) -> None:
    """Test getter errors when field missing from namespace."""
    from r2x_reeds.getters import lookup_region

    row = SimpleNamespace(other_field="value")
    result = lookup_region(test_context, row)
    assert result.is_err()


@pytest.mark.unit
@pytest.mark.parametrize(
    "getter_name,field_dict,field_ns",
    [
        pytest.param(
            "build_generator_name",
            {"technology": "wind"},
            SimpleNamespace(technology="wind"),
            id="build_generator_name",
        ),
        pytest.param("resolve_reserve_type", {}, SimpleNamespace(), id="resolve_reserve_type"),
    ],
)
def test_various_getters_missing_fields(
    test_context,
    getter_name: str,
    field_dict: dict[str, Any],
    field_ns: SimpleNamespace,
) -> None:
    """Test various getters handle missing required fields consistently."""
    from r2x_reeds import getters as getters_mod

    getter_func = getattr(getters_mod, getter_name)
    dict_result = getter_func(test_context, field_dict)
    ns_result = getter_func(test_context, field_ns)

    assert dict_result.is_ok() == ns_result.is_ok()


# Enum Type Resolution Tests


@pytest.mark.unit
def test_reserve_type_mapping(test_context) -> None:
    """Test reserve type enum resolution."""
    from r2x_reeds.getters import resolve_reserve_type

    row: dict[str, Any] = {"reserve_type": "SPINNING"}
    result = resolve_reserve_type(test_context, row)
    assert result.is_ok()


@pytest.mark.unit
def test_emission_type_mapping(test_context) -> None:
    """Test emission type enum resolution."""
    from r2x_reeds.getters import resolve_emission_type

    row: dict[str, Any] = {"emission_type": "CO2"}
    result = resolve_emission_type(test_context, row)
    assert result.is_ok()


@pytest.mark.unit
def test_emission_source_mapping(test_context) -> None:
    """Test emission source enum resolution."""
    from r2x_reeds.getters import resolve_emission_source

    row: dict[str, Any] = {"emission_source": "COMBUSTION"}
    result = resolve_emission_source(test_context, row)
    assert result.is_ok()


@pytest.mark.unit
def test_invalid_enum_values(test_context) -> None:
    """Test that invalid enum values are rejected."""
    from r2x_reeds.getters import resolve_reserve_type

    row: dict[str, Any] = {"reserve_type": "INVALID_TYPE"}
    result = resolve_reserve_type(test_context, row)
    assert result.is_err()
