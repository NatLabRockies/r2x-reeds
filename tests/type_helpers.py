from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, cast

from infrasys import System


class _HasSolveYear(Protocol):
    solve_year: int | None


def solve_year_key(component: _HasSolveYear) -> int:
    if component.solve_year is None:
        raise AssertionError("Expected component to have a solve year")
    return component.solve_year


def get_time_series(system: System, owner: object, /, **features: object) -> Any:
    """Pass typed time-series feature values through infrasys's string-only annotation."""
    get_series = cast(Callable[..., Any], system.get_time_series)
    return get_series(owner, **features)
