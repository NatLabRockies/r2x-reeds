"""Result types for parser operations."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class ComponentBuildResult:
    """Result of building a batch of components."""

    created_count: int
    errors: list[str] = None

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []


@dataclass
class HydroBudgetResult:
    """Hydro budget calculation for a single year."""

    year: int
    budget_array: np.ndarray
