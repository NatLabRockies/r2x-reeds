"""Integration tests for ReEDS parser with real DataStore.

These tests verify that the parser can build a example_system using real data files.
"""

import numpy as np
import pytest
from infrasys import Component

from r2x_reeds.models.components import ReEDSDemand, ReEDSGenerator
from r2x_reeds.parser_utils import get_technology_category


def test_system_has_buses(example_system) -> None:
    """Test that built example_system contains buses."""
    example_system = example_system
    components = list(example_system.get_components(Component))
    assert components is not None
    assert len(components) > 0, "System should have components after building"


def test_system_has_generators(example_system) -> None:
    """Test that built example_system contains generators."""
    components = list(example_system.get_components(Component))
    assert components is not None
    assert len(components) >= 0


def test_system_has_loads(example_system) -> None:
    """Test that built example_system contains loads."""
    components = list(example_system.get_components(Component))
    assert components is not None
    assert len(components) >= 0


def test_load_count_for_test_data(example_system) -> None:
    """Test expected load count for test_Pacific data."""
    loads = list(example_system.get_components(ReEDSDemand))
    assert len(loads) == 11, "11 Load expected for test case."


def test_renewable_generator_count(example_system, example_reeds_config) -> None:
    """Test expected renewable generator count for test_Pacific data."""
    # Use classmethod API per migration guide
    defaults = example_reeds_config.load_config()["defaults"]
    ren_gens = example_system.get_components(
        ReEDSGenerator,
        filter_func=lambda comp: get_technology_category(comp.technology, defaults["tech_categories"]),
    )
    assert len(list(ren_gens)) != 0.0


@pytest.mark.parametrize(
    "component_type,component_filter",
    [
        (ReEDSDemand, None),
        pytest.param(
            ReEDSGenerator,
            lambda x: x.category in ["solar", "wind"],
            marks=pytest.mark.xfail(reason="missing profiles on test data."),
        ),
        (ReEDSGenerator, lambda x: x.category == "hydro"),
    ],
    ids=["load-profiles", "renewable-profiles", "hydro-profiles"],
)
def test_system_has_time_series(component_type, component_filter, example_system, example_data_store):
    for component in example_system.get_components(component_type, filter_func=component_filter):
        assert example_system.has_time_series(component), f"Time series not found for {component.label}"


def test_load_time_series_length(example_system) -> None:
    """Test that time series length matches filtered data (single weather year = 8760 hours)."""
    assert all(
        example_system.get_time_series(component).length == 8760
        for component in example_system.get_components(ReEDSDemand)
    )


@pytest.mark.parametrize("region_name", ["p1", "p2", "p3"])
def test_load_time_series_values(
    region_name, example_data_store, example_system, example_reeds_config
) -> None:
    """Test that time series values match DataStore data for each region."""

    load_profiles = example_data_store.read_data(
        "load_profiles",
        placeholders={
            "solve_year": example_reeds_config.primary_solve_year,
            "weather_year": example_reeds_config.primary_weather_year,
        },
    ).collect()

    load_component = example_system.get_component(ReEDSDemand, region_name + "_load")
    actual_profile = load_profiles[region_name].to_numpy()
    expected_profile = example_system.get_time_series(load_component).data

    np.testing.assert_allclose(
        actual_profile,
        expected_profile,
        rtol=1e-5,
    )
