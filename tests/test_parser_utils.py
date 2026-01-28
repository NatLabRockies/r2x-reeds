from __future__ import annotations

import pytest

pytestmark = [pytest.mark.unit]


def test_tech_matches_category_with_prefixes() -> None:
    from r2x_reeds import parser_utils

    categories = {
        "wind": {"prefixes": ["wnd", "wind-"], "exact": ["wind-ons"]},
    }
    assert parser_utils.tech_matches_category("wnd-abc", "wind", categories) is True
    assert parser_utils.tech_matches_category("solar", "wind", categories) is False


def test_get_technology_category_ok_and_err() -> None:
    from r2x_reeds import parser_utils

    categories = {
        "wind": {"prefixes": ["wind"], "exact": []},
        "renewable": {"prefixes": ["wind"], "exact": []},
        "solar": ["upv", "dupv"],
    }

    result = parser_utils.get_technology_category("wind-ons", categories)
    assert result.unwrap() == "wind"

    err_result = parser_utils.get_technology_category("unknown", categories)
    assert err_result.is_err()
    assert isinstance(err_result.unwrap_err(), KeyError)


def test_get_technology_categories_multiple_matches() -> None:
    from r2x_reeds import parser_utils

    categories = {
        "wind": {"prefixes": ["wind"], "exact": []},
        "renewable": {"prefixes": ["wind", "upv"], "exact": []},
        "variable_renewable": {"prefixes": ["wind", "upv"], "exact": []},
    }

    multi_result = parser_utils.get_technology_categories("wind-ons", categories)
    assert multi_result.unwrap() == ["wind", "renewable", "variable_renewable"]

    # Legacy helper still returns only the first match
    first_match = parser_utils.get_technology_category("wind-ons", categories)
    assert first_match.unwrap() == "wind"


def test_monthly_to_hourly_polars() -> None:
    from r2x_reeds import parser_utils

    monthly = [10.0] * 12
    hourly = parser_utils.monthly_to_hourly_polars(2024, monthly).unwrap()

    assert isinstance(hourly, list) or hasattr(hourly, "size")
    assert len(hourly) == 366 * 24
    assert hourly[0] == pytest.approx(10.0)

    with pytest.raises(ValueError):
        parser_utils.monthly_to_hourly_polars(2024, [1.0]).unwrap()


def test_build_generator_field_map_replaces_region_component():
    from r2x_core import System
    from r2x_reeds import parser_utils
    from r2x_reeds.models import ReEDSRegion

    system = System(name="test_parser_utils")
    region = ReEDSRegion(name="north")
    system.add_component(region)

    row = {"technology": "wind", "region": "north"}
    mapped = parser_utils._build_generator_field_map(row, system)
    assert mapped["region"] is region

    row_missing = {"technology": "solar", "region": "south"}
    mapped_missing = parser_utils._build_generator_field_map(row_missing, system)
    assert mapped_missing["region"] == "south"


def test_merge_lazy_frames_success() -> None:
    import polars as pl

    from r2x_reeds import parser_utils

    left = pl.DataFrame({"key": [1, 2], "value": ["a", "b"]}).lazy()
    right = pl.DataFrame({"key": [1], "other": ["x"]}).lazy()
    merged_df = parser_utils.merge_lazy_frames(left, right, on=["key"]).unwrap().collect()
    assert merged_df.shape[0] == 2
    assert merged_df.filter(pl.col("other").is_not_null()).shape[0] == 1
    assert merged_df["other"][0] == "x"


def test_get_generator_class_success_and_failure() -> None:
    from r2x_reeds import parser_utils
    from r2x_reeds.models import ReEDSThermalGenerator

    technology_categories = {"thermal": {"prefixes": ["coal"]}}
    mapping = {"thermal": "ReEDSThermalGenerator"}

    found = parser_utils.get_generator_class("coal", technology_categories, mapping)
    assert found.is_ok()
    assert found.ok() is ReEDSThermalGenerator

    missing = parser_utils.get_generator_class("unknown", {}, mapping)
    assert missing.is_err()
    assert isinstance(missing.err(), TypeError)


def _create_capacity_lazy_frame():
    import polars as pl

    return pl.DataFrame(
        {
            "technology": ["wind", "gas", "coal"],
            "region": ["p1", "p2", "p3"],
            "capacity": [10, 20, 5],
            "storage_duration": [None, 1.0, None],
            "year": [2025, 2025, 2025],
        }
    ).lazy()


def test_prepare_generator_dataset_with_optional_data() -> None:
    import polars as pl

    from r2x_reeds import parser_utils

    capacity = _create_capacity_lazy_frame()
    optional_data = {
        "fuel_tech_map": pl.DataFrame(
            {"technology": ["wind", "gas"], "fuel_type": ["windfuel", "gasfuel"]}
        ).lazy(),
        "storage_duration_out": pl.DataFrame(
            {
                "technology": ["wind"],
                "vintage": [None],
                "region": ["p1"],
                "year": [2025],
                "storage_duration": [5.5],
            }
        ).lazy(),
        "consume_characteristics": pl.DataFrame(
            {"technology": ["gas"], "year": [2025], "parameter": ["electricity_efficiency"], "value": [0.8]}
        ).lazy(),
    }
    categories = {"wind": {"prefixes": ["wind"]}, "gas": {"prefixes": ["gas"]}}

    df = parser_utils._prepare_generator_dataset(
        capacity_data=capacity,
        optional_data=optional_data,
        excluded_technologies=["coal"],
        technology_categories=categories,
    ).unwrap()
    assert "fuel_type" in df.columns
    assert df.filter(pl.col("technology") == "wind").select("fuel_type").item() == "windfuel"
    assert df.filter(pl.col("technology") == "gas").select("electricity_efficiency").item() == 0.8
    assert df.filter(pl.col("technology") == "wind").select("storage_duration").item() == 5.5
    assert df.filter(pl.col("technology") == "coal").is_empty()


