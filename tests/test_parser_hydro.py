"""Tests for hydro availability profile methods."""

import pytest

from r2x_reeds.models.components import ReEDSHydroGenerator

pytestmark = [pytest.mark.integration, pytest.mark.polars]


def test_hydro_time_series(example_system):
    components = list(example_system.get_components(ReEDSHydroGenerator))
    assert components

    for component in components:
        name = "hydro_budget" if component.is_dispatchable else "max_active_power"
        ts = example_system.get_time_series(component, name=name)
        assert ts.name == name
        assert ts.length == 8760
        assert sum(ts.data) != 0.0
