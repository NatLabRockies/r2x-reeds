"""Tests for hydro budget and rating profile methods."""

import pytest

from r2x_reeds.models.components import ReEDSGenerator

pytestmark = [pytest.mark.integration]


def test_hydro_time_series(example_system):
    for component in example_system.get_components(
        ReEDSGenerator, filter_func=lambda comp: comp.technology == "hydro"
    ):
        ts = example_system.get_time_series(component)
        assert ts.name == "hydro_budget"
        assert ts.length == 8760
        assert sum(ts.data) != 0.0
