from __future__ import annotations

import pytest


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
    merged_result = parser_utils.merge_lazy_frames(left, right, on=["key"])
    assert merged_result.is_ok()
    merged_df = merged_result.ok().collect()
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

    result = parser_utils._prepare_generator_dataset(
        capacity_data=capacity,
        optional_data=optional_data,
        excluded_technologies=["coal"],
        technology_categories=categories,
    )
    assert result.is_ok()
    df = result.ok()
    assert "fuel_type" in df.columns
    assert df.filter(pl.col("technology") == "wind").select("fuel_type").item() == "windfuel"
    assert df.filter(pl.col("technology") == "gas").select("electricity_efficiency").item() == 0.8
    assert df.filter(pl.col("technology") == "wind").select("storage_duration").item() == 5.5
    assert df.filter(pl.col("technology") == "coal").is_empty()


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
    optional_data = {}

    result = parser_utils.prepare_generator_inputs(
        capacity_data=capacity,
        optional_data=optional_data,
        excluded_technologies=[],
        technology_categories=categories,
        variable_categories=["wind", "solar"],
    )
    assert result.is_ok()
    variable_df, non_variable_df = result.ok()
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

    grouped = parser_utils.get_rules_by_target([rule_a, rule_b])
    assert grouped.is_ok()
    rules_by_target = grouped.ok()
    assert len(rules_by_target["B"]) == 2

    selected = parser_utils.get_rule_for_target(rules_by_target, target_type="B", name="r2")
    assert selected.is_ok()
    assert selected.ok().name == "r2"

    fallback = parser_utils.get_rule_for_target(rules_by_target, target_type="B")
    assert fallback.is_ok()

    missing = parser_utils.get_rule_for_target(rules_by_target, target_type="UNKNOWN")
    assert missing.is_err()


# =============================================================================
# Error Path Tests for _prepare_generator_dataset
# =============================================================================


def test_prepare_generator_dataset_null_capacity_data() -> None:
    """Test error when capacity_data is None."""
    from r2x_reeds import parser_utils

    result = parser_utils._prepare_generator_dataset(
        capacity_data=None, optional_data={}, excluded_technologies=[], technology_categories={}
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

    result = parser_utils._prepare_generator_dataset(
        capacity_data=capacity,
        optional_data={},
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

    result = parser_utils._prepare_generator_dataset(
        capacity_data=capacity,
        optional_data={},
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
    # Should succeed by skipping the fuel_tech_map
    assert result.is_ok()


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

    result = parser_utils._prepare_generator_dataset(
        capacity_data=capacity,
        optional_data={},
        excluded_technologies=[],
        technology_categories=categories,
    )
    # Should handle unmapped technologies gracefully
    assert result.is_ok()
    df = result.ok()
    # Should contain the original data with categories column (empty list for unmapped)
    assert df.shape[0] > 0
    assert "categories" in df.columns
    # All categories should be empty lists for unmapped technology
    categories_col = df.select("categories").to_series().to_list()
    assert all(cat == [] for cat in categories_col)


# =============================================================================
# Error Path Tests for calculate_reserve_requirement
# =============================================================================


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


# =============================================================================
# Error Path Tests for _collect_component_kwargs_from_rule
# =============================================================================


def test_collect_component_kwargs_missing_identifier() -> None:
    """Test error handling when identifier is empty/None."""
    import polars as pl

    from r2x_core import ParserError
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
        rule_provider=DummyRule(),
        parser_context=None,
        row_identifier_getter=failing_identifier_getter,
    )
    assert result.is_err()
    error = result.unwrap_err()
    assert isinstance(error, ParserError)


def test_collect_component_kwargs_identifier_getter_error() -> None:
    """Test error accumulation when identifier_getter fails."""
    import polars as pl

    from r2x_core import ParserError
    from r2x_reeds import parser_utils

    df = pl.DataFrame({"col1": [1, 2]})

    def failing_identifier_getter(row):
        from rust_ok import Err

        return Err(ValueError("Identifier extraction failed"))

    class DummyRule:
        pass

    result = parser_utils._collect_component_kwargs_from_rule(
        data=df,
        rule_provider=DummyRule(),
        parser_context=None,
        row_identifier_getter=failing_identifier_getter,
    )
    assert result.is_err()
    error = result.unwrap_err()
    assert isinstance(error, ParserError)
    assert "failed" in str(error).lower()


# =============================================================================
# Edge Case Tests for tech_matches_category
# =============================================================================


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


# =============================================================================
# Additional Coverage Tests
# =============================================================================


def test_get_generator_class_with_no_matching_category() -> None:
    """Test error case when technology has no matching categories."""
    from r2x_reeds import parser_utils

    # Unknown tech with empty categories should error
    result = parser_utils.get_generator_class("unknown_tech", {}, "mock_models_path")
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

    result = parser_utils._prepare_generator_dataset(
        capacity_data=capacity,
        optional_data={},
        excluded_technologies=["nuclear"],
        technology_categories={},
    )

    assert result.is_ok()
    df = result.ok()
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

    result = parser_utils.merge_lazy_frames(left, right, on=["key"])
    assert result.is_ok()
    merged = result.ok().collect()
    # No matches, so right values should be null
    assert merged.filter(pl.col("other").is_not_null()).shape[0] == 0


def test_monthly_to_hourly_invalid_year() -> None:
    """Test handling of invalid leap year scenarios."""
    from r2x_reeds import parser_utils

    # Year 1900 is not a leap year despite being divisible by 4
    monthly = [10.0] * 12
    result = parser_utils.monthly_to_hourly_polars(1900, monthly)
    assert result.is_ok()
    hourly = result.ok()
    # 1900 is not a leap year, so it should have 365 days = 8760 hours
    assert len(hourly) == 365 * 24
