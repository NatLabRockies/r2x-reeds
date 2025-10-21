"""Augment results from CEM with PCM defaults."""

from pathlib import Path

from infrasys import System
from loguru import logger

from r2x_core.datafile import DataFile
from r2x_core.store import DataStore
from r2x_reeds.config import ReEDSConfig
from r2x_reeds.models.components import ReEDSGenerator
from r2x_reeds.parser import ReEDSParser


# @PluginManager.register_system_update("pcm_defaults")
def update_system(
    config: ReEDSConfig,
    system: System,
    parser: ReEDSParser | None = None,
    pcm_defaults_fpath: str | None = None,
    pcm_defaults_override: bool = False,
) -> System:
    """Augment data model using PCM defaults dictionary.

    Parameters
    ----------
    config : ReEDSConfig
        The ReEDS configuration.
    system : System
        InfraSys system.
    parser : ReEDSParser | None
        The parser object used for parsing.
    pcm_defaults_fpath : str | None
        Path for json file containing the PCM defaults.
    pcm_defaults_override : bool, default False
        Flag to override all the PCM related fields with the JSON values.

    Returns
    -------
    System
        The updated system object.

    Notes
    -----
    The current implementation of this plugin matches the ReEDSGenerator category field.
    """
    logger.info("Augmenting generators attributes with PCM defaults.")

    # Get PCM defaults file path
    if pcm_defaults_fpath is None:
        defaults = config.load_defaults()
        pcm_defaults_fpath = defaults.get("pcm_defaults_fpath")

    if not pcm_defaults_fpath:
        logger.warning("No PCM defaults file path provided. Skipping plugin.")
        return system

    logger.debug("Using PCM defaults from: {}", pcm_defaults_fpath)

    # Read PCM defaults using DataStore
    pcm_path = Path(pcm_defaults_fpath)
    pcm_data_file = DataFile(
        name="pcm_defaults", fpath=pcm_path, description="PCM defaults for generator augmentation"
    )
    data_store = DataStore(folder=pcm_path.parent)
    data_store.add_data_file(pcm_data_file)

    pcm_defaults: dict = data_store.read_data_file(name="pcm_defaults")

    # Fields that need to be multiplied by generator capacity
    needs_multiplication = {"start_cost_per_MW", "ramp_limits"}

    # Fields that should be processed first (for dependency ordering)
    fields_weight = {"capacity": 1}  # Updated from active_power_limits

    # NOTE: Matching names provides the order that we do the mapping for. First
    # we try to find the name of the generator, if not we rely on reeds category
    # and finally if we did not find a match the broader category
    for component in system.get_components(ReEDSGenerator):
        # Try multiple matching strategies
        pcm_values = (
            pcm_defaults.get(component.name)
            or pcm_defaults.get(component.technology)  # Updated from ext.reeds_tech
            or pcm_defaults.get(component.category)
        )

        if not pcm_values:
            msg = "Could not find a matching category for {}. "
            msg += "Skipping generator from pcm_defaults plugin."
            logger.debug(msg, component.name)
            continue

        msg = "Applying PCM defaults to {}"
        logger.debug(msg, component.name)

        if not pcm_defaults_override:
            fields_to_replace = [
                key for key, value in component.model_dump().items() if value is None and key in pcm_values
            ]
        else:
            fields_to_replace = [key for key in pcm_values if key in type(component).model_fields]

        for field in sorted(fields_to_replace, key=lambda x: fields_weight.get(x, -999)):
            value = pcm_values[field]
            if _check_if_null(value):
                continue

            if field in needs_multiplication:
                base_capacity = component.capacity
                if base_capacity is not None:
                    value = _multiply_value(base_capacity, value)
                else:
                    logger.warning("Cannot multiply {} for {} - no capacity defined", field, component.name)
                    continue

            if field == "start_cost_per_MW":
                field = "startup_cost"

            try:
                setattr(component, field, value)
                logger.trace("Set {} = {} for {}", field, value, component.name)
            except Exception as e:
                logger.warning("Failed to set {} for {}: {}", field, component.name, e)

    logger.info("Finished augmenting generators with PCM defaults")
    return system


def _multiply_value(base: float, val):
    """Multiply a value or dictionary of values by a base amount."""
    if isinstance(val, dict):
        return {k: base * v for k, v in val.items()}
    return base * val


def _check_if_null(val):
    """Check if a value should be considered null/empty."""
    if isinstance(val, dict):
        return all(not v for v in val.values())
    return val is None
