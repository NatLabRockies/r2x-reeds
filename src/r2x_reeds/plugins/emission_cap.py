"""Plugin to add annual carbon cap to the model.

This plugin is only applicable for ReEDs, but could work with similarly arrange data
"""

import polars as pl
from infrasys import System
from loguru import logger

from r2x_reeds.config import ReEDSConfig
from r2x_reeds.models.components import ReEDSEmission, ReEDSGenerator
from r2x_reeds.models.enums import EmissionType
from r2x_reeds.parser import ReEDSParser


# @PluginManager.register_system_update("emission_cap")
def update_system(
    config: ReEDSConfig,
    system: System,
    parser: ReEDSParser | None = None,
    emission_cap: float | None = None,
    default_unit: str = "tonne",
) -> System:
    """Apply an emission cap constraint for the system.

    This function adds to the system a constraint object that is used to set the maximum
    emission per year.

    Parameters
    ----------
    config : ReEDSConfig
        The ReEDS configuration.
    system : System
        The system object to be updated.
    parser : ReEDSParser | None
        The parser object used for parsing.
    emission_cap : float | None, optional
        The emission cap value. If None, no cap is applied. Default is None.
    default_unit : str, optional
        The default unit for measurement. Default is 'tonne'.

    Returns
    -------
    System
        The updated system object.

    Notes
    -----
    When summarizing emissions from either fuels or generators, the metric model
    defines one unit in summary (day, week, month, year) as 1000 of the base units,
    whereas the imperial U.S. model uses 2000 units. Thus, if you define a
    constraint on total emissions over a day, week, month, or year, you must
    enter the limit in the appropriate unit. For example, if the production rate
    is in lb/MWh, then an annual constraint would be in short tons, where one
    short ton equals 2000 lbs. For units in kg/MWh and `emission_cap` in metric tons,
    we multiply by 1000 (`Scalar` property in Plexos).
    """
    logger.info("Adding emission cap...")

    if emission_cap is not None:
        logger.debug("Using emission cap value from CLI. Setting emission cap to {}", emission_cap)

    emission_object = EmissionType.CO2  # This is the default emission object.
    if not any(
        component.emission_type == emission_object
        for component in system.get_supplemental_attributes(ReEDSEmission)
    ):
        logger.warning("Did not find any emission type to apply emission_cap")
        return system

    # Check if we have ReEDS parser data
    if parser is not None:
        parser_data = getattr(parser, "data", {})

        # Check for required data files
        if "switches" not in parser_data:
            logger.warning("Missing switches file from run folder.")
            return system

        if "emission_rates" not in parser_data:
            logger.warning("Missing emission rates.")
            return system

        switches_data = parser_data["switches"]
        emit_rates = parser_data["emission_rates"]

        # Convert switches to dictionary format
        if hasattr(switches_data, "iter_rows"):
            switches = {key: str(value) for key, value in switches_data.iter_rows()}
        else:
            switches = switches_data

        # Process emission rates for precombustion
        emit_rates = emit_rates.with_columns(
            pl.concat_str([pl.col("tech"), pl.col("tech_vintage"), pl.col("region")], separator="_").alias(
                "generator_name"
            )
        )
        any_precombustion = emit_rates["emission_source"].str.contains("precombustion")
        emit_rates = emit_rates.filter(any_precombustion)

        if switches.get("gsw_precombustion") and not emit_rates.is_empty():
            logger.debug("Adding precombustion emission.")
            generator_with_precombustion = emit_rates.select(
                "generator_name", "emission_type", "rate"
            ).unique()
            add_precombustion(system, generator_with_precombustion)

        # Determine emission cap from ReEDS data if not provided
        if emission_cap is None:
            emission_object = EmissionType.CO2E if switches.get("gsw_annualcapco2e") else EmissionType.CO2

            if "co2_cap" in parser_data and parser_data["co2_cap"] is not None:
                emission_cap = parser_data["co2_cap"]["value"].item()
            else:
                logger.warning("co2_cap not found from ReEDS parser")
                return system

    return set_emission_constraint(system, emission_cap, default_unit, emission_object)


def add_precombustion(system: System, emission_rates: pl.DataFrame) -> bool:
    """Add precombustion emission rates to `ReEDSEmission` objects.

    This function adds precombustion rates to the attributes ReEDSEmission.

    Parameters
    ----------
    system : System
        The system object to be updated.
    emission_rates : pl.DataFrame
        The precombustion emission_rates

    Returns
    -------
    bool
        True if the addition succeeded. False if it failed

    Raises
    ------
    ValueError
        If multiple emission_rates of the same type are attached to the component
    """
    applied_rate = False
    for generator_name, emission_type, rate in emission_rates.iter_rows():
        # Convert string to EmissionType enum
        try:
            if isinstance(emission_type, str):
                emission_type = EmissionType(emission_type.upper())
            else:
                emission_type = EmissionType(emission_type)
        except ValueError:
            logger.warning(f"Unknown emission type: {emission_type}")
            continue

        try:
            component = system.get_component(ReEDSGenerator, generator_name)
        except Exception:
            logger.trace("Generator {} not found in system", generator_name)
            continue

        # Get emission attributes for this component
        attr = system.get_supplemental_attributes_with_component(
            component, ReEDSEmission, filter_func=lambda attr, et=emission_type: attr.emission_type == et
        )

        if not attr:
            logger.trace("`ReEDSEmission:{}` object not found for {}", emission_type, generator_name)
            continue

        if len(attr) != 1:
            msg = f"Multiple emission of the same type attached to {generator_name}. "
            msg += "Check addition of supplemental attributes."
            raise ValueError(msg)

        attr = attr[0]
        attr.rate += rate
        applied_rate = True

    return applied_rate


def set_emission_constraint(
    system: System,
    emission_cap: float | None = None,
    default_unit: str = "tonne",
    emission_object: EmissionType | None = None,
) -> System:
    """Add emissions constraint object to the system."""
    if emission_cap is None:
        logger.warning("Could not set emission cap value. Skipping plugin.")
        return system

    if "emission_constraints" not in system.ext:
        system.ext["emission_constraints"] = {}

    constraint_name = f"Annual_{emission_object}_cap"

    constraint_properties = {
        "sense": "<=",
        "rhs_value": emission_cap,
        "units": default_unit,
        "penalty_price": 500,
        "emission_type": emission_object,
        "coefficient": 1.0,
        "scalar": 1000,
    }

    system.ext["emission_constraints"][constraint_name] = constraint_properties

    logger.info(
        "Added emission constraint '{}' with cap {} {} for {}",
        constraint_name,
        emission_cap,
        default_unit,
        emission_object,
    )

    return system