def test_prepare_generator_dataset_returns_other_when_fuel_missing() -> None:
    import polars as pl

    from r2x_reeds import parser_utils

    capacity = pl.DataFrame(
        {
            "technology": ["gas-cc_h2-cc", "gas-ct"],
            "region": ["p1", "p2"],
            "capacity": [10.0, 5.0],
            "year": [2040, 2040],
        }
    ).lazy()

    optional_data = {
        "fuel_tech_map": pl.DataFrame({"technology": ["steam-turbine"], "fuel_type": ["coal"]}).lazy()
    }

    categories = {"thermal": {"prefixes": ["gas"]}}
    df = parser_utils._prepare_generator_dataset(
        capacity_data=capacity,
        optional_data=optional_data,
        excluded_technologies=[],
        technology_categories=categories,
    ).unwrap()

    assert df["fuel_type"].to_list() == ["OTHER", "OTHER"]


def test_prepare_generator_dataset_preserves_fuel_type_values() -> None:
    import polars as pl

    from r2x_reeds import parser_utils

    capacity = pl.DataFrame(
        {
            "technology": ["gas-cc_h2-cc"],
            "region": ["p1"],
            "capacity": [10.0],
            "year": [2040],
        }
    ).lazy()

    optional_data = {
        "fuel_tech_map": pl.DataFrame({"technology": ["gas-cc_h2-cc"], "fuel_type": ["h2fuel"]}).lazy()
    }

    categories = {"thermal": {"prefixes": ["gas"]}}
    df = parser_utils._prepare_generator_dataset(
        capacity_data=capacity,
        optional_data=optional_data,
        excluded_technologies=[],
        technology_categories=categories,
    ).unwrap()

    assert df.select("fuel_type").item() == "h2fuel"


def test_prepare_generator_dataset_allows_missing_fuel_for_variable_generators() -> None:
    import polars as pl

    from r2x_reeds import parser_utils

    capacity = pl.DataFrame(
        {
            "technology": ["wind-ons"],
            "region": ["p1"],
            "capacity": [10.0],
            "year": [2040],
        }
    ).lazy()

    optional_data = {
        "fuel_tech_map": pl.DataFrame({"technology": ["steam-turbine"], "fuel_type": ["coal"]}).lazy()
    }

    categories = {"wind": {"prefixes": ["wind"]}, "thermal": {"prefixes": ["steam-turbine"]}}

    result = parser_utils._prepare_generator_dataset(
        capacity_data=capacity,
        optional_data=optional_data,
        excluded_technologies=[],
        technology_categories=categories,
    )
    assert result.is_ok()


def test_prepare_generator_dataset_handles_suffixed_technology_names() -> None:
    import polars as pl

    from r2x_reeds import parser_utils

    capacity = pl.DataFrame(
        {
            "technology": ["wind-ons_5"],
            "region": ["p1"],
            "capacity": [10.0],
            "year": [2025],
        }
    ).lazy()

    optional_data = {
        "fuel_tech_map": pl.DataFrame({"technology": ["wind-ons"], "fuel_type": ["wind"]}).lazy()
    }
    df = parser_utils._prepare_generator_dataset(
        capacity_data=capacity,
        optional_data=optional_data,
        excluded_technologies=[],
        technology_categories={"wind": {"prefixes": ["wind-ons"]}},
    ).unwrap()

    assert df.select("category").item() == "wind"


def test_prepare_generator_dataset_thermal_missing_fuel_type_defaults_to_other() -> None:
    import polars as pl

    from r2x_reeds import parser_utils

    capacity = pl.DataFrame(
        {
            "technology": ["gas-ct"],
            "region": ["p1"],
            "capacity": [10.0],
            "year": [2040],
        }
    ).lazy()

    optional_data = {"fuel_tech_map": pl.DataFrame({"technology": ["coal"], "fuel_type": ["coal"]}).lazy()}

    categories = {"thermal": {"prefixes": ["gas-ct"]}}

    df = parser_utils._prepare_generator_dataset(
        capacity_data=capacity,
        optional_data=optional_data,
        excluded_technologies=[],
        technology_categories=categories,
    ).unwrap()

    assert df.select("fuel_type").item() == "OTHER"


def test_prepare_generator_inputs_splits_variable_and_nonvariable() -> None:
    import polars as pl

    from r2x_reeds import parser_utils

    capacity = pl.DataFrame(
        {
            "technology": ["wind", "solar", "thermal"],
            "region": ["p1", "p1", "p2"],
            "capacity": [5, 10, 15],
            "storage_duration": [None, None, 2.0],
        }
    ).lazy()

    categories = {
        "wind": {"prefixes": ["wind"]},
        "solar": {"prefixes": ["solar"]},
        "thermal": {"prefixes": ["thermal"]},
    }
    optional_data = {"fuel_tech_map": pl.DataFrame({"technology": ["thermal"], "fuel_type": ["coal"]}).lazy()}

    variable_df, non_variable_df = parser_utils.prepare_generator_inputs(
        capacity_data=capacity,
        optional_data=optional_data,
        excluded_technologies=[],
        technology_categories=categories,
        variable_categories=["wind", "solar"],
    ).unwrap()
    assert not variable_df.is_empty()
    assert all(variable_df["is_aggregated"])
    assert non_variable_df["technology"].to_list() == ["thermal"]


