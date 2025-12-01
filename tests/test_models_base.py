"""Tests for ReEDS base models."""

import pytest
from pydantic import ValidationError

from r2x_reeds.models.base import FromTo_ToFrom, ReEDSComponent


def test_fromto_tofrom_creation():
    """Test creating a FromTo_ToFrom instance with valid values."""
    model = FromTo_ToFrom(from_to=100.0, to_from=150.0)
    assert model.from_to == 100.0


def test_fromto_tofrom_to_from_value():
    """Test that to_from value is correctly set."""
    model = FromTo_ToFrom(from_to=100.0, to_from=150.0)
    assert model.to_from == 150.0


def test_fromto_tofrom_negative_from_to_fails():
    """Test that negative from_to value raises validation error."""
    with pytest.raises(ValidationError):
        FromTo_ToFrom(from_to=-10.0, to_from=100.0)


def test_fromto_tofrom_negative_to_from_fails():
    """Test that negative to_from value raises validation error."""
    with pytest.raises(ValidationError):
        FromTo_ToFrom(from_to=100.0, to_from=-10.0)


def test_reeds_component_creation():
    """Test creating a ReEDSComponent with basic fields."""
    component = ReEDSComponent(name="test_component")
    assert component.name == "test_component"


def test_reeds_component_with_category():
    """Test ReEDSComponent with category field."""
    component = ReEDSComponent(name="test", category="technology")
    assert component.category == "technology"


def test_reeds_component_optional_category_defaults_to_none():
    """Test that optional category field defaults to None."""
    component = ReEDSComponent(name="test")
    assert component.category is None


def test_minmax_validation_enforces_min_less_than_max():
    from pydantic import ValidationError

    from r2x_reeds.models.base import MinMax

    with pytest.raises(ValidationError):
        MinMax(min=0.9, max=0.1)
