"""Tests for hydro availability profile methods."""

import polars as pl
import pytest

from r2x_reeds.models.components import ReEDSHydroGenerator
from r2x_reeds.parser_utils import calculate_hydro_profiles_for_generator

pytestmark = [pytest.mark.integration, pytest.mark.polars]


def test_calculate_hydro_profiles_matches_region_case_insensitively(hydro_generator):
    generator = hydro_generator.model_copy(
        update={"region": hydro_generator.region.model_copy(update={"name": "AL"})}
    )
    hydro_data = pl.DataFrame(
        {
            "year": [2035] * 12,
            "technology": ["hyd"] * 12,
            "region": ["al"] * 12,
            "month_num": list(range(1, 13)),
            "hydro_cf": [0.5] * 12,
        },
        schema_overrides={"year": pl.Int64, "month_num": pl.Int64},
    )
    capacity_adjustment = pl.DataFrame(
        {
            "technology": ["hyd"] * 12,
            "region": ["al"] * 12,
            "month_num": list(range(1, 13)),
            "capacity_adjustment": [1.0] * 12,
        },
        schema_overrides={"month_num": pl.Int64},
    )

    results = calculate_hydro_profiles_for_generator(
        generator,
        hydro_data=hydro_data,
        solve_years=[2035],
        weather_year=2012,
        hydro_capacity_adjustment=capacity_adjustment,
    )

    assert [result.name for result in results] == ["hydro_budget", "max_active_power"]


def test_hydro_time_series(example_system):
    components = list(example_system.get_components(ReEDSHydroGenerator))
    assert components

    for component in components:
        name = "hydro_budget" if component.is_dispatchable else "max_active_power"
        ts = example_system.get_time_series(component, name=name)
        assert ts.name == name
        assert ts.length == 8760
        assert sum(ts.data) != 0.0