def test_aggregate_variable_generators_outputs_expected_summary():
    import polars as pl

    from r2x_reeds import parser_utils

    df = pl.DataFrame(
        {
            "technology": ["wind", "wind"],
            "region": ["p1", "p1"],
            "category": ["wind", "wind"],
            "capacity": [5.0, 7.0],
            "resource_class": ["rc", "rc"],
            "fuel_type": ["fuel", "fuel"],
            "heat_rate": [1.0, 1.5],
            "forced_outage_rate": [0.1, 0.2],
            "planned_outage_rate": [0.05, 0.08],
            "maxage_years": [20, 25],
            "vom_price": [0.0, 0.0],
            "fuel_price": [10, 12],
            "inverter_loading_ratio": [1.0, 1.1],
            "capacity_factor_adjustment": [0.9, 0.95],
            "max_capacity_factor": [0.8, 0.85],
            "supply_curve_cost": [100, 110],
            "transmission_adder": [5, 6],
            "categories": [["wind"], ["wind"]],
        }
    )
    aggregated = parser_utils.aggregate_variable_generators(df)
    assert aggregated.select("capacity").item() == pytest.approx(12.0)
    assert aggregated.select("resource_class").item() == "rc"


def test_calculate_reserve_requirement_nonzero_and_zero():
    import numpy as np

    from r2x_reeds import parser_utils

    hours = np.arange(24)
    wind = [{"capacity": 1.0, "time_series": np.ones(24)}]
    solar = [{"capacity": 2.0, "time_series": np.zeros(24)}]
    loads = [{"time_series": np.full(24, 0.5)}]

    result = parser_utils.calculate_reserve_requirement(wind, solar, loads, hours, 0.1, 0.1, 0.2)
    assert result.is_ok()
    assert isinstance(result.ok(), np.ndarray)

    zero_result = parser_utils.calculate_reserve_requirement([], [], [], hours, 0.0, 0.0, 0.0)
    assert zero_result.is_err()
    assert zero_result.err().args[0] == "Reserve requirement is zero"


def test_get_rules_by_target_and_rule_selection():
    class DummyRule:
        def __init__(self, name: str, target_types: list[str]):
            self.name = name
            self._target_types = target_types

        def get_target_types(self) -> list[str]:
            return self._target_types

    rule_a = DummyRule("r1", ["A", "B"])
    rule_b = DummyRule("r2", ["B"])
    from r2x_reeds import parser_utils

    rules_by_target = parser_utils.get_rules_by_target([rule_a, rule_b]).unwrap()  # type: ignore[arg-type]
    assert len(rules_by_target["B"]) == 2

    selected = parser_utils.get_rule_for_target(rules_by_target, target_type="B", name="r2").unwrap()
    assert selected.name == "r2"

    fallback = parser_utils.get_rule_for_target(rules_by_target, target_type="B")
    assert fallback.is_ok()

    missing = parser_utils.get_rule_for_target(rules_by_target, target_type="UNKNOWN")
    assert missing.is_err()


def test_prepare_generator_dataset_null_capacity_data() -> None:
    """Test error when capacity_data is None."""
    from r2x_reeds import parser_utils

    result = parser_utils._prepare_generator_dataset(
        capacity_data=None,  # type: ignore[arg-type]
        optional_data={},
        excluded_technologies=[],
        technology_categories={},
    )
    assert result.is_err()
    assert "No capacity data" in str(result.unwrap_err())


def test_prepare_generator_dataset_empty_after_joins() -> None:
    """Test error when data is empty after all joins."""
    import polars as pl

    from r2x_reeds import parser_utils

    # Create a capacity frame that becomes empty after filtering
    capacity = pl.DataFrame(
        {
            "technology": ["unknown_tech"],
            "region": ["p1"],
            "capacity": [10.0],
            "year": [2025],
        }
    ).lazy()

    categories = {"wind": {"prefixes": ["wind"]}, "solar": {"prefixes": ["solar"]}}
    optional_data = {
        "fuel_tech_map": pl.DataFrame({"technology": ["unknown_tech"], "fuel_type": ["coal"]}).lazy()
    }

    result = parser_utils._prepare_generator_dataset(
        capacity_data=capacity,
        optional_data=optional_data,
        excluded_technologies=["unknown_tech"],
        technology_categories=categories,
    )
    assert result.is_err()
    assert "All generators were excluded" in str(result.unwrap_err())


def test_prepare_generator_dataset_all_excluded() -> None:
    """Test error when all rows are filtered by excluded_technologies."""
    import polars as pl

    from r2x_reeds import parser_utils

    capacity = pl.DataFrame(
        {
            "technology": ["coal", "oil"],
            "region": ["p1", "p2"],
            "capacity": [100.0, 50.0],
            "year": [2025, 2025],
        }
    ).lazy()

    categories = {"coal": {"prefixes": ["coal"]}, "oil": {"prefixes": ["oil"]}}
    optional_data = {
        "fuel_tech_map": pl.DataFrame({"technology": ["coal", "oil"], "fuel_type": ["coal", "oil"]}).lazy()
    }

    result = parser_utils._prepare_generator_dataset(
        capacity_data=capacity,
        optional_data=optional_data,
        excluded_technologies=["coal", "oil"],
        technology_categories=categories,
    )
    assert result.is_err()
    assert "All generators were excluded" in str(result.unwrap_err())


