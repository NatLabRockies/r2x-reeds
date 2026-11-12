"""Result types for parser operations."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class ComponentBuildResult:
    """Result of building a batch of components."""

    created_count: int
    errors: list[str] = field(default_factory=list)


@dataclass
class HydroProfileResult:
    """Hydro profile calculation for a single year."""

    year: int
    name: str
    data: np.ndarray
