"""Split oversized generators into multiple reference-sized units."""

from __future__ import annotations

import json
from importlib.resources import files
from os import PathLike
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger
from pydantic import Field
from rust_ok import Err, Ok, Result

from r2x_core import DataStore, PluginConfig, expose_plugin
from r2x_reeds.models import ReEDSGenerator

from .utils import _coerce_path, _deduplicate_records

if TYPE_CHECKING:
    from r2x_core import System


class BreakGensConfig(PluginConfig):
    reference_units: Path | str | PathLike | dict[str, Any] | None = Field(
        default=None,
        description="Reference unit definitions as a path or mapping.",
    )
    drop_capacity_threshold: int = Field(
        default=5, ge=0, description="Threshold of capacity in MW to drop of remainder exist."
    )
    skip_categories: list[str] | None = Field(
        default=None,
        description="Generator categories to skip when breaking units.",
    )
    break_category: str = Field(
        default="category",
        description="Field name used to look up reference units.",
    )


@expose_plugin
def break_generators(
    system: System,
    config: BreakGensConfig,
) -> Result[System, str]:
    """Split oversized generators into multiple reference-sized units."""
    reference_result = _load_reference_units(config.reference_units)
    if reference_result.is_err():
        error = reference_result.unwrap_err()
        logger.error("Failed to load reference units: {}", error)
        return Err(str(error) if error else "Failed to load reference units")

    system = _break_system_generators(
        system=system,
        reference_units=reference_result.unwrap(),
        capacity_threshold=config.drop_capacity_threshold,
        skip_categories=config.skip_categories,
        break_category=config.break_category,
    )

    return Ok(system)


def _break_system_generators(
    system: System,
    reference_units: dict[str, dict[str, Any]],
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
        logger.trace("Extracted technology key: {}", tech_key)

        if skip_set and tech_key in skip_set:
            logger.trace(
                "Skipping component {} because {}={} is in skip list",
                component.name,
                break_category,
                tech_key,
            )
            continue

        logger.trace(f"Breaking {component.name}")

        if not (reference_tech := reference_units.get(tech_key)):
            logger.trace(f"{tech_key} not found in reference_units")
            continue

        if not (capacity := reference_tech.get("capacity_MW", None)):
            logger.warning("`capacity_MW` not found on reference_tech for {}.", tech_key)
            logger.info("`capacity_MW` not found on reference_tech")
            continue

        # Use `.capacity` field directly (float in MW)
        reference_base_power = component.capacity
        no_splits = int(reference_base_power // capacity)
        remainder = reference_base_power % capacity

        if no_splits <= 1:
            logger.trace("Number of splits <= 1. Skipping.")
            continue

        split_no = 1
        logger.trace(
            f"Breaking generator {component.name} with capacity {reference_base_power} "
            f"into {no_splits} generators of {capacity} capacity"
        )

        for _ in range(no_splits):
            component_name = component.name + f"_{split_no:02}"
            _create_split_generator(system, component, component_name, capacity)
            split_no += 1

        if remainder > capacity_threshold:
            component_name = component.name + f"_{split_no:02}"
            _create_split_generator(system, component, component_name, remainder)
        else:
            capacity_dropped += remainder
            logger.debug(f"Dropped {remainder} capacity for {component.name}")

        system.remove_component(component)
    else:
        logger.info("No generator found that match the category. Skipping plugin.")

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
    logger.trace("Creating split generator {} with capacity {}", name, new_capacity)
    component = type(original)(
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
    logger.trace("Created new generator {} with capacity {}", component.label, new_capacity)
    system.add_component(component)

    for attribute in system.get_supplemental_attributes_with_component(original):
        logger.trace("Component {} has supplemental attribute {}. Copying.", original.label, attribute.label)
        system.add_supplemental_attribute(component, attribute)

    if system.has_time_series(original):
        logger.trace("Component {} has time series attached. Copying.", original.label)
        ts = system.get_time_series(original)
        system.add_time_series(ts, component)

    return component


def _load_reference_units(
    reference_units: Path | str | PathLike | dict[str, Any] | None, *, dedup_key: str = "name"
) -> Result[dict[str, dict[str, Any]], Exception]:
    """Load reference generator definitions and deduplicate them."""
    if reference_units is None:
        logger.info("No reference_units provided. Using package defaults from pcm_defaults.json")
        fpath = Path(str(files("r2x_reeds").joinpath("config/pcm_defaults.json")))

        try:
            reference_units = json.loads(fpath.read_text())
        except Exception as exc:
            return Err(exc)
        return _normalize_reference_data(reference_units, dedup_key, fpath)

    if isinstance(reference_units, dict):
        return _normalize_reference_data(reference_units, dedup_key, "<in-memory reference technologies>")

    reference_data: Any = None
    path_value: Path | None = None

    match _coerce_path(reference_units):
        case Ok(path_value_result):
            path_value = path_value_result
            try:
                reference_data = DataStore.load_file(path_value)
            except Exception as exc:  # pragma: no cover - propagate load failures
                return Err(exc)
        case Err(error):
            if error is None:
                return Err(RuntimeError("Failed to load reference units"))
            return Err(error)

    if path_value is None:
        return Err(RuntimeError("Failed to load reference units"))

    if not isinstance(reference_data, (list, dict)):
        return Err(TypeError("reference_technologies must be a dict or JSON array of dicts"))

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
        reference_units: dict[str, dict[str, Any]] = {}
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
            reference_units[str(key_value)] = record

        if reference_units:
            return Ok(reference_units)

        msg = (
            f"No reference technologies with key '{dedup_key}' were found in {source}. "
            "Ensure the file contains at least one valid entry."
        )
        return Err(ValueError(msg))

    msg = f"reference_technologies must be a dict or JSON array of dicts, got {type(reference_data).__name__}"
    return Err(TypeError(msg))
