from __future__ import annotations

import csv
from pathlib import Path

import pytest

from r2x_reeds.upgrader.data_upgrader import ReEDSVersionDetector
from r2x_reeds.upgrader.helpers import LEGACY_VERSION
from r2x_reeds.upgrader.upgrade_steps import (
    move_hmap_file,
    move_hmap_myr_file,
    move_transmission_cost,
    upgrade_transmission_cost_format,
)

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


def test_move_hmap_file_skips_when_neither_exists(tmp_path: Path) -> None:
    """Skips when neither old nor new file exists."""
    inputs_case = tmp_path / "inputs_case"
    rep_folder = inputs_case / "rep"
    rep_folder.mkdir(parents=True)

    result = move_hmap_file(tmp_path)
    assert result == tmp_path


def test_move_transmission_cost_skips_missing_files(tmp_path: Path) -> None:
    """Skips files that don't exist without error."""
    inputs_case = tmp_path / "inputs_case"
    inputs_case.mkdir(parents=True)

    # Neither old files exist - should complete without error
    result = move_transmission_cost(tmp_path)
    assert result == tmp_path


@pytest.mark.parametrize(
    ("current_version", "ac_filename", "distance_filename"),
    [
        (
            "2025.12.01",
            "transmission_distance_cost_500kVac.csv",
            "transmission_distance_cost_500kVdc.csv",
        ),
        ("2026.03.24", "transmission_cost_ac.csv", "transmission_distance.csv"),
    ],
)
def test_upgrader_migrates_legacy_transmission_files(
    tmp_path: Path,
    current_version: str,
    ac_filename: str,
    distance_filename: str,
) -> None:
    """Old file names and renamed legacy files both reach the current schema."""
    from r2x_reeds.upgrader.data_upgrader import ReEDSUpgrader

    inputs_case = tmp_path / "inputs_case"
    inputs_case.mkdir(parents=True)
    (inputs_case / ac_filename).write_text("r,rr,length_miles,USD2004perMW\np1,p2,132.46,298752.72\n")
    (inputs_case / distance_filename).write_text("r,rr,length_miles,USD2004perMW\np1,p2,132.46,123589.84\n")

    result = ReEDSUpgrader(tmp_path).upgrade(current_version=current_version)

    assert result.is_ok()
    with (inputs_case / "transmission_cost_ac.csv").open(newline="") as fh:
        assert csv.DictReader(fh).fieldnames == [
            "r",
            "rr",
            "USD2004perMW_forward",
            "USD2004perMW_reverse",
            "tscbin",
            "binwidth_USD2004",
        ]
    with (inputs_case / "transmission_distance.csv").open(newline="") as fh:
        assert csv.DictReader(fh).fieldnames == ["r", "rr", "miles"]


def test_upgrade_transmission_cost_format_converts_and_is_idempotent(tmp_path: Path) -> None:
    """Convert renamed legacy transmission tables to the current schema."""
    inputs_case = tmp_path / "inputs_case"
    inputs_case.mkdir(parents=True)
    ac_path = inputs_case / "transmission_cost_ac.csv"
    ac_path.write_text("r,rr,length_miles,USD2004perMW\np1,p2,132.46,298752.72\n")
    distance_path = inputs_case / "transmission_distance.csv"
    distance_path.write_text("r,rr,length_miles,USD2004perMW\np1,p2,132.46,123589.84\n")

    result = upgrade_transmission_cost_format(tmp_path)

    assert result == tmp_path
    with ac_path.open(newline="") as fh:
        ac_reader = csv.DictReader(fh)
        assert ac_reader.fieldnames == [
            "r",
            "rr",
            "USD2004perMW_forward",
            "USD2004perMW_reverse",
            "tscbin",
            "binwidth_USD2004",
        ]
        assert list(ac_reader) == [
            {
                "r": "p1",
                "rr": "p2",
                "USD2004perMW_forward": "298752.72",
                "USD2004perMW_reverse": "",
                "tscbin": "",
                "binwidth_USD2004": "",
            }
        ]
    with distance_path.open(newline="") as fh:
        distance_reader = csv.DictReader(fh)
        assert distance_reader.fieldnames == ["r", "rr", "miles"]
        assert list(distance_reader) == [{"r": "p1", "rr": "p2", "miles": "132.46"}]

    converted_ac = ac_path.read_text()
    converted_distance = distance_path.read_text()
    upgrade_transmission_cost_format(tmp_path)
    assert ac_path.read_text() == converted_ac
    assert distance_path.read_text() == converted_distance


def test_move_hmap_myr_file_moves_legacy_file(tmp_path: Path) -> None:
    """Legacy hmap_myr.csv should be moved into inputs_case/rep/."""
    inputs_case = tmp_path / "inputs_case"
    rep_folder = inputs_case / "rep"
    rep_folder.mkdir(parents=True)

    old_file = inputs_case / "hmap_myr.csv"
    old_file.write_text("yearhour,h\n1,h1\n")

    result = move_hmap_myr_file(tmp_path)

    assert result == tmp_path
    assert not old_file.exists()
    assert (rep_folder / "hmap_myr.csv").exists()


def _write_hmap_allyrs(rep_folder: Path, rows: list[dict]) -> None:
    """Write a minimal hmap_allyrs.csv fixture for testing."""
    import csv

    path = rep_folder / "hmap_allyrs.csv"
    fieldnames = ["*timestamp", "year", "yearhour", "h", "actual_h"]
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