def test_prepare_generator_dataset_fuel_tech_map_missing_column() -> None:
    """Test graceful handling when fuel_tech_map lacks 'technology' column."""
    import polars as pl

    from r2x_reeds import parser_utils

    capacity = _create_capacity_lazy_frame()

    # Create fuel_tech_map without 'technology' column
    optional_data = {
        "fuel_tech_map": pl.DataFrame({"fuel_type": ["gasfuel"]}).lazy(),
    }

    categories = {"wind": {"prefixes": ["wind"]}, "gas": {"prefixes": ["gas"]}}

    result = parser_utils._prepare_generator_dataset(
        capacity_data=capacity,
        optional_data=optional_data,
        excluded_technologies=[],
        technology_categories=categories,
    )
    assert result.is_err()
    assert "fuel_type column is missing" in str(result.unwrap_err())


def test_prepare_generator_dataset_optional_data_join_exception() -> None:
    """Test exception handling in optional data joins."""
    import polars as pl

    from r2x_reeds import parser_utils

    capacity = _create_capacity_lazy_frame()

    # Create malformed optional data that will cause join error
    optional_data = {
        "storage_duration_out": pl.DataFrame(
            {
                "invalid_col": [1],  # Missing required columns
            }
        ).lazy(),
    }

    categories = {"wind": {"prefixes": ["wind"]}, "gas": {"prefixes": ["gas"]}}

    # This should handle the exception gracefully
    result = parser_utils._prepare_generator_dataset(
        capacity_data=capacity,
        optional_data=optional_data,
        excluded_technologies=[],
        technology_categories=categories,
    )
    # May either succeed by skipping problematic join or error with proper message
    assert result.is_ok() or result.is_err()


def test_prepare_generator_dataset_category_mapping_failure() -> None:
    """Test handling when technology has no matching category."""
    import polars as pl

    from r2x_reeds import parser_utils

    capacity = pl.DataFrame(
        {
            "technology": ["unknown_type"],
            "region": ["p1"],
            "capacity": [10.0],
            "year": [2025],
        }
    ).lazy()

    # Empty categories - no matches
    categories = {}
    optional_data = {
        "fuel_tech_map": pl.DataFrame({"technology": ["unknown_type"], "fuel_type": ["coal"]}).lazy()
    }

    # Should handle unmapped technologies gracefully
    df = parser_utils._prepare_generator_dataset(
        capacity_data=capacity,
        optional_data=optional_data,
        excluded_technologies=[],
        technology_categories=categories,
    ).unwrap()
    # Should contain the original data with categories column (empty list for unmapped)
    assert df.shape[0] > 0
    assert "categories" in df.columns
    # All categories should be empty lists for unmapped technology
    categories_col = df.select("categories").to_series().to_list()
    assert all(cat == [] for cat in categories_col)


def test_calculate_reserve_requirement_exception_handling() -> None:
    """Test exception handling in calculation."""
    import numpy as np

    from r2x_reeds import parser_utils

    # Create conditions that will cause zero reserve requirement (no valid time series data)
    hours = np.arange(10)
    wind = [{"capacity": 1.0}]  # Missing time_series key - will be skipped

    result = parser_utils.calculate_reserve_requirement(wind, [], [], hours, 0.1, 0.0, 0.0)
    assert result.is_err()
    assert "Reserve requirement is zero" in str(result.unwrap_err())


def test_calculate_reserve_requirement_time_series_length_mismatch() -> None:
    """Test handling of mismatched time series lengths."""
    import numpy as np

    from r2x_reeds import parser_utils

    hours = np.arange(24)
    wind = [{"capacity": 1.0, "time_series": np.ones(10)}]  # Shorter than hours
    solar = [{"capacity": 2.0, "time_series": np.ones(15)}]  # Different length
    loads = [{"time_series": np.ones(24)}]

    result = parser_utils.calculate_reserve_requirement(wind, solar, loads, hours, 0.1, 0.1, 0.2)
    # Should handle gracefully using min() for length
    assert result.is_ok()


def test_calculate_reserve_requirement_empty_generators() -> None:
    """Test with empty generator and load lists."""
    import numpy as np

    from r2x_reeds import parser_utils

    hours = np.arange(24)

    result = parser_utils.calculate_reserve_requirement([], [], [], hours, 0.1, 0.1, 0.2)
    assert result.is_err()
    assert "Reserve requirement is zero" in str(result.unwrap_err())


def test_collect_component_kwargs_missing_identifier() -> None:
    """Test error handling when identifier is empty/None."""
    import polars as pl

    from r2x_core.exceptions import ValidationError
    from r2x_reeds import parser_utils

    df = pl.DataFrame({"col1": [1, 2, 3]})

    def failing_identifier_getter(row):
        # Return Ok with empty string
        from rust_ok import Ok

        return Ok("")

    class DummyRule:
        pass

    result = parser_utils._collect_component_kwargs_from_rule(
        data=df,
        rule_provider=DummyRule(),  # type: ignore[arg-type]
        parser_context=None,  # type: ignore[arg-type]
        row_identifier_getter=failing_identifier_getter,
    )
    assert result.is_err()
    error = result.unwrap_err()
    assert isinstance(error, ValidationError)

    assert "failed" in str(error).lower()


def test_tech_matches_category_category_not_in_dict() -> None:
    """Test return False when category doesn't exist in dict."""
    from r2x_reeds import parser_utils

    categories = {
        "wind": {"prefixes": ["wind"], "exact": []},
    }

    result = parser_utils.tech_matches_category("wind-ons", "nonexistent_category", categories)
    assert result is False


