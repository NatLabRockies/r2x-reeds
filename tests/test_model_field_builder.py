"""Tests for the forthcoming model field builder utilities."""

from __future__ import annotations

from r2x_reeds import parser_utils
from r2x_reeds.models.components import ReEDSRegion


def test_generator_field_builder_resolves_region(example_system):
    """Future builder should translate region ids into cached components."""
    row = {
        "name": "coal_example",
        "technology": "coal_new",
        "region": "p1",
        "capacity": 100.0,
    }

    fields = parser_utils._build_generator_field_map(row=row, system=example_system)

    region_component = example_system.get_component(ReEDSRegion, "p1")
    assert fields["region"] is region_component
