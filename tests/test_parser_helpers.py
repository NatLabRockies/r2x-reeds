"""Tests for parser helper functions."""

from __future__ import annotations

import polars as pl
import pytest

pytestmark = [pytest.mark.unit]


def test_filter_generators_by_transmission_region_returns_matching(sample_region):
    from r2x_reeds.models import ReEDSVariableGenerator
    from r2x_reeds.parser_utils import filter_generators_by_transmission_region

    gen = ReEDSVariableGenerator(name="upv_p1", region=sample_region, technology="upv", capacity=100.0)

    result = filter_generators_by_transmission_region(
        [gen],
        region_name=sample_region.transmission_region,
    )

    assert len(result) == 1
    assert result[0] is gen


def test_filter_generators_by_transmission_region_excludes_non_matching(sample_region):
    from r2x_reeds.models import ReEDSVariableGenerator
    from r2x_reeds.parser_utils import filter_generators_by_transmission_region

    gen = ReEDSVariableGenerator(name="upv_p1", region=sample_region, technology="upv", capacity=100.0)

    result = filter_generators_by_transmission_region(
        [gen],
        region_name="NONEXISTENT_REGION",
    )

    assert len(result) == 0


def test_filter_generators_by_transmission_region_with_category_filter(sample_region):
    from r2x_reeds.models import ReEDSThermalGenerator, ReEDSVariableGenerator
    from r2x_reeds.parser_utils import filter_generators_by_transmission_region

    solar_gen = ReEDSVariableGenerator(name="upv_p1", region=sample_region, technology="upv", capacity=100.0)
    thermal_gen = ReEDSThermalGenerator(
        name="gas_p1",
        region=sample_region,
        technology="gas-cc",
        capacity=200.0,
        heat_rate=7.5,
        fuel_type="gas",
        fuel_price=4.0,
    )

    tech_categories = {"solar": {"prefixes": ["upv"], "exact": []}}

    result = filter_generators_by_transmission_region(
        [solar_gen, thermal_gen],
        region_name=sample_region.transmission_region,
        category_filter="solar",
        tech_categories=tech_categories,
    )

    assert len(result) == 1
    assert result[0] is solar_gen


def test_filter_generators_by_transmission_region_skips_generators_without_region(sample_region):
    from r2x_reeds.models import ReEDSVariableGenerator
    from r2x_reeds.parser_utils import filter_generators_by_transmission_region

    region_p2 = sample_region.model_copy(update={"name": "p2", "transmission_region": "OTHER"})

    gen_with_matching_region = ReEDSVariableGenerator(
        name="upv_p1", region=sample_region, technology="upv", capacity=100.0
    )
    gen_with_non_matching_region = ReEDSVariableGenerator(
        name="upv_p2", region=region_p2, technology="upv", capacity=100.0
    )

    result = filter_generators_by_transmission_region(
        [gen_with_matching_region, gen_with_non_matching_region],
        region_name=sample_region.transmission_region,
    )

    assert len(result) == 1
    assert result[0] is gen_with_matching_region


def test_filter_loads_by_transmission_region_returns_matching(sample_region):
    from r2x_reeds.models import ReEDSDemand
    from r2x_reeds.parser_utils import filter_loads_by_transmission_region

    load = ReEDSDemand(name="load_p1", region=sample_region, max_active_power=1000.0)

    result = filter_loads_by_transmission_region(
        [load],
        region_name=sample_region.transmission_region,
    )

    assert len(result) == 1
    assert result[0] is load


def test_filter_loads_by_transmission_region_excludes_non_matching(sample_region):
    from r2x_reeds.models import ReEDSDemand
    from r2x_reeds.parser_utils import filter_loads_by_transmission_region

    load = ReEDSDemand(name="load_p1", region=sample_region, max_active_power=1000.0)

    result = filter_loads_by_transmission_region(
        [load],
        region_name="NONEXISTENT_REGION",
    )

    assert len(result) == 0


