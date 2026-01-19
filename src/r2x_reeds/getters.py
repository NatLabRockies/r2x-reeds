"""Getter functions for ReEDS parser using r2x-core getter registry."""

from __future__ import annotations

from typing import Any

from r2x_core import Err, Ok, PluginContext, Result
from r2x_core.getters import getter
from r2x_reeds.enum_mappings import (
    map_emission_source,
    map_emission_type,
    map_reserve_direction,
    map_reserve_type,
)
from r2x_reeds.models.base import FromTo_ToFrom
from r2x_reeds.models.components import ReEDSInterface, ReEDSRegion, ReEDSReserveRegion
from r2x_reeds.models.enums import EmissionSource, EmissionType, ReserveDirection, ReserveType
from r2x_reeds.parser_utils import tech_matches_category
from r2x_reeds.row_utils import get_row_field


def _reeds_getter(func):
    return getter(func)


@_reeds_getter
def lookup_region(row: Any, *, context: PluginContext) -> Result[ReEDSRegion, Exception]:
    """Look up region component by name from the system.

    Parameters
    ----------
    context : PluginContext
        Parser context containing the system and config
    row : Any
        Data row (dict or SimpleNamespace) with 'region' field

    Returns
    -------
    Result[ReEDSRegion, Exception]
        Ok(region) if found, Err(exception) if failed
    """
    from r2x_reeds.models.components import ReEDSRegion

    try:
        region_name = get_row_field(row, "region")
        if region_name is None:
            return Err(ValueError("Row missing required 'region' field"))

        if context.system is None:
            return Err(ValueError("System not available in context"))
        region = context.system.get_component(ReEDSRegion, str(region_name))
        return Ok(region)
    except Exception as e:
        return Err(e)


@_reeds_getter
def build_region_description(row: Any, *, context: PluginContext) -> Result[str, Exception]:
    """Return a consistent description for a region row."""

    try:
        region_name = get_row_field(row, "region_id") or get_row_field(row, "region")
        if region_name is None:
            return Err(ValueError("Row missing region identifier for description"))

        return Ok(f"ReEDS region {region_name}")
    except Exception as e:
        return Err(e)


@_reeds_getter
def build_region_name(row: Any, *, context: PluginContext) -> Result[str, Exception]:
    """Build a canonical region name for parser records."""

    def _lookup(field: str) -> Any:
        """Return the requested field value using row_utils."""
        return get_row_field(row, field)

    try:
        region_id = _lookup("region_id") or _lookup("region") or _lookup("r") or _lookup("*r")
        if not region_id:
            return Err(ValueError("Row missing region identifier for name"))
        return Ok(str(region_id))
    except Exception as e:
        return Err(e)


@_reeds_getter
def compute_is_dispatchable(row: Any, *, context: PluginContext) -> Result[bool, Exception]:
    """Determine if hydro generator is dispatchable from technology category.

    Parameters
    ----------
    context : PluginContext
        Parser context with metadata containing tech_categories
    row : Any
        Data row (dict or SimpleNamespace) with 'technology' field

    Returns
    -------
    Result[bool, Exception]
        Ok(True/False) based on technology category
    """
    from r2x_reeds.parser_utils import tech_matches_category

    try:
        tech = get_row_field(row, "technology")
        if tech is None:
            return Ok(False)

        tech_categories = context.metadata.get("tech_categories", {})
        is_dispatchable = tech_matches_category(str(tech), "hydro_dispatchable", tech_categories)
        return Ok(is_dispatchable)
    except Exception as e:
        return Err(e)


@_reeds_getter
def build_generator_name(row: Any, *, context: PluginContext) -> Result[str, Exception]:
    """Build generator name from technology, vintage, and region.

    Parameters
    ----------
    context : PluginContext
        Parser context (unused but required by getter signature)
    row : Any
        Data row (dict or SimpleNamespace) with 'technology', 'vintage', and 'region' fields

    Returns
    -------
    Result[str, Exception]
        Ok(name) with generated name in format: {tech}_{vintage}_{region} or {tech}_{region}
    """
    try:
        tech = get_row_field(row, "technology", "unknown")
        region = get_row_field(row, "region", "unknown")
        vintage = get_row_field(row, "vintage")

        if vintage:
            return Ok(f"{tech}_{vintage}_{region}")
        return Ok(f"{tech}_{region}")
    except Exception as e:
        return Err(e)


