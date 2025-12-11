"""Upgrades for ReEDS data."""

from pathlib import Path
from typing import Any

from loguru import logger

from r2x_core.upgrader_utils import UpgradeType
from r2x_reeds.upgrader.helpers import LATEST_COMMIT

from .data_upgrader import ReEDSUpgrader


@ReEDSUpgrader.register_step(target_version=LATEST_COMMIT, upgrade_type=UpgradeType.FILE, priority=30)
def move_hmap_file(folder: Path, upgrader_context: dict[str, Any] | None = None):
    """Move hmap to new folder.

    This upgrade step is idempotent - it safely handles being called multiple times
    by checking if the file has already been moved to its target location.
    """
    old_location = folder / "inputs_case/hmap_allyrs.csv"
    new_location = folder / "inputs_case/rep/hmap_allyrs.csv"

    # Check if the file has already been moved to the new location
    if new_location.exists():
        logger.debug("File {} already exists at target location, skipping move", new_location.name)
        return

    # Check if the file exists at the old location
    if not old_location.exists():
        raise FileNotFoundError(
            f"File {old_location} does not exist and target {new_location} does not exist either."
        )

    # Move the file to its new location
    old_location.rename(new_location)
    logger.debug("Moved {} to {}", old_location.name, new_location)
    return


@ReEDSUpgrader.register_step(target_version=LATEST_COMMIT, upgrade_type=UpgradeType.FILE, priority=30)
def move_transmission_cost(folder: Path, upgrader_context: dict[str, Any] | None = None):
    """Rename the legacy transmission distance/cost files to their new names."""
    rename_map = [
        ("inputs_case/transmission_distance_cost_500kVac.csv", "inputs_case/transmission_cost_ac.csv"),
        ("inputs_case/transmission_distance_cost_500kVdc.csv", "inputs_case/transmission_distance.csv"),
    ]

    for old_rel, new_rel in rename_map:
        old_path = folder / old_rel
        new_path = folder / new_rel

        if new_path.exists():
            logger.debug("Target {} already exists; skipping move", new_path.name)
            continue

        if not old_path.exists():
            logger.debug("Legacy file {} not found; skipping", old_path.name)
            continue

        old_path.rename(new_path)
        logger.debug("Moved legacy transmission file {} to {}", old_path.name, new_path.name)
