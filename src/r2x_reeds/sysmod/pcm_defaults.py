"""Augment results from CEM with PCM defaults."""

import json
from pathlib import Path
from typing import Any

from infrasys import System
from loguru import logger
from pydantic import Field
from rust_ok import Err, Ok, Result

from r2x_core import PluginConfig, expose_plugin
from r2x_reeds.models.components import ReEDSGenerator


class PCMDefaultsConfig(PluginConfig):
    """Configuration for augmenting CEM results with PCM default values."""

    pcm_defaults_fpath: Path | str | None = Field(
        default=None,
        description="Path for JSON file containing PCM defaults.",
    )
    pcm_defaults_dict: dict[str, dict[str, Any]] | None = Field(
        default=None,
        description="Dictionary of PCM defaults to apply.",
    )
    pcm_defaults_override: bool = Field(
        default=False,
        description="Flag to override existing PCM fields with JSON values.",
    )


@expose_plugin
def add_pcm_defaults(
    system: System,
    config: PCMDefaultsConfig,
) -> Result[System, Exception]:
    """Augment data model using PCM defaults dictionary.

    Parameters
    ----------
    system : System
        InfraSys system to modify.
    config : PCMDefaultsConfig
        Configuration for PCM defaults input and override behavior.

    Returns
    -------
    Result[System, Exception]
        The updated system object or the original JSON read or processing error.

    Notes
    -----
    The current implementation of this plugin matches the ReEDSGenerator category field.
    Startup costs remain in dollars per MW through defaults and generator splitting.
    Exporters convert this coefficient using the final generator capacity.
    """
    logger.info("Augmenting generators attributes with PCM defaults.")

    # Use pcm_defaults_dict if provided, otherwise load from file
    if config.pcm_defaults_dict is not None:
        logger.debug("Using provided pcm_defaults_dict")
        pcm_defaults: dict[str, dict[str, Any]] = config.pcm_defaults_dict
    else:
        if not config.pcm_defaults_fpath:
            logger.warning("No PCM defaults file path or dict provided. Skipping plugin.")
            return Ok(system)

        logger.debug("Using PCM defaults from: {}", config.pcm_defaults_fpath)

        try:
            pcm_path = Path(config.pcm_defaults_fpath)
            pcm_defaults = json.loads(pcm_path.read_text(encoding="utf-8"))
            if isinstance(pcm_defaults, list):
                pcm_defaults = {item["name"]: item for item in pcm_defaults}
            if not isinstance(pcm_defaults, dict):
                msg = "PCM defaults JSON must be an object or an array of named objects"
                raise ValueError(msg)
        except (OSError, TypeError, ValueError) as error:
            logger.error("Failed to load PCM defaults: {}", error)
            return Err(error)

    # Fields that need to be multiplied by generator capacity
    needs_multiplication = {"ramp_rate"}

    # Fields that should be processed first (for dependency ordering)
    fields_weight = {"capacity": 1}  # Updated from active_power_limits

    # NOTE: Matching names provides the order that we do the mapping for. First
    # we try to find the name of the generator, if not we rely on reeds category
    # and finally if we did not find a match the broader category
    for component in system.get_components(ReEDSGenerator):
        # Try multiple matching strategies
        pcm_values = pcm_defaults.get(component.name) or pcm_defaults.get(component.technology)
        if pcm_values is None and component.category is not None:
            pcm_values = pcm_defaults.get(component.category)

        if not pcm_values:
            msg = "Could not find a matching category for {}. "
            msg += "Skipping generator from pcm_defaults plugin."
            logger.debug(msg, component.name)
            continue

        msg = "Applying PCM defaults to {}"
        logger.debug(msg, component.name)

        model_fields = type(component).model_fields
        if not config.pcm_defaults_override:
            fields_to_replace = [
                key
                for key in pcm_values
                if key in model_fields and _check_if_null(_get_component_attribute(component, key))
            ]
        else:
            fields_to_replace = [key for key in pcm_values if key in model_fields]

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

            try:
                setattr(component, field, value)
                logger.trace("Set {} = {} for {}", field, value, component.name)
            except Exception as e:
                logger.warning("Failed to set {} for {}: {}", field, component.name, e)

    logger.info("Finished augmenting generators with PCM defaults")
    return Ok(system)


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