@_reeds_getter
def build_load_name(row: Any, *, context: PluginContext) -> Result[str, Exception]:
    """Build canonical load name from region."""

    try:
        region = get_row_field(row, "region")
        if region is None:
            return Err(ValueError("Load row missing 'region' field"))
        return Ok(f"{region}_load")
    except Exception as e:
        return Err(e)


@_reeds_getter
def build_reserve_name(row: Any, *, context: PluginContext) -> Result[str, Exception]:
    """Build reserve component name from region and type."""

    try:
        region = get_row_field(row, "region")
        reserve_type = get_row_field(row, "reserve_type")
        if not region or not reserve_type:
            return Err(ValueError("Reserve row missing region or reserve_type"))
        return Ok(f"{region}_{reserve_type}")
    except Exception as e:
        return Err(e)


@_reeds_getter
def resolve_reserve_type(row: Any, *, context: PluginContext) -> Result[ReserveType, Exception]:
    """Map reserve_type string to ReserveType enum."""

    try:
        value = get_row_field(row, "reserve_type")
        if not value:
            return Err(ValueError("Reserve row missing reserve_type"))
        return map_reserve_type(str(value))
    except Exception as e:
        return Err(e)


@_reeds_getter
def resolve_reserve_direction(row: Any, *, context: PluginContext) -> Result[ReserveDirection, Exception]:
    """Map direction string to ReserveDirection enum."""

    try:
        value = get_row_field(row, "direction")
        if value is None:
            return Err(ValueError("Reserve row missing direction"))
        return map_reserve_direction(str(value))
    except Exception as e:
        return Err(e)


@_reeds_getter
def get_storage_duration(row: Any, *, context: PluginContext) -> Result[float, Exception]:
    """Return storage duration, defaulting to 1.0 if missing."""
    try:
        value = get_row_field(row, "storage_duration")
        return Ok(float(value) if value is not None else 1.0)
    except Exception as e:
        return Err(e)


@_reeds_getter
def get_round_trip_efficiency(row: Any, *, context: PluginContext) -> Result[float, Exception]:
    """Return round-trip efficiency, defaulting to 1.0 if missing."""
    try:
        value = get_row_field(row, "round_trip_efficiency")
        return Ok(float(value) if value is not None else 1.0)
    except Exception as e:
        return Err(e)


@_reeds_getter
def get_fuel_type(row: Any, *, context: PluginContext) -> Result[str, Exception]:
    """Resolve the fuel type from the joined ``fuel2tech`` mapping."""
    try:
        value = get_row_field(row, "fuel_type")
        if value is not None:
            return Ok(str(value).strip())

        technology = get_row_field(row, "technology")
        tech_categories = getattr(context, "metadata", {}).get("tech_categories", {})
        if technology and tech_matches_category(str(technology), "thermal", tech_categories):
            return Ok("OTHER")

        return Err(ValueError("Row missing required 'fuel_type' field"))
    except Exception as e:
        return Err(e)


@_reeds_getter
def resolve_emission_type(row: Any, *, context: PluginContext) -> Result[EmissionType, Exception]:
    """Normalize emission type strings to the EmissionType enum."""

    try:
        value = get_row_field(row, "emission_type")
        if not value:
            return Err(ValueError("Row missing required 'emission_type' field"))
        return map_emission_type(str(value))
    except Exception as e:
        return Err(e)


@_reeds_getter
def resolve_emission_source(row: Any, *, context: PluginContext) -> Result[EmissionSource, Exception]:
    """Map emission_source text to the EmissionSource enum."""

    try:
        raw_value = get_row_field(row, "emission_source")
        return map_emission_source(raw_value)
    except Exception as e:
        return Err(e)


@_reeds_getter
def resolve_emission_generator_identifier(row: Any, *, context: PluginContext) -> Result[str, Exception]:
    """Identify the generator associated with an emission row."""

    try:
        identifier = get_row_field(row, "name")
        if not identifier:
            return Err(ValueError("Emission row missing generator identifier"))
        return Ok(str(identifier))
    except Exception as e:
        return Err(e)


