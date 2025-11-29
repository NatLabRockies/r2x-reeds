"""Tests for r2x_reeds.row_utils module.

Tests verify that row utility functions correctly handle:
- Dictionary inputs
- SimpleNamespace inputs
- Objects with __dict__ attributes
- Missing fields
- Falsy vs None vs missing field distinction
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    pass


@pytest.fixture
def dict_row_with_data() -> dict[str, object]:
    """Fixture for a dict with test data."""
    return {"name": "test", "value": 42}


@pytest.fixture
def dict_row_sparse() -> dict[str, str]:
    """Fixture for a sparse dict with limited fields."""
    return {"name": "test"}


@pytest.fixture
def dict_row_with_none() -> dict[str, object]:
    """Fixture for a dict with None value."""
    return {"value": None}


@pytest.fixture
def namespace_row_with_data():
    """Fixture for a namespace with test data."""
    from types import SimpleNamespace

    return SimpleNamespace(name="test", value=42)


@pytest.fixture
def namespace_row_sparse():
    """Fixture for a sparse namespace with limited fields."""
    from types import SimpleNamespace

    return SimpleNamespace(name="test")


@pytest.fixture
def namespace_row_with_none():
    """Fixture for a namespace with None value."""
    from types import SimpleNamespace

    return SimpleNamespace(value=None)


@pytest.mark.unit
def test_get_row_field_dict_existing_field(dict_row_with_data: dict[str, object]) -> None:
    """Test extracting existing fields from dict."""
    from r2x_reeds.row_utils import get_row_field

    assert get_row_field(dict_row_with_data, "name") == "test"
    assert get_row_field(dict_row_with_data, "value") == 42


@pytest.mark.unit
def test_get_row_field_dict_missing_field_default_none(dict_row_sparse: dict[str, str]) -> None:
    """Test extracting missing field from dict with None default."""
    from r2x_reeds.row_utils import get_row_field

    assert get_row_field(dict_row_sparse, "missing") is None


@pytest.mark.unit
def test_get_row_field_dict_missing_field_custom_default(
    dict_row_sparse: dict[str, str],
) -> None:
    """Test extracting missing field from dict with custom defaults."""
    from r2x_reeds.row_utils import get_row_field

    for default, expected in [
        ("default", "default"),
        (0, 0),
        ([], []),
    ]:
        assert get_row_field(dict_row_sparse, "missing", default) == expected


@pytest.mark.unit
def test_get_row_field_dict_none_value(dict_row_with_none: dict[str, object]) -> None:
    """Test that None value is distinguished from missing field."""
    from r2x_reeds.row_utils import get_row_field

    assert get_row_field(dict_row_with_none, "value") is None
    assert get_row_field(dict_row_with_none, "missing") is None
    assert get_row_field(dict_row_with_none, "missing", "default") == "default"


@pytest.mark.unit
def test_get_row_field_dict_falsy_values() -> None:
    """Test that falsy values are returned correctly, not treated as missing."""
    from r2x_reeds.row_utils import get_row_field

    for value in [0, "", [], {}, False, 0.0]:
        row: dict[str, object] = {"field": value}
        assert get_row_field(row, "field") == value


@pytest.mark.unit
def test_get_row_field_namespace_existing_field(namespace_row_with_data) -> None:
    """Test extracting existing fields from SimpleNamespace."""
    from r2x_reeds.row_utils import get_row_field

    assert get_row_field(namespace_row_with_data, "name") == "test"
    assert get_row_field(namespace_row_with_data, "value") == 42


@pytest.mark.unit
def test_get_row_field_namespace_missing_field_default_none(namespace_row_sparse) -> None:
    """Test extracting missing field from namespace with None default."""
    from r2x_reeds.row_utils import get_row_field

    assert get_row_field(namespace_row_sparse, "missing") is None


@pytest.mark.unit
def test_get_row_field_namespace_missing_field_custom_default(namespace_row_sparse) -> None:
    """Test extracting missing field from namespace with custom defaults."""
    from r2x_reeds.row_utils import get_row_field

    for default, expected in [
        ("default", "default"),
        (0, 0),
        ([], []),
    ]:
        assert get_row_field(namespace_row_sparse, "missing", default) == expected


@pytest.mark.unit
def test_get_row_field_namespace_none_value(namespace_row_with_none) -> None:
    """Test None value in namespace."""
    from r2x_reeds.row_utils import get_row_field

    assert get_row_field(namespace_row_with_none, "value") is None
    assert get_row_field(namespace_row_with_none, "missing", "default") == "default"


@pytest.mark.unit
def test_get_row_field_namespace_falsy_values() -> None:
    """Test that falsy values are returned correctly from namespace."""
    from types import SimpleNamespace

    from r2x_reeds.row_utils import get_row_field

    for value in [0, "", [], {}, False, 0.0]:
        row = SimpleNamespace(field=value)
        assert get_row_field(row, "field") == value


@pytest.mark.unit
def test_dict_namespace_consistency_existing_field() -> None:
    """Test consistent behavior for existing fields."""
    from types import SimpleNamespace

    from r2x_reeds.row_utils import get_row_field

    for value in ["test_value", 42, 3.14]:
        dict_row: dict[str, object] = {"field": value}
        ns_row = SimpleNamespace(field=value)
        assert get_row_field(dict_row, "field") == get_row_field(ns_row, "field")
        assert get_row_field(dict_row, "field") == value


@pytest.mark.unit
def test_dict_namespace_consistency_missing_field() -> None:
    """Test consistent behavior for missing fields."""
    from types import SimpleNamespace

    from r2x_reeds.row_utils import get_row_field

    dict_row: dict[str, str] = {"other": "value"}
    ns_row = SimpleNamespace(other="value")
    assert get_row_field(dict_row, "missing") == get_row_field(ns_row, "missing")
    assert get_row_field(dict_row, "missing", "default") == get_row_field(ns_row, "missing", "default")


@pytest.mark.unit
def test_dict_namespace_consistency_falsy_values() -> None:
    """Test consistent handling of falsy values between dict and namespace."""
    from types import SimpleNamespace

    from r2x_reeds.row_utils import get_row_field

    for value in [0, "", [], {}, False]:
        dict_row: dict[str, object] = {"field": value}
        ns_row = SimpleNamespace(field=value)
        assert get_row_field(dict_row, "field") == get_row_field(ns_row, "field")
        assert get_row_field(dict_row, "field") == value


@pytest.mark.unit
def test_has_row_field_dict_existing(dict_row_with_data: dict[str, object]) -> None:
    """Test checking existing fields in dict."""
    from r2x_reeds.row_utils import has_row_field

    assert has_row_field(dict_row_with_data, "name") is True
    assert has_row_field(dict_row_with_data, "value") is True


@pytest.mark.unit
def test_has_row_field_dict_existing_with_none(dict_row_with_none: dict[str, object]) -> None:
    """Test that existing field with None value is still detected."""
    from r2x_reeds.row_utils import has_row_field

    assert has_row_field(dict_row_with_none, "value") is True


@pytest.mark.unit
def test_has_row_field_dict_missing(dict_row_sparse: dict[str, str]) -> None:
    """Test checking missing field in dict."""
    from r2x_reeds.row_utils import has_row_field

    assert has_row_field(dict_row_sparse, "missing") is False


@pytest.mark.unit
def test_has_row_field_dict_empty() -> None:
    """Test checking field in empty dict."""
    from r2x_reeds.row_utils import has_row_field

    row: dict[str, object] = {}
    assert has_row_field(row, "field") is False


@pytest.mark.unit
def test_has_row_field_namespace_existing(namespace_row_with_data) -> None:
    """Test checking existing fields in namespace."""
    from r2x_reeds.row_utils import has_row_field

    assert has_row_field(namespace_row_with_data, "name") is True
    assert has_row_field(namespace_row_with_data, "value") is True


@pytest.mark.unit
def test_has_row_field_namespace_existing_with_none(namespace_row_with_none) -> None:
    """Test that existing field with None value is still detected."""
    from r2x_reeds.row_utils import has_row_field

    assert has_row_field(namespace_row_with_none, "value") is True


@pytest.mark.unit
def test_has_row_field_namespace_missing(namespace_row_sparse) -> None:
    """Test checking missing field in namespace."""
    from r2x_reeds.row_utils import has_row_field

    assert has_row_field(namespace_row_sparse, "missing") is False


@pytest.mark.unit
def test_has_row_field_namespace_empty() -> None:
    """Test checking field in empty namespace."""
    from types import SimpleNamespace

    from r2x_reeds.row_utils import has_row_field

    row = SimpleNamespace()
    assert has_row_field(row, "field") is False


@pytest.mark.unit
def test_dict_namespace_has_field_consistency() -> None:
    """Test consistent field existence checks between dict and namespace."""
    from types import SimpleNamespace

    from r2x_reeds.row_utils import has_row_field

    dict_row: dict[str, object] = {"name": "test", "value": None}
    ns_row = SimpleNamespace(name="test", value=None)

    assert has_row_field(dict_row, "name") == has_row_field(ns_row, "name") is True
    assert has_row_field(dict_row, "value") == has_row_field(ns_row, "value") is True
    assert has_row_field(dict_row, "missing") == has_row_field(ns_row, "missing") is False
