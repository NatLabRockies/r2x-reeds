from __future__ import annotations

import numpy as np
import pytest

from r2x_reeds import parser_utils


def test_tech_matches_category_with_prefixes() -> None:
    categories = {
        "wind": {"prefixes": ["wnd", "wind-"], "exact": ["wind-ons"]},
    }
    assert parser_utils.tech_matches_category("wnd-abc", "wind", categories) is True
    assert parser_utils.tech_matches_category("solar", "wind", categories) is False


def test_get_technology_category_ok_and_err() -> None:
    categories = {
        "wind": {"prefixes": ["wind"], "exact": []},
        "solar": ["upv", "dupv"],
    }

    result = parser_utils.get_technology_category("wind-ons", categories)
    assert result.unwrap() == "wind"

    err_result = parser_utils.get_technology_category("unknown", categories)
    assert err_result.is_err()
    assert isinstance(err_result.unwrap_err(), KeyError)


def test_monthly_to_hourly_polars() -> None:
    monthly = [10.0] * 12
    hourly = parser_utils.monthly_to_hourly_polars(2024, monthly).unwrap()

    assert isinstance(hourly, np.ndarray)
    assert hourly.size == 366 * 24
    assert hourly[0] == pytest.approx(10.0)

    with pytest.raises(ValueError):
        parser_utils.monthly_to_hourly_polars(2024, [1.0]).unwrap()
