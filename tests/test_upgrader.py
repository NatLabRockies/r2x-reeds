import csv

import pytest

from r2x_core import SemanticVersioningStrategy
from r2x_reeds.upgrader.data_upgrader import ReEDSUpgrader
from r2x_reeds.upgrader.helpers import LEGACY_VERSION

pytestmark = [pytest.mark.integration]


@pytest.fixture
def upgraded_system(reeds_run_upgrader, example_reeds_config, caplog):
    from typing import cast

    from r2x_core import DataStore, PluginContext
    from r2x_reeds.parser import ReEDSParser

    store = DataStore.from_plugin_config(example_reeds_config, path=reeds_run_upgrader)

    ctx = PluginContext(config=example_reeds_config, store=store)
    parser = cast(ReEDSParser, ReEDSParser.from_context(ctx))
    result_ctx = parser.run()
    system = result_ctx.system
    assert system is not None
    return system


def test_reeds_upgrader(reeds_run_upgrader):
    upgrader = ReEDSUpgrader(reeds_run_upgrader)

    # Verify upgrader is initialized with folder path and steps
    assert upgrader.path == reeds_run_upgrader
    assert isinstance(upgrader.steps, list)


def test_reeds_upgrader_runs(reeds_run_upgrader):
    upgrader = ReEDSUpgrader(reeds_run_upgrader)

    result = upgrader.upgrade()
    assert result.is_ok()
    assert result.unwrap() == reeds_run_upgrader


def test_upgraded_system(upgraded_system):
    from r2x_core import System

    assert isinstance(upgraded_system, System)


def test_upgrader_uses_semantic_versioning():
    """Verify ReEDSUpgrader uses SemanticVersioningStrategy."""
    assert isinstance(ReEDSUpgrader.version_strategy, SemanticVersioningStrategy)


def test_legacy_dataset_runs_all_upgrades(tmp_path):
    """Legacy datasets (without tag column) get version 0.0.0 and run all upgrades."""
    # Create a legacy meta.csv without the "tag" column
    meta_path = tmp_path / "meta.csv"
    with open(meta_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["computer", "repo", "branch", "commit", "description"])
        writer.writerow(["host", "/path", "main", "abc123", "desc"])

    upgrader = ReEDSUpgrader(tmp_path)
    version = upgrader.version_reader.read_version(tmp_path)
    assert version == LEGACY_VERSION


def test_upgrader_missing_meta_file(tmp_path):
    """Upgrader returns error when meta.csv is missing."""
    upgrader = ReEDSUpgrader(tmp_path)
    result = upgrader.upgrade()
    assert result.is_err()
    assert "not found" in str(result.err())


def test_upgrader_with_explicit_version(tmp_path):
    """Upgrader accepts explicit current_version parameter."""
    # Create minimal meta.csv
    meta_path = tmp_path / "meta.csv"
    with open(meta_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["computer", "repo", "branch", "commit", "description", "tag"])
        writer.writerow(["host", "/path", "main", "abc123", "desc", "2026.01.22"])

    upgrader = ReEDSUpgrader(tmp_path)
    # Pass explicit version that's already up-to-date
    result = upgrader.upgrade(current_version="2026.01.22")
    assert result.is_ok()


def test_upgrader_with_target_version(tmp_path):
    """Upgrader respects target_version parameter."""
    meta_path = tmp_path / "meta.csv"
    with open(meta_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["computer", "repo", "branch", "commit", "description", "tag"])
        writer.writerow(["host", "/path", "main", "abc123", "desc", "0.0.0"])

    upgrader = ReEDSUpgrader(tmp_path)
    # Target version older than upgrade steps should skip them
    result = upgrader.upgrade(current_version="0.0.0", target_version="2025.01.01")
    assert result.is_ok()


def test_upgrader_with_custom_strategy(tmp_path):
    """Upgrader accepts custom version strategy."""
    meta_path = tmp_path / "meta.csv"
    with open(meta_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["computer", "repo", "branch", "commit", "description", "tag"])
        writer.writerow(["host", "/path", "main", "abc123", "desc", "2026.01.22"])

    upgrader = ReEDSUpgrader(tmp_path)
    result = upgrader.upgrade(
        current_version="2026.01.22",
        strategy=SemanticVersioningStrategy(),
    )
    assert result.is_ok()


def test_upgrader_skips_non_file_upgrades(tmp_path):
    """Upgrader skips steps with non-matching upgrade type."""
    from r2x_core import UpgradeType

    meta_path = tmp_path / "meta.csv"
    with open(meta_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["computer", "repo", "branch", "commit", "description", "tag"])
        writer.writerow(["host", "/path", "main", "abc123", "desc", "0.0.0"])

    upgrader = ReEDSUpgrader(tmp_path)
    # Request SYSTEM upgrades when all registered steps are FILE type
    result = upgrader.upgrade(current_version="0.0.0", upgrade_type=UpgradeType.SYSTEM)
    assert result.is_ok()
