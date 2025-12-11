from __future__ import annotations

import csv
from pathlib import Path

from r2x_reeds.upgrader.data_upgrader import ReEDSVersionDetector
from r2x_reeds.upgrader.upgrade_steps import move_hmap_file, move_transmission_cost


def test_version_detector_reads_meta(tmp_path: Path) -> None:
    """The version detector reads the fourth column of the second row."""
    meta_path = tmp_path / "meta.csv"
    with open(meta_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["a", "b", "c", "d", "e"])
        writer.writerow(["0", "1", "2", "v1.2", "extra"])

    detector = ReEDSVersionDetector()
    assert detector.read_version(tmp_path) == "v1.2"


def test_version_detector_missing_file(tmp_path: Path) -> None:
    """Missing files return a FileNotFoundError instance."""
    detector = ReEDSVersionDetector()
    result = detector.read_version(tmp_path)
    assert isinstance(result, FileNotFoundError)


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
