from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from loguru import logger

if TYPE_CHECKING:
    from r2x_core import DataStore, System
    from r2x_reeds import ReEDSConfig, ReEDSParser

pytest_plugins = [
    "tests.fixtures.data_fixtures",
    "tests.fixtures.component_fixtures",
]


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


@pytest.fixture
def caplog(caplog):
    from r2x_core.logger import setup_logging

    setup_logging(verbosity=2)
    logger.remove()
    logger.enable("r2x_reeds")
    handler_id = logger.add(caplog.handler, level="TRACE", format="{message}")
    try:
        yield caplog
    finally:
        logger.remove(handler_id)


@pytest.fixture(scope="function")
def empty_file(tmp_path) -> Path:
    empty_fpath = tmp_path / "test.csv"
    empty_fpath.write_text("")
    yield empty_fpath
    empty_fpath.unlink()


@pytest.fixture(scope="session")
def example_system(parser: "ReEDSParser", reeds_config: "ReEDSConfig", data_store: "DataStore") -> "System":
    """Build and return the system (shared fixture for all tests)."""
    from r2x_core import PluginContext

    # Create a fresh context for the build operation
    ctx = PluginContext(config=reeds_config, store=data_store)
    result_ctx = parser.run(ctx=ctx)

    # The system is stored in the context after on_build
    if result_ctx.system is None:
        raise RuntimeError("Failed to build system: system is None in context")
    return result_ctx.system