def test_filter_loads_by_transmission_region_skips_loads_without_region(sample_region):
    from r2x_reeds.models import ReEDSDemand
    from r2x_reeds.parser_utils import filter_loads_by_transmission_region

    region_p2 = sample_region.model_copy(update={"name": "p2", "transmission_region": "OTHER"})

    load_with_matching_region = ReEDSDemand(name="load_p1", region=sample_region, max_active_power=1000.0)
    load_with_non_matching_region = ReEDSDemand(name="load_p2", region=region_p2, max_active_power=500.0)

    result = filter_loads_by_transmission_region(
        [load_with_matching_region, load_with_non_matching_region],
        region_name=sample_region.transmission_region,
    )

    assert len(result) == 1
    assert result[0] is load_with_matching_region


def test_filter_generators_by_category_returns_matching(sample_region):
    from r2x_reeds.models import ReEDSVariableGenerator
    from r2x_reeds.parser_utils import filter_generators_by_category

    gen = ReEDSVariableGenerator(name="upv_p1", region=sample_region, technology="upv", capacity=100.0)

    tech_categories = {"solar": {"prefixes": ["upv"], "exact": []}}

    result = filter_generators_by_category(
        [gen],
        category="solar",
        tech_categories=tech_categories,
    )

    assert len(result) == 1
    assert result[0] is gen


def test_filter_generators_by_category_excludes_non_matching(sample_region):
    from r2x_reeds.models import ReEDSVariableGenerator
    from r2x_reeds.parser_utils import filter_generators_by_category

    gen = ReEDSVariableGenerator(name="upv_p1", region=sample_region, technology="upv", capacity=100.0)

    tech_categories = {"wind": {"prefixes": ["wind"], "exact": []}}

    result = filter_generators_by_category(
        [gen],
        category="wind",
        tech_categories=tech_categories,
    )

    assert len(result) == 0


def test_filter_generators_by_category_handles_empty_list():
    from r2x_reeds.parser_utils import filter_generators_by_category

    tech_categories = {"solar": {"prefixes": ["upv"], "exact": []}}

    result = filter_generators_by_category(
        [],
        category="solar",
        tech_categories=tech_categories,
    )

    assert result == []


def test_build_generator_emission_lookup_creates_correct_keys(sample_region):
    from r2x_reeds.models import ReEDSThermalGenerator
    from r2x_reeds.parser_utils import build_generator_emission_lookup

    gen = ReEDSThermalGenerator(
        name="gas_p1_2020",
        region=sample_region,
        technology="gas-cc",
        capacity=200.0,
        heat_rate=7.5,
        fuel_type="gas",
        fuel_price=4.0,
        vintage="2020",
    )

    lookup = build_generator_emission_lookup([gen])

    expected_key = ("gas-cc", sample_region.name, "2020")
    assert expected_key in lookup
    assert lookup[expected_key] == ["gas_p1_2020"]


def test_build_generator_emission_lookup_uses_sentinel_for_missing_vintage(sample_region):
    from r2x_reeds.models import ReEDSVariableGenerator
    from r2x_reeds.parser_utils import build_generator_emission_lookup

    gen = ReEDSVariableGenerator(name="upv_p1", region=sample_region, technology="upv", capacity=100.0)

    lookup = build_generator_emission_lookup([gen])

    expected_key = ("upv", sample_region.name, "__missing_vintage__")
    assert expected_key in lookup


def test_build_generator_emission_lookup_groups_generators_with_same_key(sample_region):
    from r2x_reeds.models import ReEDSThermalGenerator
    from r2x_reeds.parser_utils import build_generator_emission_lookup

    gen1 = ReEDSThermalGenerator(
        name="gas_p1_2020_a",
        region=sample_region,
        technology="gas-cc",
        capacity=200.0,
        heat_rate=7.5,
        fuel_type="gas",
        fuel_price=4.0,
        vintage="2020",
    )
    gen2 = ReEDSThermalGenerator(
        name="gas_p1_2020_b",
        region=sample_region,
        technology="gas-cc",
        capacity=300.0,
        heat_rate=7.2,
        fuel_type="gas",
        fuel_price=4.0,
        vintage="2020",
    )

    lookup = build_generator_emission_lookup([gen1, gen2])

    key = ("gas-cc", sample_region.name, "2020")
    assert len(lookup[key]) == 2
    assert "gas_p1_2020_a" in lookup[key]
    assert "gas_p1_2020_b" in lookup[key]


