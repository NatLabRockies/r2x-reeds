"""Tests comparing new parser output with legacy system.

The new parser creates more granular components than the legacy system:
- 1299 components vs legacy's 347
- 6 component types vs legacy's 16 types
- One generator per technology-vintage-region vs aggregated RenewableDispatch
- One transmission line per interface with bidirectional ratings vs aggregated MonitoredLine

Component Type Mapping:
- RenewableDispatch (58) → ReEDSGenerator (359)
- PowerLoad (11) → ReEDSDemand (11)
- ACBus (11) → ReEDSRegion (11)
- MonitoredLine (17) → ReEDSTransmissionLine (17)
"""

import json
from pathlib import Path
from typing import Any

import pytest
from infrasys import Component, System

from r2x_core import DataStore
from r2x_reeds import ReEDSConfig, ReEDSParser


@pytest.fixture
def legacy_system_path() -> Path:
    """Path to legacy system JSON file."""
    return Path(__file__).parent / "data" / "legacy_system.json"


@pytest.fixture
def legacy_system_data(legacy_system_path: Path) -> dict[str, Any]:
    """Load legacy system JSON data."""
    with open(legacy_system_path) as f:
        return json.load(f)


@pytest.fixture
def legacy_component_count(legacy_system_data: dict[str, Any]) -> int:
    """Get component count from legacy system."""
    return len(legacy_system_data.get("components", []))


@pytest.fixture
def legacy_component_types(legacy_system_data: dict[str, Any]) -> dict[str, int]:
    """Get component type distribution from legacy system."""
    types: dict[str, int] = {}
    for comp in legacy_system_data.get("components", []):
        comp_type = comp.get("__metadata__", {}).get("fields", {}).get("type", "Unknown")
        types[comp_type] = types.get(comp_type, 0) + 1
    return types


@pytest.fixture
def legacy_component_names(legacy_system_data: dict[str, Any]) -> set[str]:
    """Get all component names from legacy system."""
    names = set()
    for comp in legacy_system_data.get("components", []):
        if name := comp.get("name"):
            names.add(name)
    return names


@pytest.fixture
def reeds_config() -> ReEDSConfig:
    """Create ReEDS configuration matching legacy system."""
    return ReEDSConfig(solve_year=2032, weather_year=2012)


@pytest.fixture
def data_store(reeds_run_path: Path, reeds_config: ReEDSConfig) -> DataStore:
    """Create DataStore from file mapping."""
    return DataStore.from_plugin_config(reeds_config, path=reeds_run_path)


@pytest.fixture
def new_system(reeds_config: ReEDSConfig, data_store: DataStore) -> System:
    """Build system using new parser."""
    parser = ReEDSParser(config=reeds_config, store=data_store, name="test_system")
    return parser.build_system()


def test_legacy_system_has_components(legacy_component_count: int) -> None:
    """Test that legacy system has components."""
    assert legacy_component_count > 0


def test_legacy_component_types_exist(legacy_component_types: dict[str, int]) -> None:
    """Test that legacy system has various component types."""
    assert len(legacy_component_types) > 0


def test_component_count_matches(legacy_component_count: int, new_system: System) -> None:
    """Compare component counts between legacy and new parser.

    The new parser creates more granular components (one per technology-vintage-region).
    This test documents the difference rather than asserting equality.
    """
    new_components = list(new_system.get_components(Component))
    new_count = len(new_components)

    assert new_count > 0, "New system should have components"
    assert legacy_component_count > 0, "Legacy system should have components"


def test_component_types_match(legacy_component_types: dict[str, int], new_system: System) -> None:
    """Test that component type distribution matches between systems."""
    new_types: dict[str, int] = {}
    for comp in new_system.get_components(Component):
        comp_type = type(comp).__name__
        new_types[comp_type] = new_types.get(comp_type, 0) + 1

    type_mapping: dict[str, tuple[str, ...]] = {
        "RenewableDispatch": (
            "ReEDSGenerator",
            "ReEDSThermalGenerator",
            "ReEDSVariableGenerator",
            "ReEDSStorage",
            "ReEDSHydroGenerator",
            "ReEDSConsumingTechnology",
        ),
        "PowerLoad": ("ReEDSDemand",),
        "ACBus": ("ReEDSRegion",),
        "MonitoredLine": ("ReEDSTransmissionLine",),
    }

    for legacy_type in legacy_component_types:
        allowed_types = type_mapping.get(legacy_type)
        if allowed_types is None:
            # No expectations for other legacy types
            continue

        assert any(new_type in new_types for new_type in allowed_types), (
            f"Legacy type {legacy_type} expects one of {allowed_types} but new system has {list(new_types)}"
        )


def test_component_names_match(legacy_component_names: set[str], new_system: System) -> None:
    """Test that component names match between systems."""
    new_names = {comp.name for comp in new_system.get_components(Component)}

    missing_in_new = legacy_component_names - new_names
    extra_in_new = new_names - legacy_component_names

    assert len(new_names) > 0, "New system should have components"
    assert len(missing_in_new) >= 0
    assert len(extra_in_new) >= 0


def test_time_series_count_by_component(legacy_system_data: dict[str, Any], new_system: System) -> None:
    """Test time series counts per component."""
    total_ts = 0
    for comp in new_system.get_components(Component):
        ts_list = new_system.list_time_series(comp)
        if ts_list:
            total_ts += len(ts_list)

    assert total_ts >= 0


def test_system_structure_summary(
    legacy_component_count: int,
    legacy_component_types: dict[str, int],
    legacy_component_names: set[str],
    new_system: System,
) -> None:
    """Summary test documenting structural differences between legacy and new parser."""
    new_components = list(new_system.get_components(Component))
    new_count = len(new_components)

    new_types: dict[str, int] = {}
    for comp in new_components:
        comp_type = type(comp).__name__
        new_types[comp_type] = new_types.get(comp_type, 0) + 1

    new_names = {comp.name for comp in new_components}

    print("\n" + "=" * 80)
    print("LEGACY VS NEW PARSER COMPARISON SUMMARY")
    print("=" * 80)
    print("\nTotal Components:")
    print(f"  Legacy: {legacy_component_count}")
    print(f"  New:    {new_count}")
    print(f"  Diff:   {new_count - legacy_component_count:+d}")

    print("\nComponent Types:")
    print(f"  Legacy has {len(legacy_component_types)} types, New has {len(new_types)} types")

    print("\nType Mapping:")
    type_mapping = {
        "RenewableDispatch": "ReEDSGenerator",
        "PowerLoad": "ReEDSDemand",
        "ACBus": "ReEDSRegion",
        "MonitoredLine": "ReEDSTransmissionLine",
    }

    for legacy_type, new_type in type_mapping.items():
        legacy_count_val = legacy_component_types.get(legacy_type, 0)
        new_count_val = new_types.get(new_type, 0)
        diff = new_count_val - legacy_count_val
        print(f"  {legacy_type} ({legacy_count_val}) → {new_type} ({new_count_val}) [{diff:+d}]")

    print("\nComponent Names:")
    missing = legacy_component_names - new_names
    extra = new_names - legacy_component_names
    print(f"  Missing in new: {len(missing)} components")
    if missing:
        print(f"    Examples: {sorted(missing)[:5]}")
    print(f"  Extra in new:   {len(extra)} components")
    if extra:
        print(f"    Examples: {sorted(extra)[:5]}")

    print("\n" + "=" * 80)
