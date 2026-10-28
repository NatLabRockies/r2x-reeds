"""Upgrades for ReEDS data."""

import csv
import os
import stat
import tempfile
from pathlib import Path
from typing import Any

import h5py
import numpy as np
from loguru import logger

from r2x_core import UpgradeStep, UpgradeType


def move_hmap_file(folder: Path, upgrader_context: dict[str, Any] | None = None) -> Path:
    """Move hmap to new folder.

    This upgrade step is idempotent - it safely handles being called multiple times
    by checking if the file has already been moved to its target location.
    """
    old_location = folder / "inputs_case/hmap_allyrs.csv"
    new_location = folder / "inputs_case/rep/hmap_allyrs.csv"

    if new_location.exists():
        logger.debug("File {} already exists at target location, skipping move", new_location.name)
        return folder

    if not old_location.exists():
        logger.warning(
            "hmap_allyrs.csv not found at {} or {}. "
            "Skipping file move; parser will use an in-memory fallback hour_map for translation.",
            old_location,
            new_location,
        )
        return folder

    new_location.parent.mkdir(parents=True, exist_ok=True)
    old_location.rename(new_location)
    logger.debug("Moved {} to {}", old_location.name, new_location)
    return folder


def move_transmission_cost(folder: Path, upgrader_context: dict[str, Any] | None = None) -> Path:
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
    return folder


def _rewrite_transmission_csv(path: Path, column_mapping: dict[str, str | None]) -> None:
    """Rewrite a legacy transmission CSV with the specified current columns."""
    if not path.exists():
        logger.debug("Transmission file {} not found; skipping conversion", path.name)
        return

    fieldnames = list(column_mapping)
    with path.open(newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        source_fields = reader.fieldnames
        if source_fields is None:
            raise ValueError(f"Cannot upgrade transmission file {path}: CSV header is missing")
        if set(fieldnames).issubset(source_fields):
            logger.debug("Transmission file {} already has the current columns", path.name)
            return

        resolved_sources = {}
        for target, source in column_mapping.items():
            if source is None:
                resolved_sources[target] = next(
                    (candidate for candidate in (target, f"*{target}") if candidate in source_fields),
                    None,
                )
                continue
            candidates = (source, f"*{source}", target, f"*{target}")
            resolved_sources[target] = next(
                (candidate for candidate in candidates if candidate in source_fields),
                source,
            )
        required_fields = {source for source in resolved_sources.values() if source is not None}
        missing_fields = required_fields.difference(source_fields)
        if missing_fields:
            missing = ", ".join(sorted(missing_fields))
            raise ValueError(f"Cannot upgrade transmission file {path}: missing legacy column(s): {missing}")

        rows = [
            {target: row[source] if source is not None else "" for target, source in resolved_sources.items()}
            for row in reader
        ]

    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            newline="",
            encoding="utf-8",
            dir=path.parent,
            delete=False,
        ) as destination:
            temporary_path = Path(destination.name)
            writer = csv.DictWriter(destination, fieldnames=fieldnames, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)

        os.chmod(temporary_path, stat.S_IMODE(path.stat().st_mode))
        temporary_path.replace(path)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise

    logger.debug("Converted legacy transmission file {} to current columns", path.name)


def upgrade_transmission_cost_format(folder: Path, upgrader_context: dict[str, Any] | None = None) -> Path:
    """Convert renamed legacy transmission inputs to the current CSV schemas.

    Legacy AC costs become forward costs. The new reverse-cost and cost-bin fields
    have no legacy equivalents and are left empty. The DC table contributes only
    distances to the current shared transmission-distance table.
    """
    inputs_case = folder / "inputs_case"
    _rewrite_transmission_csv(
        inputs_case / "transmission_cost_ac.csv",
        {
            "r": "r",
            "rr": "rr",
            "USD2004perMW_forward": "USD2004perMW",
            "USD2004perMW_reverse": None,
            "tscbin": None,
            "binwidth_USD2004": None,
        },
    )
    _rewrite_transmission_csv(
        inputs_case / "transmission_distance.csv",
        {"r": "r", "rr": "rr", "miles": "length_miles"},
    )
    return folder