@_reeds_getter
def lookup_from_region(row: Any, *, context: PluginContext) -> Result[ReEDSRegion, Exception]:
    """Lookup region using the 'from_region' key."""

    return _lookup_region_by_field(row, field="from_region", context=context)


@_reeds_getter
def lookup_to_region(row: Any, *, context: PluginContext) -> Result[ReEDSRegion, Exception]:
    """Lookup region using the 'to_region' key."""

    return _lookup_region_by_field(row, field="to_region", context=context)


def _lookup_region_by_field(
    row: Any, field: str, *, context: PluginContext
) -> Result[ReEDSRegion, Exception]:
    """Shared helper to look up regions by a configurable field."""
    from r2x_reeds.models.components import ReEDSRegion

    try:
        region_name = get_row_field(row, field)
        if region_name is None:
            return Err(ValueError(f"Row missing required '{field}' field"))

        if context.system is None:
            return Err(ValueError("System not available in context"))
        region = context.system.get_component(ReEDSRegion, str(region_name))
        return Ok(region)
    except Exception as e:
        return Err(e)


def _lookup_reserve_region_by_field(
    row: Any, field: str, *, context: PluginContext
) -> Result[ReEDSReserveRegion, Exception]:
    """Fetch reserve regions by alternative field names."""
    from r2x_reeds.models.components import ReEDSReserveRegion

    try:
        region_name = get_row_field(row, field)
        if region_name is None:
            return Err(ValueError(f"Row missing required '{field}' field"))

        if context.system is None:
            return Err(ValueError("System not available in context"))
        region = context.system.get_component(ReEDSReserveRegion, str(region_name))
        return Ok(region)
    except Exception as e:
        return Err(e)


@_reeds_getter
def lookup_reserve_region(row: Any, *, context: PluginContext) -> Result[ReEDSReserveRegion, Exception]:
    """Lookup reserve region component using the 'region' key."""

    return _lookup_reserve_region_by_field(row, field="region", context=context)


@_reeds_getter
def build_transmission_interface_name(row: Any, *, context: PluginContext) -> Result[str, Exception]:
    """Create a canonical interface name by sorting region names."""

    try:
        from_region = get_row_field(row, "from_region")
        to_region = get_row_field(row, "to_region")

        if not from_region or not to_region:
            return Err(ValueError("Transmission row missing region identifiers"))

        stable_regions = sorted([str(from_region), str(to_region)])
        return Ok(f"{stable_regions[0]}||{stable_regions[1]}")
    except Exception as e:
        return Err(e)


@_reeds_getter
def build_transmission_line_name(row: Any, *, context: PluginContext) -> Result[str, Exception]:
    """Build a line name from from/to regions and line type."""

    try:
        from_region = get_row_field(row, "from_region")
        to_region = get_row_field(row, "to_region")
        line_type = get_row_field(row, "trtype")

        if not from_region or not to_region or not line_type:
            return Err(ValueError("Transmission row missing identifiers for line name"))

        return Ok(f"{from_region}_{to_region}_{line_type}")
    except Exception as e:
        return Err(e)


@_reeds_getter
def lookup_transmission_interface(row: Any, *, context: PluginContext) -> Result[ReEDSInterface, Exception]:
    """Fetch transmission interface component by canonical name."""

    if context.system is None:
        return Err(ValueError("System not available in context"))

    from r2x_reeds.models.components import ReEDSInterface

    name_result = build_transmission_interface_name(row, context=context)
    if name_result.is_err():
        return Err(name_result.err())

    try:
        interface_name = name_result.ok()
        if interface_name is None:
            return Err(ValueError("Transmission interface name not available"))
        interface = context.system.get_component(ReEDSInterface, interface_name)
        return Ok(interface)
    except Exception as e:
        return Err(e)


@_reeds_getter
def build_transmission_flow(row: Any, *, context: PluginContext) -> Result[FromTo_ToFrom, Exception]:
    """Build symmetric FromTo_ToFrom object from the 'value' field."""

    try:
        value = get_row_field(row, "capacity")
        if value is None:
            value = get_row_field(row, "value")
        if value is None:
            return Err(ValueError("Transmission row missing 'capacity' field"))

        return Ok(FromTo_ToFrom(from_to=float(value), to_from=float(value)))
    except Exception as e:
        return Err(e)
