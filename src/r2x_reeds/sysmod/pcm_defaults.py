"""Augment results from CEM with PCM defaults."""

from pathlib import Path

from infrasys import System
from loguru import logger

from r2x_core.datafile import DataFile
from r2x_core.store import DataStore
from r2x_reeds.models.components import ReEDSGenerator


def add_pcm_defaults(
    system: System,
    pcm_defaults_fpath: str | None = None,
    pcm_defaults_dict: dict | None = None,
    pcm_defaults_override: bool = False,
) -> System:
    """Augment data model using PCM defaults dictionary.

    Parameters
    ----------
    system : System
        InfraSys system to modify.
    pcm_defaults_fpath : str, optional
        Path for json file containing the PCM defaults.
    pcm_defaults_dict : dict, optional
        Dictionary of PCM defaults. If provided, takes precedence over pcm_defaults_fpath.
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

    # Use pcm_defaults_dict if provided, otherwise load from file
    if pcm_defaults_dict is not None:
        logger.debug("Using provided pcm_defaults_dict")
        pcm_defaults: dict = pcm_defaults_dict
    else:
        if not pcm_defaults_fpath:
            logger.warning("No PCM defaults file path or dict provided. Skipping plugin.")
            return system

        logger.debug("Using PCM defaults from: {}", pcm_defaults_fpath)

        # Read PCM defaults using DataStore
        pcm_path = Path(pcm_defaults_fpath)
        pcm_data_file = DataFile(
            name="pcm_defaults", fpath=pcm_path, description="PCM defaults for generator augmentation"
        )
        data_store = DataStore(path=pcm_path.parent)
        data_store.add_data(pcm_data_file)

        pcm_defaults = data_store.read_data(name="pcm_defaults")

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
            or pcm_defaults.get(component.technology)
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
                key for key in pcm_values if _check_if_null(_get_component_attribute(component, key))
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


def _get_component_attribute(component, attr):
    """Safely retrieve an attribute that may not exist on the component."""
    try:
        return getattr(component, attr)
    except AttributeError:
        return None