def upgrade_unitspec_upgrades_hdf5(
    folder: Path,
    upgrader_context: dict[str, Any] | None = None,
) -> Path:
    """Move the legacy unit-specific upgrade set into the current HDF5 bundle."""
    inputs_case = folder / "inputs_case"
    csv_path = inputs_case / "unitspec_upgrades.csv"
    h5_path = inputs_case / "inputs.h5"
    group_name = "unitspec_upgrades"

    if h5_path.exists():
        with h5py.File(h5_path, mode="r") as bundle:
            if group_name in bundle:
                group = bundle[group_name]
                if "columns" in group and "i" in group:
                    logger.debug("{} already exists in {}, skipping conversion", group_name, h5_path.name)
                    return folder
                raise ValueError(f"Existing {group_name} group in {h5_path} is missing required datasets")

    if not csv_path.exists():
        logger.debug("Legacy {} not found; skipping conversion", csv_path.name)
        return folder

    with csv_path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.reader(source)
        header = next(reader, None)
        if (
            header is None
            or len(header) != 1
            or header[0].strip().lstrip("*").lower() not in {"i", "technology"}
        ):
            raise ValueError(f"Cannot upgrade {csv_path}: expected a single '*i' technology column")
        technologies = []
        for row in reader:
            if len(row) != 1:
                raise ValueError(f"Cannot upgrade {csv_path}: expected one value per row")
            technology = row[0].strip()
            if technology:
                technologies.append(technology)

    string_dtype = h5py.string_dtype(encoding="utf-8")
    with h5py.File(h5_path, mode="a") as bundle:
        if group_name in bundle:
            group = bundle[group_name]
            if "columns" in group and "i" in group:
                logger.debug("{} already exists in {}, skipping conversion", group_name, h5_path.name)
                return folder
            raise ValueError(f"Existing {group_name} group in {h5_path} is missing required datasets")

        group = bundle.create_group(group_name)
        group.create_dataset("columns", data=np.asarray(["i"], dtype=string_dtype))
        group.create_dataset("i", data=np.asarray(technologies, dtype=string_dtype))

    logger.info("Converted {} to {}/{}", csv_path.name, h5_path.name, group_name)
    return folder


def move_hmap_myr_file(folder: Path, upgrader_context: dict[str, Any] | None = None) -> Path:
    """Move hmap_myr.csv from inputs_case/ to inputs_case/rep/ if present at the old location.

    ReEDS runs prior to 2026-03-28 placed hmap_myr.csv directly under inputs_case/.
    Newer runs expect it at inputs_case/rep/hmap_myr.csv.
    This step is idempotent: it skips when the target already exists.

    Notes
    -----
    hmap_myr.csv maps every sequential year-hour (1-8760) to its representative
    period key and is an output of the ReEDS representative-period selection process.
    It cannot be derived from hmap_allyrs.csv — that file only populates the ``h``
    column for the representative hours themselves, leaving all other rows blank.
    Runs that lack hmap_myr.csv entirely will silently skip loadsite demand expansion.
    """
    old_location = folder / "inputs_case/hmap_myr.csv"
    new_location = folder / "inputs_case/rep/hmap_myr.csv"

    if new_location.exists():
        logger.debug("hmap_myr.csv already at target location {}, skipping move", new_location)
        return folder

    if not old_location.exists():
        logger.debug("hmap_myr.csv not found at legacy location {}; skipping", old_location)
        return folder

    new_location.parent.mkdir(parents=True, exist_ok=True)
    old_location.rename(new_location)
    logger.debug("Moved legacy hmap_myr.csv from {} to {}", old_location, new_location)
    return folder


UPGRADE_STEPS = [
    UpgradeStep(
        name="move_hmap_file",
        func=move_hmap_file,
        target_version="2026.01.22",
        upgrade_type=UpgradeType.FILE,
        priority=30,
    ),
    UpgradeStep(
        name="move_transmission_cost",
        func=move_transmission_cost,
        target_version="2026.01.22",
        upgrade_type=UpgradeType.FILE,
        priority=30,
    ),
    UpgradeStep(
        name="upgrade_transmission_cost_format",
        func=upgrade_transmission_cost_format,
        target_version="2026.10.04",
        upgrade_type=UpgradeType.FILE,
        priority=31,
    ),
    UpgradeStep(
        name="upgrade_unitspec_upgrades_hdf5",
        func=upgrade_unitspec_upgrades_hdf5,
        target_version="2026.10.04",
        upgrade_type=UpgradeType.FILE,
        priority=32,
    ),
    UpgradeStep(
        name="move_hmap_myr_file",
        func=move_hmap_myr_file,
        target_version="2026.03.24",
        upgrade_type=UpgradeType.FILE,
        priority=35,
    ),
]
