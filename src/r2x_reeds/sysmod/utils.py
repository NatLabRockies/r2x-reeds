"""Utility helpers for sysmods."""

from __future__ import annotations

from collections.abc import Iterable
from os import PathLike
from pathlib import Path
from typing import Any

from loguru import logger
from rust_ok import Err, Ok, Result


def _deduplicate_records(records: Iterable[dict[str, Any]] | None, *, key: str) -> list[dict[str, Any]]:
    """Remove duplicate dictionaries from an iterable while preserving order.

    Parameters
    ----------
    records : Iterable[dict[str, Any]] | None
        Iterable containing dictionary records to deduplicate.
    key : str
        Dictionary key used to determine uniqueness.

    Returns
    -------
    list[dict[str, Any]]
        Deduplicated list of dictionaries.

    Notes
    -----
    - Records missing the provided key are kept but reported.
    - When duplicates are found, the first occurrence wins and a warning is logged.
    """
    if records is None:
        return []

    deduped: list[dict[str, Any]] = []
    seen_keys: set[Any] = set()
    missing_key_count = 0
    duplicates: set[Any] = set()

    for record in records:
        if not isinstance(record, dict):
            logger.warning("Skipping non-dict record during deduplication: {}", record)
            continue

        if key not in record:
            missing_key_count += 1
            deduped.append(record)
            continue

        value = record[key]
        if value in seen_keys:
            duplicates.add(value)
            continue

        seen_keys.add(value)
        deduped.append(record)

    if duplicates:
        joined = ", ".join(sorted(str(value) for value in duplicates))
        logger.warning(
            "Duplicate entries found for key '{}' while loading reference technologies: {}. "
            "Keeping first occurrence.",
            key,
            joined,
        )

    if missing_key_count:
        logger.warning(
            "Deduplication key '{}' missing in {} record(s); those records were kept as-is.",
            key,
            missing_key_count,
        )

    return deduped


def _coerce_path(
    reference_technologies: Path | str | PathLike,
) -> Result[Path, TypeError | FileNotFoundError | IsADirectoryError]:
    """Convert a raw path input into a validated file path."""
    try:
        reference_path = Path(reference_technologies)
    except TypeError:
        msg = (
            "reference_technologies must be either a dict or a valid path-like object, "
            f"got {type(reference_technologies).__name__}"
        )
        return Err(TypeError(msg))

    if not reference_path.exists():
        return Err(FileNotFoundError(f"Reference technologies file not found: {reference_path}"))

    if reference_path.is_dir():
        return Err(
            IsADirectoryError(
                f"Expected a file path for reference technologies, got directory: {reference_path}"
            )
        )

    return Ok(reference_path)
