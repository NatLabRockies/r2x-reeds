"""Tests for parser validation functions in parser_checks.py."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from r2x_core import DataStore


def test_dataset_exists_and_non_empty_success(example_data_store: DataStore) -> None:
    """Test successful validation when dataset exists and has data."""
    from r2x_reeds.parser_checks import check_dataset_non_empty

    result = check_dataset_non_empty(example_data_store, "modeled_years")
    assert result.is_ok()


def test_dataset_missing_from_store_error(example_data_store: DataStore) -> None:
    """Test error when dataset key not in DataStore."""
    from r2x_core import ValidationError
    from r2x_reeds.parser_checks import check_dataset_non_empty

    result = check_dataset_non_empty(example_data_store, "nonexistent_dataset")
    assert result.is_err()
    error = result.unwrap_err()
    assert isinstance(error, ValidationError)
    assert "Key nonexistent_dataset not found" in str(error)
    assert "Check spelling" in str(error)


def test_dataset_with_placeholder_substitution(example_data_store: DataStore) -> None:
    """Test that placeholders parameter is passed to read_data."""
    from r2x_reeds.parser_checks import check_dataset_non_empty

    placeholders = {"solve_year": 2032}
    result = check_dataset_non_empty(example_data_store, "modeled_years", placeholders=placeholders)
    assert result.is_ok()


def test_column_exists_success(example_data_store: DataStore) -> None:
    """Test successful validation when column exists in dataset."""
    from r2x_reeds.parser_checks import check_column_exists

    result = check_column_exists(example_data_store, "modeled_years", "modeled_years")
    assert result.is_ok()


def test_column_missing_error_with_available_columns(example_data_store: DataStore) -> None:
    """Test error with helpful message listing available columns."""
    from r2x_core import ValidationError
    from r2x_reeds.parser_checks import check_column_exists

    result = check_column_exists(example_data_store, "hierarchy", "nonexistent_column")
    assert result.is_err()
    error = result.unwrap_err()
    assert isinstance(error, ValidationError)
    assert "Column" in str(error)
    assert "nonexistent_column" in str(error)
    assert "not found" in str(error)


def test_dataset_check_fails_early_return(example_data_store: DataStore) -> None:
    """Test early return when dataset doesn't exist."""
    from r2x_core import ValidationError
    from r2x_reeds.parser_checks import check_column_exists

    result = check_column_exists(example_data_store, "nonexistent_dataset", "some_column")
    assert result.is_err()
    error = result.unwrap_err()
    assert isinstance(error, ValidationError)
    # Should fail on dataset check, not column check
    assert "not found in data store" in str(error).lower()


def test_column_with_placeholder_substitution(example_data_store: DataStore) -> None:
    """Test that placeholders parameter is passed through."""
    from r2x_reeds.parser_checks import check_column_exists

    placeholders = {"solve_year": 2032}
    result = check_column_exists(
        example_data_store, "modeled_years", "modeled_years", placeholders=placeholders
    )
    assert result.is_ok()


def test_single_required_value_present(example_data_store: DataStore) -> None:
    """Test validation passes when single required value exists."""
    from r2x_reeds.parser_checks import check_required_values_in_column

    result = check_required_values_in_column(
        store=example_data_store,
        dataset="modeled_years",
        column_name="modeled_years",
        required_values=[2032],
    )
    assert result.is_ok()


def test_missing_value_error_with_available_list(example_data_store: DataStore) -> None:
    """Test error message includes missing values and available values."""
    from r2x_core import ValidationError
    from r2x_reeds.parser_checks import check_required_values_in_column

    result = check_required_values_in_column(
        store=example_data_store,
        dataset="modeled_years",
        column_name="modeled_years",
        required_values=[1999, 2032],
        what="Test year(s)",
    )
    assert result.is_err()
    error = result.unwrap_err()
    assert isinstance(error, ValidationError)
    assert "Test year(s)" in str(error)
    assert "1999" in str(error)
    assert "not found" in str(error)


def test_iterable_required_values_handling_list(example_data_store: DataStore) -> None:
    """Test proper handling of iterable required_values with list."""
    from r2x_reeds.parser_checks import check_required_values_in_column

    result_list = check_required_values_in_column(
        store=example_data_store,
        dataset="modeled_years",
        column_name="modeled_years",
        required_values=[2032],
    )
    assert result_list.is_ok()


def test_iterable_required_values_handling_tuple(example_data_store: DataStore) -> None:
    """Test proper handling of iterable required_values with tuple."""
    from r2x_reeds.parser_checks import check_required_values_in_column

    result_tuple = check_required_values_in_column(
        store=example_data_store,
        dataset="modeled_years",
        column_name="modeled_years",
        required_values=(2032,),
    )
    assert result_tuple.is_ok()


def test_string_required_value_handling(example_data_store: DataStore) -> None:
    """Test proper handling when required_values is a single non-iterable value."""
    from r2x_reeds.parser_checks import check_required_values_in_column

    result = check_required_values_in_column(
        store=example_data_store,
        dataset="modeled_years",
        column_name="modeled_years",
        required_values=2032,
    )
    assert result.is_ok()


def test_column_check_fails_early_return(example_data_store: DataStore) -> None:
    """Test early return when column check fails."""
    from r2x_core import ValidationError
    from r2x_reeds.parser_checks import check_required_values_in_column

    result = check_required_values_in_column(
        store=example_data_store,
        dataset="modeled_years",
        column_name="nonexistent_column",
        required_values=[2032],
    )
    assert result.is_err()
    error = result.unwrap_err()
    assert isinstance(error, ValidationError)
    assert "nonexistent_column" in str(error)


def test_default_column_name_uses_dataset_name(example_data_store: DataStore) -> None:
    """Test that column_name defaults to dataset name when not provided."""
    from r2x_reeds.parser_checks import check_required_values_in_column

    result = check_required_values_in_column(
        store=example_data_store,
        dataset="modeled_years",
        required_values=[2032],
    )
    assert result.is_ok()


def test_multiple_missing_values_reported(example_data_store: DataStore) -> None:
    """Test that all missing values are reported in error message."""
    from r2x_core import ValidationError
    from r2x_reeds.parser_checks import check_required_values_in_column

    result = check_required_values_in_column(
        store=example_data_store,
        dataset="modeled_years",
        column_name="modeled_years",
        required_values=[1999, 2000, 2020],
        what="Historical years",
    )
    assert result.is_err()
    error = result.unwrap_err()
    assert isinstance(error, ValidationError)
    error_str = str(error)
    # All missing values should be mentioned
    assert "1999" in error_str
    assert "2000" in error_str
    assert "2020" in error_str


def test_with_placeholder_substitution(example_data_store: DataStore) -> None:
    """Test that placeholders parameter is passed through."""
    from r2x_reeds.parser_checks import check_required_values_in_column

    placeholders = {"solve_year": 2032}
    result = check_required_values_in_column(
        store=example_data_store,
        dataset="modeled_years",
        column_name="modeled_years",
        required_values=[2032],
        placeholders=placeholders,
    )
    assert result.is_ok()
