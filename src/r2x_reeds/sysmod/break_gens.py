"""Split oversized generators into multiple reference-sized units."""

from __future__ import annotations

from os import PathLike
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger
from rust_ok import Err, Ok, Result

from r2x_core import DataStore
from r2x_reeds.models import ReEDSGenerator

from .utils import _coerce_path, _deduplicate_records

if TYPE_CHECKING:
    from r2x_core import System


def break_generators(
    system: System,
    reference_technologies: Path | str | PathLike | dict[str, Any],
    drop_capacity_threshold: int = 5,
    skip_categories: list[str] | None = None,
    break_category: str = "category",
) -> None:
    """Public API for breaking generators with fail-fast error handling."""
    match _break_generators_result(
        system=system,
        reference_technologies=reference_technologies,
        drop_capacity_threshold=drop_capacity_threshold,
        skip_categories=skip_categories,
        break_category=break_category,
    ):
        case Ok(_):
            return None
        case Err(error):
            raise error


def _break_generators_result(
    system: System,
    reference_technologies: Path | str | PathLike | dict[str, Any],
    drop_capacity_threshold: int,
    skip_categories: list[str] | None,
    break_category: str,
) -> Result[None, Exception]:
    """Load references, run splitting logic, and propagate errors via Result."""
    if drop_capacity_threshold < 0:
        msg = "drop_capacity_threshold must be non-negative"
        return Err(ValueError(msg))

    match _load_reference_generators(reference_technologies):
        case Ok(reference_generators):
            _break_generators(
                system=system,
                reference_generators=reference_generators,
                capacity_threshold=drop_capacity_threshold,
                skip_categories=skip_categories,
                break_category=break_category,
            )
            return Ok(None)
        case Err(error):
            return Err(error)


def _break_generators(
    system: System,
    reference_generators: dict[str, dict[str, Any]],
    capacity_threshold: float,
    skip_categories: list[str] | None = None,
    break_category: str = "category",
) -> System:
    """Break component generator into smaller units."""
    skip_set: set[str] = {str(value) for value in skip_categories} if skip_categories else set()

    capacity_dropped = 0
    for component in system.get_components(
        ReEDSGenerator, filter_func=lambda comp: getattr(comp, break_category, None)
    ):
        tech_key = str(getattr(component, break_category))

        if skip_set and tech_key in skip_set:
            logger.trace(
                "Skipping component {} because {}={} is in skip list",
                component.name,
                break_category,
                tech_key,
            )
            continue

        logger.trace(f"Breaking {component.name}")

        if not (reference_tech := reference_generators.get(tech_key)):
            logger.trace(f"{tech_key} not found in reference_generators")
            continue

        if not (avg_capacity := reference_tech.get("avg_capacity_MW", None)):
            continue

        # Use .capacity field directly (float in MW)
        reference_base_power = component.capacity
        no_splits = int(reference_base_power // avg_capacity)
        remainder = reference_base_power % avg_capacity

        if no_splits <= 1:
            continue
        split_no = 1
        logger.trace(
            f"Breaking generator {component.name} with capacity {reference_base_power} "
            f"into {no_splits} generators of {avg_capacity} capacity"
        )

        for _ in range(no_splits):
            component_name = component.name + f"_{split_no:02}"
            _create_split_generator(system, component, component_name, avg_capacity)
            split_no += 1

        if remainder > capacity_threshold:
            component_name = component.name + f"_{split_no:02}"
            _create_split_generator(system, component, component_name, remainder)
        else:
            capacity_dropped += remainder
            logger.debug(f"Dropped {remainder} capacity for {component.name}")

        system.remove_component(component)

    logger.debug(f"Total capacity dropped {capacity_dropped} MW")
    return system


def _create_split_generator(
    system: System, original: ReEDSGenerator, name: str, new_capacity: float
) -> ReEDSGenerator:
    """Create a new split generator component.

    Parameters
    ----------
    system : System
        System to add the new generator to.
    original : ReEDSGenerator
        Original generator component to split.
    name : str
        Name for the new split generator.
    new_capacity : float
        Capacity of the new generator (MW).

    Returns
    -------
    ReEDSGenerator
        The newly created split generator component.
    """
    new_component = ReEDSGenerator(
        name=name,
        region=original.region,
        technology=original.technology,
        capacity=new_capacity,
        category=original.category,
        heat_rate=original.heat_rate,
        forced_outage_rate=original.forced_outage_rate,
        planned_outage_rate=original.planned_outage_rate,
        fuel_type=original.fuel_type,
        fuel_price=original.fuel_price,
        vom_cost=original.vom_cost,
        vintage=original.vintage,
    )

    system.add_component(new_component)

    for attribute in system.get_supplemental_attributes_with_component(original):
        logger.trace("Component {} has supplemental attribute {}. Copying.", original.label, attribute.label)
        system.add_supplemental_attribute(new_component, attribute)

    if system.has_time_series(original):
        logger.trace("Component {} has time series attached. Copying.", original.label)
        ts = system.get_time_series(original)
        system.add_time_series(ts, new_component)

    return new_component


def _load_reference_generators(
    reference_technologies: Path | str | PathLike | dict[str, Any], *, dedup_key: str = "name"
) -> Result[dict[str, dict[str, Any]], Exception]:
    """Load reference generator definitions and deduplicate them."""
    if isinstance(reference_technologies, dict):
        return _normalize_reference_data(
            reference_technologies, dedup_key, "<in-memory reference technologies>"
        )

    match _coerce_path(reference_technologies):
        case Ok(path_value):
            try:
                reference_data = DataStore.load_file(path_value)
            except Exception as exc:  # pragma: no cover - propagate load failures
                return Err(exc)
        case Err(error):
            return Err(error)

    return _normalize_reference_data(reference_data, dedup_key, path_value)


def _normalize_reference_data(
    reference_data: Any, dedup_key: str, source: Path | str | PathLike
) -> Result[dict[str, dict[str, Any]], Exception]:
    """Convert raw reference data into a keyed dict with helpful errors."""
    if isinstance(reference_data, dict):
        normalized_input: list[dict[str, Any]] = []
        for key, record in reference_data.items():
            if not isinstance(record, dict):
                logger.warning("Skipping non-dict reference record for key '{}': {}", key, record)
                continue
            normalized_record = dict(record)
            normalized_record.setdefault(dedup_key, key)
            normalized_input.append(normalized_record)
        reference_data = normalized_input

    if isinstance(reference_data, list):
        reference_generators: dict[str, dict[str, Any]] = {}
        for record in _deduplicate_records(reference_data, key=dedup_key):
            if not isinstance(record, dict):
                logger.warning("Skipping non-dict reference record: {}", record)
                continue
            key_value = record.get(dedup_key)
            if key_value is None:
                logger.warning(
                    "Skipping reference record missing key '{}' in {}",
                    dedup_key,
                    source,
                )
                continue
            reference_generators[str(key_value)] = record

        if reference_generators:
            return Ok(reference_generators)

        msg = (
            f"No reference technologies with key '{dedup_key}' were found in {source}. "
            "Ensure the file contains at least one valid entry."
        )
        return Err(ValueError(msg))

    msg = f"reference_technologies must be a dict or JSON array of dicts, got {type(reference_data).__name__}"
    return Err(TypeError(msg))