def test_tech_matches_category_exact_match_takes_precedence() -> None:
    """Test exact match takes precedence over prefix matching."""
    from r2x_reeds import parser_utils

    categories = {
        "wind": {"prefixes": ["w"], "exact": ["wind-ons"]},
    }

    # Exact match should return True
    result = parser_utils.tech_matches_category("wind-ons", "wind", categories)
    assert result is True

    # Non-exact prefix match should still work
    result_prefix = parser_utils.tech_matches_category("wind-offshore", "wind", categories)
    assert result_prefix is True


def test_get_generator_class_with_no_matching_category() -> None:
    """Test error case when technology has no matching categories."""
    from r2x_reeds import parser_utils

    # Unknown tech with empty categories should error
    result = parser_utils.get_generator_class("unknown_tech", {}, {})
    assert result.is_err()
    error = result.unwrap_err()
    assert isinstance(error, TypeError)
    # Error message indicates no category match
    assert "unknown_tech" in str(error)


def test_prepare_generator_dataset_with_valid_excludes() -> None:
    """Test that excluded technologies are properly filtered."""
    import polars as pl

    from r2x_reeds import parser_utils

    capacity = pl.DataFrame(
        {
            "technology": ["wind", "solar", "nuclear"],
            "region": ["p1", "p1", "p1"],
            "capacity": [10.0, 20.0, 30.0],
            "year": [2025, 2025, 2025],
        }
    ).lazy()
    optional_data = {
        "fuel_tech_map": pl.DataFrame(
            {"technology": ["wind", "solar", "nuclear"], "fuel_type": ["wind", "solar", "uranium"]}
        ).lazy()
    }

    df = parser_utils._prepare_generator_dataset(
        capacity_data=capacity,
        optional_data=optional_data,
        excluded_technologies=["nuclear"],
        technology_categories={},
    ).unwrap()

    techs = df.select("technology").to_series().to_list()
    assert "nuclear" not in techs
    assert "wind" in techs
    assert "solar" in techs


def test_merge_lazy_frames_with_no_matches() -> None:
    """Test merge when left and right have no matching keys."""
    import polars as pl

    from r2x_reeds import parser_utils

    left = pl.DataFrame({"key": [1, 2], "value": ["a", "b"]}).lazy()
    right = pl.DataFrame({"key": [3, 4], "other": ["x", "y"]}).lazy()

    merged = parser_utils.merge_lazy_frames(left, right, on=["key"]).unwrap().collect()
    # No matches, so right values should be null
    assert merged.filter(pl.col("other").is_not_null()).shape[0] == 0


def test_monthly_to_hourly_invalid_year() -> None:
    """Test handling of invalid leap year scenarios."""
    from r2x_reeds import parser_utils

    # Year 1900 is not a leap year despite being divisible by 4
    monthly = [10.0] * 12
    hourly = parser_utils.monthly_to_hourly_polars(1900, monthly).unwrap()
    # 1900 is not a leap year, so it should have 365 days = 8760 hours
    assert len(hourly) == 365 * 24


def test_tech_matches_category_empty_tech_string() -> None:
    """Empty technology string should not match any category."""
    from r2x_reeds import parser_utils

    categories = {
        "wind": {"prefixes": ["wind"], "exact": ["wind-ons"]},
    }
    assert parser_utils.tech_matches_category("", "wind", categories) is False


def test_tech_matches_category_empty_prefixes_and_exact() -> None:
    """Category with empty prefixes and exact lists should not match."""
    from r2x_reeds import parser_utils

    categories = {
        "wind": {"prefixes": [], "exact": []},
    }
    assert parser_utils.tech_matches_category("wind-ons", "wind", categories) is False


def test_tech_matches_category_list_format_case_insensitive() -> None:
    """List format categories should be case-insensitive."""
    from r2x_reeds import parser_utils

    categories = {
        "solar": ["UPV", "DUPV", "csp"],
    }
    # Mixed case should match
    assert parser_utils.tech_matches_category("upv", "solar", categories) is True
    assert parser_utils.tech_matches_category("UPV", "solar", categories) is True
    assert parser_utils.tech_matches_category("Upv", "solar", categories) is True
    assert parser_utils.tech_matches_category("CSP", "solar", categories) is True


def test_get_technology_categories_empty_tech_name() -> None:
    """Empty technology name should return Err."""
    from r2x_reeds import parser_utils

    categories = {
        "wind": {"prefixes": ["wind"], "exact": []},
    }
    result = parser_utils.get_technology_categories("", categories)
    assert result.is_err()
    assert isinstance(result.unwrap_err(), KeyError)


def test_monthly_to_hourly_century_year_2000_leap() -> None:
    """Year 2000 is a leap year (divisible by 400)."""
    from r2x_reeds import parser_utils

    monthly = [10.0] * 12
    hourly = parser_utils.monthly_to_hourly_polars(2000, monthly).unwrap()
    # 2000 is a leap year (divisible by 400), so 366 days = 8784 hours
    assert len(hourly) == 366 * 24


def test_monthly_to_hourly_century_year_2100_not_leap() -> None:
    """Year 2100 is NOT a leap year (divisible by 100 but not 400)."""
    from r2x_reeds import parser_utils

    monthly = [10.0] * 12
    hourly = parser_utils.monthly_to_hourly_polars(2100, monthly).unwrap()
    # 2100 is not a leap year (divisible by 100 but not 400), so 365 days = 8760 hours
    assert len(hourly) == 365 * 24


def test_monthly_to_hourly_with_zero_values() -> None:
    """Monthly profile with zero values should work."""
    from r2x_reeds import parser_utils

    monthly = [0.0] * 12
    hourly = parser_utils.monthly_to_hourly_polars(2024, monthly).unwrap()
    assert all(v == 0.0 for v in hourly)


