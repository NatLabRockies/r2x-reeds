"""Plugin to dissaggregate and aggregate generators.

This plugin breaks apart generators that are to big in conmparisson with the
WECC database. If the generator is to small after the breakup than the capacity
threshold variable, we drop the generator entirely.
"""

# System packages
import re
from pathlib import Path

import numpy as np
import pandas as pd
from infrasys import System
from loguru import logger

from r2x_core.datafile import DataFile
from r2x_core.store import DataStore
from r2x_reeds.config import ReEDSConfig
from r2x_reeds.models.components import ReEDSEmission, ReEDSGenerator
from r2x_reeds.parser import ReEDSParser

CAPACITY_THRESHOLD = 5


# @PluginManager.register_system_update("break_gens")
def update_system(
    config: ReEDSConfig,
    system: System,
    parser: ReEDSParser,
    pcm_defaults_fpath: str | None = None,
    capacity_threshold: int = CAPACITY_THRESHOLD,
) -> System:
    """Break apart large generators based on average capacity."""
    logger.info("Dividing generators into average size generators")

    if pcm_defaults_fpath is None:
        defaults = config.load_defaults()
        pcm_defaults_path = defaults.get("pcm_defaults_fpath")
        if pcm_defaults_path:
            pcm_data_file = DataFile(
                name="pcm_defaults",
                fpath=pcm_defaults_path,
                description="PCM defaults for generator breaking",
            )
            data_store = DataStore(folder=pcm_data_file.fpath.parent)
            data_store.add_data_file(pcm_data_file)

            pcm_defaults = data_store.read_data_file(name="pcm_defaults")
        else:
            logger.warning("No pcm_defaults_fpath found in defaults")
            return system
    else:
        logger.debug("Using custom defaults from {}", pcm_defaults_fpath)
        pcm_path = Path(pcm_defaults_fpath)

        pcm_data_file = DataFile(
            name="pcm_defaults", fpath=pcm_path, description="Custom PCM defaults for generator breaking"
        )
        data_store = DataStore(folder=pcm_path.parent)
        data_store.add_data_file(pcm_data_file)
        pcm_defaults = data_store.read_data_file(name="pcm_defaults")

    reference_generators = (
        pd.DataFrame.from_dict(pcm_defaults)
        .transpose()
        .reset_index()
        .rename(columns={"index": "tech"})
        .set_index("tech")
        .replace({np.nan: None})
        .to_dict(orient="index")
    )

    defaults = config.load_defaults()
    non_break_techs = defaults.get("non_break_techs", [])

    return break_generators(system, reference_generators, capacity_threshold, non_break_techs)


def break_generators(
    system: System,
    reference_generators: dict[str, dict],
    capacity_threshold: int = CAPACITY_THRESHOLD,
    non_break_techs: list[str] | None = None,
    break_category: str = "category",
) -> System:
    """Break component generator into smaller units."""
    regex_pattern = f"^(?!{'|'.join(non_break_techs)})." if non_break_techs else ".*"

    capacity_dropped = 0
    for component in system.get_components(
        ReEDSGenerator, filter_func=lambda x: re.search(regex_pattern, x.name)
    ):
        if not (tech := getattr(component, break_category, None)):
            logger.trace("Skipping component {} with missing category", component.name)
            continue

        logger.trace("Breaking {}", component.name)

        if not (reference_tech := reference_generators.get(tech)):
            logger.trace("{} not found in reference_generators", tech)
            continue

        if not (avg_capacity := reference_tech.get("avg_capacity_MW", None)):
            continue

        logger.trace("Average_capacity: {}", avg_capacity)

        # Updated to use .capacity field directly (float in MW)
        reference_base_power = component.capacity
        no_splits = int(reference_base_power // avg_capacity)
        remainder = reference_base_power % avg_capacity

        if no_splits <= 1:
            continue

        split_no = 1
        logger.trace(
            "Breaking generator {} with capacity {} into {} generators of {} capacity",
            component.name,
            reference_base_power,
            no_splits,
            avg_capacity,
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
            logger.debug("Dropped {} capacity for {}", remainder, component.name)

        system.remove_component(component)

    logger.info("Total capacity dropped {} MW", capacity_dropped)
    return system


def _create_split_generator(
    system: System, original: ReEDSGenerator, name: str, new_capacity: float, original_capacity: float
) -> ReEDSGenerator:
    """Create a new split generator component."""
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

    for attribute in system.get_supplemental_attributes_with_component(original, ReEDSEmission):
        system.add_supplemental_attribute(new_component, attribute)

    if system.has_time_series(original):
        logger.trace("Component {} has time series attached. Copying.", original.name)
        ts = system.get_time_series(original)
        system.add_time_series(ts, new_component)

    return new_component
