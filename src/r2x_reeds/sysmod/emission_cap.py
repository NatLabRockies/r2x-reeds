"""Plugin to add annual carbon cap to the model.

This plugin is only applicable for ReEDS, but could work with similarly arranged data
"""

import polars as pl
from infrasys import System
from loguru import logger

from r2x_core import DataStore
from r2x_reeds.models.components import ReEDSEmission, ReEDSGenerator
from r2x_reeds.models.enums import EmissionType


def add_emission_cap(
    system: System,
    emission_cap: float | None = None,
    switches_fpath: str | None = None,
    emission_rates_fpath: str | None = None,
    co2_cap_fpath: str | None = None,
    default_unit: str = "tonne",
    **kwargs,
) -> System:
    """Apply an emission cap constraint for the system.

    This function adds to the system a constraint object that is used to set the maximum
    emission per year.

    Parameters
    ----------
    system : System
        The system object to be updated (from stdin).
    emission_cap : float, optional
        The emission cap value. If None, will attempt to load from co2_cap file.
        Default is None.
    switches_fpath : str, optional
        Path to CSV file containing switches/configuration data with columns:
        switch_name, value.
    emission_rates_fpath : str, optional
        Path to CSV file containing emission rates with columns:
        tech, tech_vintage, region, emission_source, emission_type, rate.
    co2_cap_fpath : str, optional
        Path to CSV file containing CO2 cap value with columns: value.
    default_unit : str, optional
        The default unit for measurement. Default is 'tonne'.
    **kwargs
        Additional keyword arguments (ignored).

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

    emission_object = EmissionType.CO2  # This is the default emission object.

    # Check if we have CO2 emission type in the system
    if not any(
        component.type == emission_object for component in system.get_supplemental_attributes(ReEDSEmission)
    ):
        logger.warning("Did not find any emission type to apply emission_cap")
        return system

    # If emission_cap not provided, try to load from file
    if emission_cap is None and co2_cap_fpath is not None:
        try:
            co2_cap_data = DataStore.load_file(co2_cap_fpath, name="co2_cap")
            if co2_cap_data is not None:
                co2_cap_data = co2_cap_data.collect()
            if co2_cap_data is not None and not co2_cap_data.is_empty():
                emission_cap = co2_cap_data["value"].item()
                logger.debug(f"Loaded emission cap from file: {emission_cap}")
        except Exception as e:
            logger.warning(f"Failed to extract emission cap value: {e}")

    # Check for precombustion emissions if data files provided
    if switches_fpath is not None and emission_rates_fpath is not None:
        try:
            switches = DataStore.load_file(switches_fpath, name="switches")
            emit_rates = DataStore.load_file(emission_rates_fpath, name="emission_rates")
            if switches is not None:
                switches = switches.collect()
            if emit_rates is not None:
                emit_rates = emit_rates.collect()
            if switches is not None and emit_rates is not None:
                _add_precombustion_if_enabled(system, switches, emit_rates)
        except Exception as e:
            logger.debug(f"Could not process precombustion emissions: {e}")

    return set_emission_constraint(system, emission_cap, default_unit, emission_object)


def _add_precombustion_if_enabled(system: System, switches: pl.DataFrame, emit_rates: pl.DataFrame) -> None:
    """Add precombustion emissions if enabled in switches.

    Parameters
    ----------
    system : System
        The system to modify.
    switches : pl.DataFrame
        Switches/configuration data.
    emit_rates : pl.DataFrame
        Emission rates data.
    """
    try:
        # Convert switches to dictionary format if it's a DataFrame
        if isinstance(switches, pl.DataFrame):
            if switches.is_empty():
                logger.warning("Switches data is empty")
                return

            # Try to extract the switch value
            switches_dict = {}
            if "switch_name" in switches.columns and "value" in switches.columns:
                for row in switches.iter_rows(named=True):
                    switches_dict[row["switch_name"]] = str(row["value"]).lower() in ["true", "1", "yes"]
            else:
                # Assume first column is name, second is value
                cols = switches.columns
                if len(cols) >= 2:
                    for row in switches.iter_rows(named=True):
                        key = row[cols[0]]
                        val = str(row[cols[1]]).lower() in ["true", "1", "yes"]
                        switches_dict[key] = val
        else:
            switches_dict = switches

        # Check for precombustion flag
        if switches_dict.get("gsw_precombustion") or switches_dict.get("gsw_annualcapco2e"):
            # Process emission rates for precombustion
            if not emit_rates.is_empty():
                emit_rates_processed = emit_rates.with_columns(
                    pl.concat_str(
                        [pl.col("tech"), pl.col("tech_vintage"), pl.col("region")], separator="_"
                    ).alias("generator_name")
                )

            # Filter for precombustion emissions
            any_precombustion = emit_rates_processed["emission_source"].str.contains("precombustion")
            emit_rates_precomb = emit_rates_processed.filter(any_precombustion)

            if not emit_rates_precomb.is_empty():
                logger.debug("Adding precombustion emission.")
                generator_with_precombustion = emit_rates_precomb.select(
                    "generator_name", "emission_type", "rate"
                ).unique()
                add_precombustion(system, generator_with_precombustion)
    except Exception as e:
        logger.debug(f"Could not process precombustion emissions: {e}")


def add_precombustion(system: System, emission_rates: pl.DataFrame) -> bool:
    """Add precombustion emission rates to `ReEDSEmission` objects.

    This function adds precombustion rates to the attributes ReEDSEmission.

    Parameters
    ----------
    system : System
        The system object to be updated.
    emission_rates : pl.DataFrame
        The precombustion emission_rates with columns: generator_name, emission_type, rate.

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
            component, ReEDSEmission, filter_func=lambda attr, et=emission_type: attr.type == et
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
    """Add emissions constraint object to the system.

    Parameters
    ----------
    system : System
        The system to modify.
    emission_cap : float | None, optional
        The emission cap value. If None, no cap is applied.
    default_unit : str, optional
        The default unit for measurement. Default is 'tonne'.
    emission_object : EmissionType | None, optional
        The type of emission to cap. Default is None.

    Returns
    -------
    System
        The modified system.
    """
    if emission_cap is None:
        logger.warning("Could not set emission cap value. Skipping plugin.")
        return system

    if not hasattr(system, "ext"):
        system._emission_constraints = {}
        constraint_storage = system._emission_constraints
    else:
        if "emission_constraints" not in system.ext:
            system.ext["emission_constraints"] = {}
        constraint_storage = system.ext["emission_constraints"]

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

    constraint_storage[constraint_name] = constraint_properties

    logger.info(
        "Added emission constraint '{}' with cap {} {} for {}",
        constraint_name,
        emission_cap,
        default_unit,
        emission_object,
    )

    return system