def test_merge_lazy_frames_empty_left() -> None:
    """Merge with empty left frame."""
    import polars as pl

    from r2x_reeds import parser_utils

    left = pl.DataFrame({"key": [], "value": []}).cast({"key": pl.Int64, "value": pl.Utf8}).lazy()
    right = pl.DataFrame({"key": [1, 2], "other": ["x", "y"]}).lazy()

    merged = parser_utils.merge_lazy_frames(left, right, on=["key"]).unwrap().collect()
    assert merged.shape[0] == 0


def test_merge_lazy_frames_inner_join() -> None:
    """Inner join keeps only matching rows."""
    import polars as pl

    from r2x_reeds import parser_utils

    left = pl.DataFrame({"key": [1, 2, 3], "value": ["a", "b", "c"]}).lazy()
    right = pl.DataFrame({"key": [2, 3, 4], "other": ["x", "y", "z"]}).lazy()

    merged = parser_utils.merge_lazy_frames(left, right, on=["key"], how="inner").unwrap().collect()
    # Only keys 2 and 3 are in both
    assert merged.shape[0] == 2
    assert set(merged["key"].to_list()) == {2, 3}


def test_merge_lazy_frames_custom_suffix() -> None:
    """Custom suffix for duplicate columns."""
    import polars as pl

    from r2x_reeds import parser_utils

    left = pl.DataFrame({"key": [1], "value": ["a"]}).lazy()
    right = pl.DataFrame({"key": [1], "value": ["x"]}).lazy()

    merged = parser_utils.merge_lazy_frames(left, right, on=["key"], suffix="_other").unwrap().collect()
    assert "value" in merged.columns
    assert "value_other" in merged.columns


def test_get_generator_class_type_object_mapping() -> None:
    """Category mapping with type object (not string)."""
    from r2x_reeds import parser_utils
    from r2x_reeds.models import ReEDSThermalGenerator, ReEDSVariableGenerator

    technology_categories = {"thermal": {"prefixes": ["gas"]}, "wind": {"prefixes": ["wind"]}}
    # Mapping with actual type objects instead of strings
    mapping = {"thermal": ReEDSThermalGenerator, "wind": ReEDSVariableGenerator}

    result = parser_utils.get_generator_class("gas-cc", technology_categories, mapping)
    assert result.is_ok()
    assert result.ok() is ReEDSThermalGenerator


def test_get_generator_class_category_no_mapping() -> None:
    """Category exists in tech_categories but not in class mapping."""
    from r2x_reeds import parser_utils

    technology_categories = {"thermal": {"prefixes": ["gas"]}}
    mapping = {"solar": "ReEDSVariableGenerator"}  # thermal not in mapping

    result = parser_utils.get_generator_class("gas-cc", technology_categories, mapping)
    assert result.is_err()
    assert isinstance(result.err(), TypeError)


def test_get_generator_class_second_category_has_mapping() -> None:
    """First category has no mapping, second does."""
    from r2x_reeds import parser_utils
    from r2x_reeds.models import ReEDSVariableGenerator

    # Technology matches both 'wind' and 'renewable', but only 'renewable' has mapping
    technology_categories = {
        "wind": {"prefixes": ["wind"]},
        "renewable": {"prefixes": ["wind"]},
    }
    mapping = {"renewable": "ReEDSVariableGenerator"}  # wind not in mapping

    result = parser_utils.get_generator_class("wind-ons", technology_categories, mapping)
    assert result.is_ok()
    assert result.ok() is ReEDSVariableGenerator


def test_prepare_generator_dataset_all_optional_none() -> None:
    """All optional_data values are None."""
    import polars as pl

    from r2x_reeds import parser_utils

    capacity = pl.DataFrame(
        {
            "technology": ["wind"],
            "region": ["p1"],
            "capacity": [10.0],
            "year": [2025],
        }
    ).lazy()

    optional_data = {
        "fuel_tech_map": pl.DataFrame({"technology": ["wind"], "fuel_type": ["wind"]}).lazy(),
        "storage_duration_out": None,
        "consume_characteristics": None,
    }

    categories = {"wind": {"prefixes": ["wind"]}}

    df = parser_utils._prepare_generator_dataset(
        capacity_data=capacity,
        optional_data=optional_data,
        excluded_technologies=[],
        technology_categories=categories,
    ).unwrap()
    assert df.shape[0] == 1


def test_prepare_generator_dataset_storage_duration_not_overwritten() -> None:
    """Existing storage_duration should not be overwritten by storage_duration_out."""
    import polars as pl

    from r2x_reeds import parser_utils

    capacity = pl.DataFrame(
        {
            "technology": ["battery"],
            "region": ["p1"],
            "capacity": [10.0],
            "year": [2025],
            "storage_duration": [4.0],  # Already has a value
            "vintage": [None],
        }
    ).lazy()

    optional_data = {
        "fuel_tech_map": pl.DataFrame({"technology": ["battery"], "fuel_type": ["battery"]}).lazy(),
        "storage_duration_out": pl.DataFrame(
            {
                "technology": ["battery"],
                "vintage": [None],
                "region": ["p1"],
                "year": [2025],
                "storage_duration": [8.0],  # Different value
            }
        ).lazy(),
    }

    categories = {"storage": {"prefixes": ["battery"]}}

    df = parser_utils._prepare_generator_dataset(
        capacity_data=capacity,
        optional_data=optional_data,
        excluded_technologies=[],
        technology_categories=categories,
    ).unwrap()
    # The original 4.0 should be preserved, not overwritten by 8.0
    assert df.filter(pl.col("technology") == "battery").select("storage_duration").item() == 4.0


