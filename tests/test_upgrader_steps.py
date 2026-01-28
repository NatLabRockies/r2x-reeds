from __future__ import annotations

import csv
from pathlib import Path

import pytest

from r2x_reeds.upgrader.data_upgrader import ReEDSVersionDetector
from r2x_reeds.upgrader.helpers import LEGACY_VERSION
from r2x_reeds.upgrader.upgrade_steps import move_hmap_file, move_transmission_cost

pytestmark = [pytest.mark.integration]


def test_version_detector_reads_tag_by_header(tmp_path: Path) -> None:
    """The version detector reads the tag column by header name."""
    meta_path = tmp_path / "meta.csv"
    with open(meta_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["computer", "repo", "branch", "commit", "description", "tag"])
        writer.writerow(["host", "/path", "main", "abc123", "desc", "2026.01.22"])

    detector = ReEDSVersionDetector()
    assert detector.read_version(tmp_path) == "2026.01.22"


def test_version_detector_legacy_format_returns_sentinel(tmp_path: Path) -> None:
    """Legacy format without tag header returns LEGACY_VERSION."""
    meta_path = tmp_path / "meta.csv"
    with open(meta_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["computer", "repo", "branch", "commit", "description"])
        writer.writerow(["host", "/path", "main", "abc123", "desc"])

    detector = ReEDSVersionDetector()
    assert detector.read_version(tmp_path) == LEGACY_VERSION


def test_version_detector_empty_tag_returns_sentinel(tmp_path: Path) -> None:
    """Empty tag value returns LEGACY_VERSION."""
    meta_path = tmp_path / "meta.csv"
    with open(meta_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["computer", "repo", "branch", "commit", "description", "tag"])
        writer.writerow(["host", "/path", "main", "abc123", "desc", ""])

    detector = ReEDSVersionDetector()
    assert detector.read_version(tmp_path) == LEGACY_VERSION


def test_version_detector_tag_column_any_position(tmp_path: Path) -> None:
    """Tag column works regardless of position in header."""
    meta_path = tmp_path / "meta.csv"
    with open(meta_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        # Put tag column in different position (index 2)
        writer.writerow(["computer", "repo", "tag", "branch", "commit", "description"])
        writer.writerow(["host", "/path", "2025.12.01", "main", "abc123", "desc"])

    detector = ReEDSVersionDetector()
    assert detector.read_version(tmp_path) == "2025.12.01"


def test_version_detector_missing_file(tmp_path: Path) -> None:
    """Missing files raise FileNotFoundError."""
    detector = ReEDSVersionDetector()
    with pytest.raises(FileNotFoundError):
        detector.read_version(tmp_path)


def test_move_hmap_file_moves_and_skips(tmp_path: Path) -> None:
    """Upgrade step moves the file once and skips when already moved."""
    inputs_case = tmp_path / "inputs_case"
    rep_folder = inputs_case / "rep"
    rep_folder.mkdir(parents=True)
    old_file = inputs_case / "hmap_allyrs.csv"
    old_file.write_text("content")

    move_hmap_file(tmp_path)
    assert not old_file.exists()
    assert (rep_folder / "hmap_allyrs.csv").read_text() == "content"

    # Running again should be a no-op now that target exists
    move_hmap_file(tmp_path)
    assert (rep_folder / "hmap_allyrs.csv").exists()


def test_move_transmission_cost_moves_and_skips(tmp_path: Path) -> None:
    """Legacy transmission files should be renamed once."""
    inputs_case = tmp_path / "inputs_case"
    inputs_case.mkdir(parents=True)

    ac_old = inputs_case / "transmission_distance_cost_500kVac.csv"
    ac_old.write_text("ac")
    dc_old = inputs_case / "transmission_distance_cost_500kVdc.csv"
    dc_old.write_text("dc")

    move_transmission_cost(tmp_path)
    assert not ac_old.exists()
    assert not dc_old.exists()
    assert (inputs_case / "transmission_cost_ac.csv").read_text() == "ac"
    assert (inputs_case / "transmission_distance.csv").read_text() == "dc"

    # Running again is a no-op now that targets exist
    move_transmission_cost(tmp_path)
    assert (inputs_case / "transmission_cost_ac.csv").exists()
    assert (inputs_case / "transmission_distance.csv").exists()
