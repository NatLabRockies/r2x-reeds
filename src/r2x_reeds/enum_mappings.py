"""Centralized enum mapping functions for ReEDS parser.

This module provides standardized functions for mapping string values to enum types,
eliminating duplicated mapping logic across the codebase. Each function handles
the specific normalization and validation required for its enum type.
"""

from __future__ import annotations

from r2x_core import Err, Ok, Result

from .models.enums import EmissionSource, EmissionType, ReserveDirection, ReserveType

RESERVE_TYPE_MAP = {
    "SPINNING": ReserveType.SPINNING,
    "FLEXIBILITY": ReserveType.FLEXIBILITY,
    "REGULATION": ReserveType.REGULATION,
    "COMBO": ReserveType.COMBO,
}

RESERVE_DIRECTION_MAP = {
    "UP": ReserveDirection.UP,
    "DOWN": ReserveDirection.DOWN,
}


def map_reserve_type(value: str) -> Result[ReserveType, ValueError]:
    """Map string value to ReserveType enum.

    Handles normalization of reserve type strings to their corresponding enum values.
    Supports case-insensitive matching with standard reserve type names.

    Parameters
    ----------
    value : str
        Reserve type string to map (e.g., "SPINNING", "FLEXIBILITY", "REGULATION")

    Returns
    -------
    Result[ReserveType, ValueError]
        Ok(enum_value) if mapping successful, Err(ValueError) if unknown type

    Examples
    --------
    >>> map_reserve_type("SPINNING").ok()
    <ReserveType.SPINNING: 'spinning'>
    >>> map_reserve_type("FLEXIBILITY").ok()
    <ReserveType.FLEXIBILITY_UP: 'flexibility_up'>
    >>> map_reserve_type("unknown").is_err()
    True
    """
    key = str(value).upper()
    if key not in RESERVE_TYPE_MAP:
        return Err(ValueError(f"Unknown reserve type: {value}"))
    return Ok(RESERVE_TYPE_MAP[key])


def map_reserve_direction(value: str) -> Result[ReserveDirection, ValueError]:
    """Map string value to ReserveDirection enum.

    Handles normalization of direction strings to their corresponding enum values.
    Supports case-insensitive matching with standard direction names.

    Parameters
    ----------
    value : str
        Direction string to map (e.g., "up", "down", "UP", "DOWN")

    Returns
    -------
    Result[ReserveDirection, ValueError]
        Ok(enum_value) if mapping successful, Err(ValueError) if unknown direction

    Examples
    --------
    >>> map_reserve_direction("up").ok()
    <ReserveDirection.UP: 'up'>
    >>> map_reserve_direction("DOWN").ok()
    <ReserveDirection.DOWN: 'down'>
    >>> map_reserve_direction("invalid").is_err()
    True
    """
    normalized = str(value).upper()
    if normalized not in RESERVE_DIRECTION_MAP:
        return Err(ValueError(f"Unknown direction: {value}"))
    return Ok(RESERVE_DIRECTION_MAP[normalized])


def map_emission_type(value: str) -> Result[EmissionType, ValueError]:
    """Map string value to EmissionType enum.

    Handles case-insensitive matching of emission type strings to enum values
    by iterating through available enum values.

    Parameters
    ----------
    value : str
        Emission type string to map (e.g., "CO2", "CO2e", "N2O", "CH4")

    Returns
    -------
    Result[EmissionType, ValueError]
        Ok(enum_value) if mapping successful, Err(ValueError) if unknown type

    Examples
    --------
    >>> map_emission_type("CO2").ok()
    <EmissionType.CO2: 'CO2'>
    >>> map_emission_type("n2o").ok()
    <EmissionType.N2O: 'N2O'>
    >>> map_emission_type("unknown").is_err()
    True
    """
    normalized = str(value).strip()
    normalized_casefold = normalized.casefold()
    for emission in EmissionType:
        if emission.value.casefold() == normalized_casefold:
            return Ok(emission)
    return Err(ValueError(f"Unknown emission type: {value}"))


def map_emission_source(value: str | None) -> Result[EmissionSource, ValueError]:
    """Map string value to EmissionSource enum.

    Handles flexible matching of emission source strings with keyword detection.
    Returns COMBUSTION as default if value is None. Matches keywords like
    PRECOMBUSTION, PROCESS, UPSTREAM, or COMBUSTION.

    Parameters
    ----------
    value : str | None
        Emission source string to map (e.g., "COMBUSTION", "PRECOMBUSTION", "UPSTREAM")

    Returns
    -------
    Result[EmissionSource, ValueError]
        Ok(enum_value) if mapping successful
        Ok(EmissionSource.COMBUSTION) if value is None (default)
        Err(ValueError) if unknown source

    Examples
    --------
    >>> map_emission_source("COMBUSTION").ok()
    <EmissionSource.COMBUSTION: 'combustion'>
    >>> map_emission_source("PRECOMBUSTION").ok()
    <EmissionSource.PRECOMBUSTION: 'precombustion'>
    >>> map_emission_source(None).ok()
    <EmissionSource.COMBUSTION: 'combustion'>
    >>> map_emission_source("unknown").is_err()
    True
    """
    if value is None:
        return Ok(EmissionSource.COMBUSTION)

    key = str(value).strip().upper()
    if "PRECOMBUSTION" in key or "PROCESS" in key or "UPSTREAM" in key:
        return Ok(EmissionSource.PRECOMBUSTION)
    if "COMBUSTION" in key:
        return Ok(EmissionSource.COMBUSTION)
    return Err(ValueError(f"Unknown emission source: {value}"))