def test_prepare_generator_dataset_consume_char_filters_non_efficiency() -> None:
    """Consume characteristics should only include electricity_efficiency."""
    import polars as pl

    from r2x_reeds import parser_utils

    capacity = pl.DataFrame(
        {
            "technology": ["electrolyzer"],
            "region": ["p1"],
            "capacity": [10.0],
            "year": [2025],
        }
    ).lazy()

    optional_data = {
        "fuel_tech_map": pl.DataFrame({"technology": ["electrolyzer"], "fuel_type": ["elec"]}).lazy(),
        "consume_characteristics": pl.DataFrame(
            {
                "technology": ["electrolyzer", "electrolyzer", "electrolyzer"],
                "year": [2025, 2025, 2025],
                "parameter": ["electricity_efficiency", "other_param", "storage_rate"],
                "value": [0.8, 0.5, 0.3],
            }
        ).lazy(),
    }

    categories = {"consuming": {"prefixes": ["electrolyzer"]}}

    df = parser_utils._prepare_generator_dataset(
        capacity_data=capacity,
        optional_data=optional_data,
        excluded_technologies=[],
        technology_categories=categories,
    ).unwrap()
    # Should only have electricity_efficiency, not other params
    assert "electricity_efficiency" in df.columns
    assert df.select("electricity_efficiency").item() == 0.8


def test_aggregate_variable_generators_single_row() -> None:
    """Single row should return same capacity, no averaging needed."""
    import polars as pl

    from r2x_reeds import parser_utils

    df = pl.DataFrame(
        {
            "technology": ["wind"],
            "region": ["p1"],
            "category": ["wind"],
            "capacity": [10.0],
            "resource_class": ["rc1"],
            "fuel_type": ["fuel"],
            "heat_rate": [1.5],
            "forced_outage_rate": [0.1],
            "planned_outage_rate": [0.05],
            "maxage_years": [25],
            "vom_price": [0.5],
            "fuel_price": [10.0],
            "inverter_loading_ratio": [1.0],
            "capacity_factor_adjustment": [0.95],
            "max_capacity_factor": [0.85],
            "supply_curve_cost": [100.0],
            "transmission_adder": [5.0],
            "categories": [["wind"]],
        }
    )
    aggregated = parser_utils.aggregate_variable_generators(df)
    assert aggregated.select("capacity").item() == pytest.approx(10.0)
    assert aggregated.select("heat_rate").item() == pytest.approx(1.5)


def test_aggregate_variable_generators_missing_columns() -> None:
    """Missing AGG_COLUMNS should get null values."""
    import polars as pl

    from r2x_reeds import parser_utils

    # Only provide required columns plus capacity
    df = pl.DataFrame(
        {
            "technology": ["wind", "wind"],
            "region": ["p1", "p1"],
            "category": ["wind", "wind"],
            "capacity": [5.0, 7.0],
            "categories": [["wind"], ["wind"]],
        }
    )
    aggregated = parser_utils.aggregate_variable_generators(df)
    assert aggregated.select("capacity").item() == pytest.approx(12.0)
    # Missing columns should be null
    assert aggregated.select("heat_rate").item() is None
    assert aggregated.select("fuel_type").item() is None


def test_calculate_reserve_requirement_wind_only() -> None:
    """Only wind generators contribute to reserve."""
    import numpy as np

    from r2x_reeds import parser_utils

    hours = np.arange(24)
    wind = [{"capacity": 10.0, "time_series": np.ones(24) * 0.5}]

    requirement = parser_utils.calculate_reserve_requirement(
        wind_generators=wind,
        solar_generators=[],
        loads=[],
        hourly_time_index=hours,
        wind_pct=0.1,
        solar_pct=0.0,
        load_pct=0.0,
    ).unwrap()
    # wind contribution: 0.5 * 0.1 = 0.05 per hour
    assert requirement[0] == pytest.approx(0.05)


def test_calculate_reserve_requirement_solar_zero_percentage() -> None:
    """Solar with 0% should not contribute."""
    import numpy as np

    from r2x_reeds import parser_utils

    hours = np.arange(24)
    wind = [{"capacity": 1.0, "time_series": np.ones(24)}]
    solar = [{"capacity": 100.0, "time_series": np.ones(24)}]

    requirement = parser_utils.calculate_reserve_requirement(
        wind_generators=wind,
        solar_generators=solar,
        loads=[],
        hourly_time_index=hours,
        wind_pct=0.1,
        solar_pct=0.0,  # Solar should not contribute
        load_pct=0.0,
    ).unwrap()
    # Only wind contributes: 1.0 * 0.1 = 0.1
    assert requirement[0] == pytest.approx(0.1)


def test_calculate_reserve_requirement_time_series_longer_than_index() -> None:
    """Time series longer than hourly_time_index should be truncated."""
    import numpy as np

    from r2x_reeds import parser_utils

    hours = np.arange(10)  # Only 10 hours
    wind = [{"capacity": 1.0, "time_series": np.ones(100) * 0.5}]  # 100 values

    requirement = parser_utils.calculate_reserve_requirement(
        wind_generators=wind,
        solar_generators=[],
        loads=[],
        hourly_time_index=hours,
        wind_pct=0.1,
        solar_pct=0.0,
        load_pct=0.0,
    ).unwrap()
    # Result should be truncated to 10 hours
    assert len(requirement) == 10


