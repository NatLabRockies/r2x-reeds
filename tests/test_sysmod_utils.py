from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


@pytest.mark.unit
def test_deduplicate_records_warns_and_keeps_first() -> None:
    """Verify duplicate detection and first-occurrence preservation."""
    from r2x_reeds.sysmod.utils import _deduplicate_records

    records = [
        {"name": "battery", "avg_capacity_MW": 10},
        {"name": "battery", "avg_capacity_MW": 12},
        {"name": "wind", "avg_capacity_MW": 40},
    ]

    result = _deduplicate_records(records, key="name")

    assert len(result) == 2
    assert result[0]["avg_capacity_MW"] == 10
    assert result[1]["name"] == "wind"


@pytest.mark.unit
def test_deduplicate_records_none_returns_empty() -> None:
    """Test that None input returns empty list (covers line 35)."""
    from r2x_reeds.sysmod.utils import _deduplicate_records

    result = _deduplicate_records(None, key="name")

    assert result == []
    assert isinstance(result, list)


@pytest.mark.unit
def test_deduplicate_records_empty_iterable_returns_empty() -> None:
    """Test that empty list returns empty list."""
    from r2x_reeds.sysmod.utils import _deduplicate_records

    result = _deduplicate_records([], key="name")

    assert result == []


@pytest.mark.unit
def test_deduplicate_records_with_non_dict_skips_and_warns() -> None:
    """Test that non-dict records are skipped (covers lines 44-45)."""
    from r2x_reeds.sysmod.utils import _deduplicate_records

    records: list[Any] = [
        {"name": "battery", "value": 10},
        "not a dict",
        42,
        {"name": "solar", "value": 20},
    ]

    result = _deduplicate_records(records, key="name")

    assert len(result) == 2
    assert result[0]["name"] == "battery"
    assert result[1]["name"] == "solar"


@pytest.mark.unit
def test_deduplicate_records_missing_key_keeps_and_warns() -> None:
    """Test that records missing the key are kept (covers lines 48-50, 70-73)."""
    from r2x_reeds.sysmod.utils import _deduplicate_records

    records = [
        {"name": "battery", "value": 10},
        {"other_field": "missing name key"},
        {"different": "also missing name"},
        {"name": "solar", "value": 20},
    ]

    result = _deduplicate_records(records, key="name")

    assert len(result) == 4
    assert result[0]["name"] == "battery"
    assert "other_field" in result[1]
    assert "different" in result[2]
    assert result[3]["name"] == "solar"


@pytest.mark.unit
def test_deduplicate_records_no_duplicates_no_warnings() -> None:
    """Test happy path: valid unique records."""
    from r2x_reeds.sysmod.utils import _deduplicate_records

    records = [
        {"name": "battery", "value": 10},
        {"name": "solar", "value": 20},
        {"name": "wind", "value": 30},
    ]

    result = _deduplicate_records(records, key="name")

    assert len(result) == 3
    assert result[0]["name"] == "battery"
    assert result[1]["name"] == "solar"
    assert result[2]["name"] == "wind"


@pytest.mark.unit
def test_deduplicate_records_combined_issues() -> None:
    """Integration test: duplicates + missing keys + non-dicts together."""
    from r2x_reeds.sysmod.utils import _deduplicate_records

    records: list[Any] = [
        {"name": "battery", "value": 10},
        {"name": "battery", "value": 12},
        "invalid",
        {"no_name_field": True},
        {"name": "solar", "value": 20},
    ]

    result = _deduplicate_records(records, key="name")

    assert len(result) == 3
    assert result[0]["value"] == 10
    assert result[1] == {"no_name_field": True}
    assert result[2]["name"] == "solar"


@pytest.mark.unit
def test_coerce_path_valid_file_returns_ok(tmp_path: Path) -> None:
    """Test successful path coercion with valid file."""
    from r2x_reeds.sysmod.utils import _coerce_path

    test_file = tmp_path / "test.csv"
    test_file.write_text("test data")

    result = _coerce_path(test_file)

    assert result.is_ok()
    assert result.unwrap() == test_file


@pytest.mark.unit
def test_coerce_path_string_path_returns_ok(tmp_path: Path) -> None:
    """Test string path conversion to Path object."""
    from r2x_reeds.sysmod.utils import _coerce_path

    test_file = tmp_path / "test.csv"
    test_file.write_text("test data")

    result = _coerce_path(str(test_file))

    assert result.is_ok()
    assert result.unwrap() == test_file


@pytest.mark.unit
def test_coerce_path_directory_returns_err(tmp_path: Path) -> None:
    """Test directory path returns IsADirectoryError (covers line 96 - CRITICAL)."""
    from r2x_reeds.sysmod.utils import _coerce_path

    test_dir = tmp_path / "test_directory"
    test_dir.mkdir()

    result = _coerce_path(test_dir)

    assert result.is_err()
    error = result.unwrap_err()
    assert isinstance(error, IsADirectoryError)
    assert "Expected a file path" in str(error)
    assert "got directory" in str(error)


@pytest.mark.unit
def test_coerce_path_nonexistent_file_returns_err(tmp_path: Path) -> None:
    """Test FileNotFoundError for non-existent path."""
    from r2x_reeds.sysmod.utils import _coerce_path

    nonexistent = tmp_path / "does_not_exist.csv"

    result = _coerce_path(nonexistent)

    assert result.is_err()
    error = result.unwrap_err()
    assert isinstance(error, FileNotFoundError)
    assert "not found" in str(error)


@pytest.mark.unit
def test_coerce_path_invalid_type_returns_err() -> None:
    """Test TypeError for invalid path type."""
    from r2x_reeds.sysmod.utils import _coerce_path

    result = _coerce_path(123)  # type: ignore

    assert result.is_err()
    error = result.unwrap_err()
    assert isinstance(error, TypeError)
    assert "path-like object" in str(error)


@pytest.mark.unit
def test_coerce_path_pathlike_object_returns_ok(tmp_path: Path) -> None:
    """Test PathLike protocol support."""
    from r2x_reeds.sysmod.utils import _coerce_path

    test_file = tmp_path / "test.csv"
    test_file.write_text("test data")

    result = _coerce_path(test_file)

    assert result.is_ok()
    assert result.unwrap() == test_file
