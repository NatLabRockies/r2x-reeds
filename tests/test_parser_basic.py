"""Basic ReEDS parser tests using r2x-core 0.1.1 API.

These tests verify basic parser instantiation and configuration using
a minimal test data set.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

pytestmark = [pytest.mark.integration]

if TYPE_CHECKING:
    pass