def test_build_generator_emission_lookup_handles_empty_list():
    from r2x_reeds.parser_utils import build_generator_emission_lookup

    lookup = build_generator_emission_lookup([])

    assert lookup == {}


def test_match_emission_rows_to_generators_returns_matched_rows():
    from r2x_reeds.parser_utils import match_emission_rows_to_generators

    emit_df = pl.DataFrame(
        {
            "technology": ["gas-cc", "coal"],
            "region": ["p1", "p2"],
            "vintage": ["2020", "2015"],
            "rate": [0.5, 0.8],
        }
    )

    lookup = {
        ("gas-cc", "p1", "2020"): ["gas_p1_2020"],
    }

    result = match_emission_rows_to_generators(emit_df, generator_lookup=lookup)

    assert result.height == 1
    assert "name" in result.columns
    assert result["name"][0] == "gas_p1_2020"


def test_match_emission_rows_to_generators_handles_null_vintage():
    from r2x_reeds.parser_utils import match_emission_rows_to_generators

    emit_df = pl.DataFrame(
        {
            "technology": ["upv"],
            "region": ["p1"],
            "vintage": [None],
            "rate": [0.0],
        }
    )

    lookup = {
        ("upv", "p1", "__missing_vintage__"): ["upv_p1"],
    }

    result = match_emission_rows_to_generators(emit_df, generator_lookup=lookup)

    assert result.height == 1
    assert result["name"][0] == "upv_p1"


def test_match_emission_rows_to_generators_returns_empty_when_no_matches():
    from r2x_reeds.parser_utils import match_emission_rows_to_generators

    emit_df = pl.DataFrame(
        {
            "technology": ["nuclear"],
            "region": ["p3"],
            "vintage": ["2010"],
            "rate": [0.0],
        }
    )

    lookup = {}

    result = match_emission_rows_to_generators(emit_df, generator_lookup=lookup)

    assert result.height == 0


def test_match_emission_rows_to_generators_preserves_original_columns():
    from r2x_reeds.parser_utils import match_emission_rows_to_generators

    emit_df = pl.DataFrame(
        {
            "technology": ["gas-cc"],
            "region": ["p1"],
            "vintage": ["2020"],
            "rate": [0.5],
            "extra_col": ["value"],
        }
    )

    lookup = {("gas-cc", "p1", "2020"): ["gas_p1_2020"]}

    result = match_emission_rows_to_generators(emit_df, generator_lookup=lookup)

    assert "rate" in result.columns
    assert "extra_col" in result.columns
    assert result["extra_col"][0] == "value"


def test_build_year_month_calendar_df_returns_expected_columns():
    from r2x_reeds.parser_utils import build_year_month_calendar_df

    result = build_year_month_calendar_df([2024])

    assert "year" in result.columns
    assert "month_num" in result.columns
    assert "days_in_month" in result.columns
    assert "hours_in_month" in result.columns


def test_build_year_month_calendar_df_returns_12_rows_per_year():
    from r2x_reeds.parser_utils import build_year_month_calendar_df

    result = build_year_month_calendar_df([2024, 2025])

    assert result.height == 24


def test_build_year_month_calendar_df_leap_year_february():
    from r2x_reeds.parser_utils import build_year_month_calendar_df

    result = build_year_month_calendar_df([2024])

    feb_row = result.filter(pl.col("month_num") == 2)
    assert feb_row["days_in_month"][0] == 29
    assert feb_row["hours_in_month"][0] == 29 * 24


def test_build_year_month_calendar_df_non_leap_year_february():
    from r2x_reeds.parser_utils import build_year_month_calendar_df

    result = build_year_month_calendar_df([2023])

    feb_row = result.filter(pl.col("month_num") == 2)
    assert feb_row["days_in_month"][0] == 28
    assert feb_row["hours_in_month"][0] == 28 * 24


def test_build_year_month_calendar_df_handles_empty_year_list():
    from r2x_reeds.parser_utils import build_year_month_calendar_df

    result = build_year_month_calendar_df([])

    assert result.height == 0


