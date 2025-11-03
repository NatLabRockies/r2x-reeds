"""Plugin to dissaggregate and aggregate generators.

This plugin breaks apart generators that are too big in comparison with the
WECC database. If the generator is too small after the breakup than the capacity
threshold variable, we drop the generator entirely.
"""

# System packages
import re

import numpy as np
import pandas as pd
from infrasys import System
from loguru import logger

from r2x_core.store import DataStore
from r2x_reeds.models.components import ReEDSEmission, ReEDSGenerator

CAPACITY_THRESHOLD = 5


def break_gens(
    system: System,
    folder_path: str | None = None,
    pcm_defaults_fpath: str | None = None,
    pcm_defaults_dict: dict | None = None,
    capacity_threshold: int = CAPACITY_THRESHOLD,
    non_break_techs: list[str] | None = None,
) -> System:
    """Break apart large generators based on average capacity.

    Parameters
    ----------
    system : System
        The system to modify.
    folder_path : str, optional
        Path to the folder containing ReEDS data (used to resolve relative paths).
    pcm_defaults_fpath : str, optional
        Path to PCM defaults file. If not provided, will look for it in the
        folder_path under defaults/pcm_generator_defaults.csv.
    pcm_defaults_dict : dict, optional
        Dictionary of PCM defaults. If provided, takes precedence over pcm_defaults_fpath.
        Should be a dict mapping technology names to dicts with 'avg_capacity_MW' key.
    capacity_threshold : int, default 5
        Minimum capacity threshold for generators (MW).
    non_break_techs : list[str], optional
        List of technology names that should not be broken apart.

    Returns
    -------
    System
        Modified system with broken generators.
    """
    logger.info("Dividing generators into average size generators")

    reference_generators = None

    if pcm_defaults_dict is not None and not pcm_defaults_fpath:
        logger.debug("Using provided pcm_defaults_dict")
        reference_generators = pcm_defaults_dict
        return break_generators(system, reference_generators, capacity_threshold, non_break_techs)

    reference_generators = DataStore.load_file(pcm_defaults_fpath)

    reference_generators = (
        pd.DataFrame.from_dict(reference_generators)
        .transpose()
        .reset_index()
        .rename(columns={"index": "tech"})
        .set_index("tech")
        .replace({np.nan: None})
        .to_dict(orient="index")
    )

    # Default non-break techs if not provided
    if non_break_techs is None:
        non_break_techs = []

    return break_generators(system, reference_generators, capacity_threshold, non_break_techs)


def break_generators(
    system: System,
    reference_generators: dict[str, dict],
    capacity_threshold: int = CAPACITY_THRESHOLD,
    non_break_techs: list[str] | None = None,
    break_category: str = "category",
) -> System:
    """Break component generator into smaller units.

    Parameters
    ----------
    system : System
        The system containing generators to break.
    reference_generators : dict[str, dict]
        Dictionary mapping technology names to their reference data including avg_capacity_MW.
    capacity_threshold : int, default 5
        Minimum capacity threshold (MW). Generators smaller than this are dropped.
    non_break_techs : list[str], optional
        List of technology names that should not be broken apart.
    break_category : str, default "category"
        Attribute name to use for categorizing generators.

    Returns
    -------
    System
        Modified system with broken generators.
    """
    regex_pattern = f"^(?!{'|'.join(non_break_techs)})." if non_break_techs else ".*"

    capacity_dropped = 0
    for component in system.get_components(
        ReEDSGenerator, filter_func=lambda x: re.search(regex_pattern, x.name)
    ):
        if not (tech := getattr(component, break_category, None)):
            logger.trace(f"Skipping component {component.name} with missing category")
            continue

        logger.trace(f"Breaking {component.name}")

        if not (reference_tech := reference_generators.get(tech)):
            logger.trace(f"{tech} not found in reference_generators")
            continue

        if not (avg_capacity := reference_tech.get("avg_capacity_MW", None)):
            continue

        logger.trace(f"Average_capacity: {avg_capacity}")

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
            _create_split_generator(system, component, component_name, avg_capacity, reference_base_power)
            split_no += 1

        if remainder > capacity_threshold:
            component_name = component.name + f"_{split_no:02}"
            _create_split_generator(system, component, component_name, remainder, reference_base_power)
        else:
            capacity_dropped += remainder
            logger.debug(f"Dropped {remainder} capacity for {component.name}")

        system.remove_component(component)

    logger.info(f"Total capacity dropped {capacity_dropped} MW")
    return system


def _create_split_generator(
    system: System, original: ReEDSGenerator, name: str, new_capacity: float, original_capacity: float
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
    original_capacity : float
        Original capacity before splitting (MW).

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

    # Copy supplemental attributes (emissions)
    for attribute in system.get_supplemental_attributes_with_component(original, ReEDSEmission):
        system.add_supplemental_attribute(new_component, attribute)

    # Copy time series if present
    if system.has_time_series(original):
        logger.trace(f"Component {original.name} has time series attached. Copying.")
        ts = system.get_time_series(original)
        system.add_time_series(ts, new_component)

    return new_component
