"""Tests for hydro availability profile methods."""

import polars as pl
import pytest

from r2x_reeds.models.components import ReEDSHydroGenerator

pytestmark = [pytest.mark.integration, pytest.mark.polars]


def test_prepare_hydro_datasets_normalizes_region_case(parser, monkeypatch):
    hydro_cf = pl.DataFrame(
        {
            "year": [2035] * 12,
            "technology": ["hyd"] * 12,
            "region": ["al"] * 12,
            "month": list(range(1, 13)),
            "hydro_cf": [0.5] * 12,
        }
    ).lazy()
    capacity_adjustment = pl.DataFrame(
        {
            "technology": ["hyd"] * 12,
            "region": ["al"] * 12,
            "month": list(range(1, 13)),
            "capacity_adjustment": [1.0] * 12,
        }
    ).lazy()
    monkeypatch.setattr(
        parser,
        "read_data_file",
        lambda name: hydro_cf if name == "hydro_cf" else capacity_adjustment,
    )
    monkeypatch.setattr(parser, "_hydro_cf_prepared", None)
    monkeypatch.setattr(parser, "_hydro_capacity_adjustment_prepared", None)
    monkeypatch.setattr(parser, "month_map", {})
    monkeypatch.setattr(
        parser,
        "year_month_day_hours",
        pl.DataFrame(
            {
                "year": [2035] * 12,
                "month_num": pl.Series(range(1, 13), dtype=pl.Int16),
                "days_in_month": [31] * 12,
                "hours_in_month": [744] * 12,
            }
        ),
    )

    result = parser._prepare_hydro_datasets()

    assert result.is_ok()
    assert parser._hydro_cf_prepared["region"].unique().to_list() == ["AL"]
    assert parser._hydro_capacity_adjustment_prepared["region"].unique().to_list() == ["AL"]


def test_hydro_time_series(example_system):
    components = list(example_system.get_components(ReEDSHydroGenerator))
    assert components

    for component in components:
        name = "hydro_budget" if component.is_dispatchable else "max_active_power"
        ts = example_system.get_time_series(component, name=name)
        assert ts.name == name
        assert ts.length == 8760
        assert sum(ts.data) != 0.0