def test_calculate_hydro_budgets_for_generator_returns_budget_results(sample_region):
    from r2x_reeds.models import ReEDSHydroGenerator
    from r2x_reeds.parser_types import HydroBudgetResult
    from r2x_reeds.parser_utils import calculate_hydro_budgets_for_generator

    gen = ReEDSHydroGenerator(
        name="hyd_p1",
        region=sample_region,
        technology="hyd",
        capacity=200.0,
        vintage="2020",
        is_dispatchable=True,
    )

    hydro_data = pl.DataFrame(
        {
            "technology": ["hyd"] * 12,
            "region": [sample_region.name] * 12,
            "vintage": ["2020"] * 12,
            "year": [2024] * 12,
            "month_num": list(range(1, 13)),
            "hydro_cf": [0.5] * 12,
            "days_in_month": [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31],
            "hours_in_month": [d * 24 for d in [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]],
        }
    )

    results = calculate_hydro_budgets_for_generator(
        gen,
        hydro_data=hydro_data,
        solve_years=[2024],
    )

    assert len(results) == 1
    assert isinstance(results[0], HydroBudgetResult)
    assert results[0].year == 2024
    assert len(results[0].budget_array) == 366 * 24


def test_calculate_hydro_budgets_for_generator_skips_incomplete_months(sample_region):
    from r2x_reeds.models import ReEDSHydroGenerator
    from r2x_reeds.parser_utils import calculate_hydro_budgets_for_generator

    gen = ReEDSHydroGenerator(
        name="hyd_p1",
        region=sample_region,
        technology="hyd",
        capacity=200.0,
        vintage="2020",
        is_dispatchable=True,
    )

    hydro_data = pl.DataFrame(
        {
            "technology": ["hyd"] * 6,
            "region": [sample_region.name] * 6,
            "vintage": ["2020"] * 6,
            "year": [2024] * 6,
            "month_num": list(range(1, 7)),
            "hydro_cf": [0.5] * 6,
            "days_in_month": [31, 29, 31, 30, 31, 30],
            "hours_in_month": [d * 24 for d in [31, 29, 31, 30, 31, 30]],
        }
    )

    results = calculate_hydro_budgets_for_generator(
        gen,
        hydro_data=hydro_data,
        solve_years=[2024],
    )

    assert len(results) == 0


def test_calculate_hydro_budgets_for_generator_returns_empty_when_no_match(sample_region):
    from r2x_reeds.models import ReEDSHydroGenerator
    from r2x_reeds.parser_utils import calculate_hydro_budgets_for_generator

    gen = ReEDSHydroGenerator(
        name="hyd_p1",
        region=sample_region,
        technology="hyd",
        capacity=200.0,
        vintage="2020",
        is_dispatchable=True,
    )

    hydro_data = pl.DataFrame(
        {
            "technology": ["other"] * 12,
            "region": [sample_region.name] * 12,
            "vintage": ["2020"] * 12,
            "year": [2024] * 12,
            "month_num": list(range(1, 13)),
            "hydro_cf": [0.5] * 12,
            "days_in_month": [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31],
            "hours_in_month": [d * 24 for d in [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]],
        }
    )

    results = calculate_hydro_budgets_for_generator(
        gen,
        hydro_data=hydro_data,
        solve_years=[2024],
    )

    assert len(results) == 0


def test_calculate_hydro_budgets_for_generator_uses_capacity_and_cf(sample_region):
    from r2x_reeds.models import ReEDSHydroGenerator
    from r2x_reeds.parser_utils import calculate_hydro_budgets_for_generator

    gen = ReEDSHydroGenerator(
        name="hyd_p1",
        region=sample_region,
        technology="hyd",
        capacity=100.0,
        vintage="2020",
        is_dispatchable=True,
    )

    hydro_data = pl.DataFrame(
        {
            "technology": ["hyd"] * 12,
            "region": [sample_region.name] * 12,
            "vintage": ["2020"] * 12,
            "year": [2023] * 12,
            "month_num": list(range(1, 13)),
            "hydro_cf": [1.0] * 12,
            "days_in_month": [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31],
            "hours_in_month": [d * 24 for d in [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]],
        }
    )

    results = calculate_hydro_budgets_for_generator(
        gen,
        hydro_data=hydro_data,
        solve_years=[2023],
    )

    jan_daily_budget = 100.0 * 1.0 * (31 * 24) / 31
    assert results[0].budget_array[0] == pytest.approx(jan_daily_budget)