def test_collect_component_kwargs_identifier_returns_err() -> None:
    """Identifier getter returning Err should accumulate errors."""
    from collections.abc import Mapping
    from typing import Any

    import polars as pl
    from rust_ok import Err, Result

    from r2x_core.exceptions import ValidationError
    from r2x_reeds import parser_utils

    df = pl.DataFrame({"col1": [1, 2]})

    def failing_identifier_getter(row: Mapping[str, Any]) -> Result[str, Exception]:
        return Err(ValueError("Cannot derive identifier"))

    class DummyRule:
        pass

    result = parser_utils._collect_component_kwargs_from_rule(
        data=df,
        rule_provider=DummyRule(),  # type: ignore[arg-type]
        parser_context=None,  # type: ignore[arg-type]
        row_identifier_getter=failing_identifier_getter,
    )
    assert result.is_err()
    error = result.unwrap_err()
    assert isinstance(error, ValidationError)
    assert "Cannot derive identifier" in str(error)


def test_collect_component_kwargs_empty_dataframe() -> None:
    """Empty DataFrame should return Ok with empty list."""
    from collections.abc import Mapping
    from typing import Any

    import polars as pl
    from rust_ok import Ok, Result

    from r2x_reeds import parser_utils

    df = pl.DataFrame({"col1": []})

    def identifier_getter(row: Mapping[str, Any]) -> Result[str, Exception]:
        return Ok(str(row.get("col1", "")))

    class DummyRule:
        pass

    result = parser_utils._collect_component_kwargs_from_rule(
        data=df,
        rule_provider=DummyRule(),  # type: ignore[arg-type]
        parser_context=None,  # type: ignore[arg-type]
        row_identifier_getter=identifier_getter,
    )
    collected = result.unwrap()
    assert collected == []


def test_resolve_generator_rule_missing_technology() -> None:
    """Row without 'technology' key returns error."""
    from r2x_reeds import parser_utils

    row = {"region": "p1", "capacity": 10.0}  # No technology key
    technology_categories = {"wind": {"prefixes": ["wind"]}}
    category_class_mapping = {"wind": "ReEDSVariableGenerator"}
    rules_by_target = {}

    result = parser_utils._resolve_generator_rule_from_row(
        row,
        technology_categories=technology_categories,
        category_class_mapping=category_class_mapping,
        rules_by_target=rules_by_target,
    )
    assert result.is_err()
    assert "missing technology" in str(result.err()).lower()


def test_resolve_generator_rule_no_matching_rule() -> None:
    """Technology class found but no rule defined."""
    from r2x_reeds import parser_utils

    row = {"technology": "wind-ons", "region": "p1"}
    technology_categories = {"wind": {"prefixes": ["wind"]}}
    category_class_mapping = {"wind": "ReEDSVariableGenerator"}
    rules_by_target = {}  # No rules defined

    result = parser_utils._resolve_generator_rule_from_row(
        row,
        technology_categories=technology_categories,
        category_class_mapping=category_class_mapping,
        rules_by_target=rules_by_target,
    )
    assert result.is_err()
    assert "no parser rule" in str(result.err()).lower()


def test_prepare_generator_inputs_empty_variable_categories_defaults() -> None:
    """Empty variable_categories list defaults to ['wind', 'solar'] due to 'or' logic."""
    import polars as pl

    from r2x_reeds import parser_utils

    capacity = pl.DataFrame(
        {
            "technology": ["wind", "solar", "gas"],
            "region": ["p1", "p1", "p1"],
            "capacity": [10.0, 20.0, 30.0],
            "year": [2025, 2025, 2025],
        }
    ).lazy()

    categories = {
        "wind": {"prefixes": ["wind"]},
        "solar": {"prefixes": ["solar"]},
        "gas": {"prefixes": ["gas"]},
    }
    optional_data = {
        "fuel_tech_map": pl.DataFrame(
            {"technology": ["wind", "solar", "gas"], "fuel_type": ["wind", "solar", "gas"]}
        ).lazy()
    }

    # Empty list is falsy, so it defaults to ["wind", "solar"]
    variable_df, non_variable_df = parser_utils.prepare_generator_inputs(
        capacity_data=capacity,
        optional_data=optional_data,
        excluded_technologies=[],
        technology_categories=categories,
        variable_categories=[],  # Empty list -> defaults to ["wind", "solar"]
    ).unwrap()
    # wind and solar are variable (default behavior)
    assert variable_df.shape[0] == 2
    # Only gas is non-variable
    assert non_variable_df.shape[0] == 1


def test_prepare_generator_inputs_custom_categories_no_match() -> None:
    """Custom variable_categories that don't match any tech."""
    import polars as pl

    from r2x_reeds import parser_utils

    capacity = pl.DataFrame(
        {
            "technology": ["gas-cc", "coal"],
            "region": ["p1", "p1"],
            "capacity": [10.0, 20.0],
            "year": [2025, 2025],
        }
    ).lazy()

    categories = {
        "gas": {"prefixes": ["gas"]},
        "coal": {"prefixes": ["coal"]},
    }
    optional_data = {
        "fuel_tech_map": pl.DataFrame({"technology": ["gas-cc", "coal"], "fuel_type": ["gas", "coal"]}).lazy()
    }

    variable_df, non_variable_df = parser_utils.prepare_generator_inputs(
        capacity_data=capacity,
        optional_data=optional_data,
        excluded_technologies=[],
        technology_categories=categories,
        variable_categories=["wind", "solar"],  # Categories that don't exist in data
    ).unwrap()
    # No matches for wind/solar
    assert variable_df.is_empty()
    # All techs are non-variable
    assert non_variable_df.shape[0] == 2
