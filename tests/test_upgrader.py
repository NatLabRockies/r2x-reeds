import csv

import pytest

from r2x_core import DataStore, PluginContext, SemanticVersioningStrategy
from r2x_reeds import ReEDSConfig
from r2x_reeds.upgrader.data_upgrader import ReEDSUpgrader, run_reeds_upgrades
from r2x_reeds.upgrader.helpers import LEGACY_VERSION

pytestmark = [pytest.mark.integration]


@pytest.fixture
def upgraded_system(reeds_run_upgrader, example_reeds_config, caplog):

    from r2x_core import DataStore, PluginContext
    from r2x_reeds.parser import ReEDSParser

    store = DataStore.from_plugin_config(example_reeds_config, path=reeds_run_upgrader)

    ctx = PluginContext(config=example_reeds_config, store=store)
    parser = ReEDSParser.from_context(ctx)
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


def test_upgrader_missing_version_value(tmp_path, monkeypatch):
    """Upgrader should fail when version detection returns None."""

    from r2x_reeds.upgrader.data_upgrader import ReEDSVersionDetector

    meta_path = tmp_path / "meta.csv"
    meta_path.write_text("computer,repo,branch,commit,description\nhost,/path,main,abc123,desc\n")

    monkeypatch.setattr(ReEDSVersionDetector, "read_version", lambda self, folder_path: None)

    upgrader = ReEDSUpgrader(tmp_path)
    result = upgrader.upgrade()
    assert result.is_err()
    assert "could not be determined" in str(result.err())


def test_run_reeds_upgrades_missing_meta_file(tmp_path):
    """run_reeds_upgrades should return an error when meta.csv is missing."""
    from types import SimpleNamespace
    from typing import cast

    class _Store:
        folder = tmp_path

    ctx = SimpleNamespace(
        current_version=None, target_version=None, version_strategy=SemanticVersioningStrategy()
    )
    result = run_reeds_upgrades(
        store=cast(DataStore, _Store()),
        ctx=cast(PluginContext[ReEDSConfig], ctx),
    )
    assert result.is_err()
    assert "not found" in str(result.err())


def test_run_reeds_upgrades_missing_version_value(tmp_path, monkeypatch):
    """run_reeds_upgrades should fail when the version reader returns None."""
    from types import SimpleNamespace
    from typing import cast

    from r2x_reeds.upgrader.data_upgrader import ReEDSVersionDetector

    class _Store:
        folder = tmp_path

    ctx = SimpleNamespace(
        current_version=None, target_version=None, version_strategy=SemanticVersioningStrategy()
    )
    monkeypatch.setattr(ReEDSVersionDetector, "read_version", lambda self, folder_path: None)

    result = run_reeds_upgrades(
        store=cast(DataStore, _Store()),
        ctx=cast(PluginContext[ReEDSConfig], ctx),
    )
    assert result.is_err()
    assert "could not be determined" in str(result.err())


def test_run_reeds_upgrades_propagates_upgrade_error(tmp_path, monkeypatch):
    """run_reeds_upgrades should surface upgrade failures from ReEDSUpgrader.upgrade."""
    from types import SimpleNamespace
    from typing import cast

    from rust_ok import Err

    class _Store:
        folder = tmp_path

    ctx = SimpleNamespace(
        current_version="2026.01.22", target_version=None, version_strategy=SemanticVersioningStrategy()
    )
    monkeypatch.setattr(ReEDSUpgrader, "upgrade", lambda self, **kwargs: Err("boom"))

    result = run_reeds_upgrades(
        store=cast(DataStore, _Store()),
        ctx=cast(PluginContext[ReEDSConfig], ctx),
    )
    assert result.is_err()
    assert "boom" in str(result.err())


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


def test_upgrader_runs_upgrade_steps(tmp_path):
    """Test that upgrade steps are actually executed when version is old."""
    # Create meta.csv with legacy version
    meta_path = tmp_path / "meta.csv"
    with open(meta_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["computer", "repo", "branch", "commit", "description", "tag"])
        writer.writerow(["host", "/path", "main", "abc123", "desc", "0.0.0"])

    # Create the files needed for the upgrade steps
    inputs_case = tmp_path / "inputs_case"
    rep_folder = inputs_case / "rep"
    rep_folder.mkdir(parents=True)

    # Create the file that move_hmap_file will move
    hmap_file = inputs_case / "hmap_allyrs.csv"
    hmap_file.write_text("test content")

    # Run upgrade with legacy version
    upgrader = ReEDSUpgrader(tmp_path)
    result = upgrader.upgrade(current_version="0.0.0")

    assert result.is_ok()
    # Verify the file was moved
    assert not hmap_file.exists()
    assert (rep_folder / "hmap_allyrs.csv").exists()


def test_upgrader_handles_failing_step(tmp_path):
    """Test that upgrader completes when hmap_allyrs is missing in both locations."""

    # Create meta.csv with legacy version
    meta_path = tmp_path / "meta.csv"
    with open(meta_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["computer", "repo", "branch", "commit", "description", "tag"])
        writer.writerow(["host", "/path", "main", "abc123", "desc", "0.0.0"])

    # Create the files needed for the upgrade steps
    inputs_case = tmp_path / "inputs_case"
    rep_folder = inputs_case / "rep"
    rep_folder.mkdir(parents=True)

    # Don't create hmap_allyrs.csv so the step will fail
    # (move_hmap_file now warns and skips when neither old nor new exists)

    upgrader = ReEDSUpgrader(tmp_path)
    result = upgrader.upgrade(current_version="0.0.0")

    # The upgrade should succeed because missing hmap_allyrs is handled as a warning/skip
    assert result.is_ok()


def test_run_reeds_upgrades_reads_version_when_missing(tmp_path, monkeypatch):
    """run_reeds_upgrades should populate ctx.current_version from meta.csv when absent."""

    from types import SimpleNamespace
    from typing import cast

    meta_path = tmp_path / "meta.csv"
    with open(meta_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["computer", "repo", "branch", "commit", "description", "tag"])
        writer.writerow(["host", "/path", "main", "abc123", "desc", "2026.01.22"])

    class _Store:
        folder = tmp_path

    ctx = SimpleNamespace(
        current_version=None, target_version=None, version_strategy=SemanticVersioningStrategy()
    )

    def _fake_upgrade(self, **kwargs):
        return self.version_reader.read_version(self.path) and __import__("rust_ok").Ok(tmp_path)

    monkeypatch.setattr(ReEDSUpgrader, "upgrade", _fake_upgrade)

    result = run_reeds_upgrades(
        store=cast(DataStore, _Store()),
        ctx=cast(PluginContext[ReEDSConfig], ctx),
    )
    assert result.is_ok()
    assert ctx.current_version == "2026.01.22"
