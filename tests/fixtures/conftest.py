"""Pytest configuration for fixtures plugin."""

from pathlib import Path

import pytest


def pytest_addoption(parser):
    """Add custom pytest command line options."""
    parser.addoption(
        "--reeds-data-path",
        action="store",
        default=None,
        help="Path to ReEDS run data (overrides default test data)",
    )


@pytest.fixture(scope="session")
def reeds_data_path_override(request) -> Path | None:
    """Return override path from command line if provided."""
    path_str = request.config.getoption("--reeds-data-path")
    if path_str:
        path = Path(path_str)
        if not path.exists():
            pytest.fail(f"Provided --reeds-data-path does not exist: {path}")
        return path
    return None
