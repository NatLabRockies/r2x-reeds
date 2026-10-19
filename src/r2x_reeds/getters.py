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
from r2x_reeds.row_utils import get_row_field


def _reeds_getter(func):
    """Decorator to register a function as a ReEDS-specific getter."""
    return getter(func)


def get_region_by_name(system: Any, region_name: str) -> ReEDSRegion:
    """Return a region by exact name, allowing source-case differences."""
    try:
        return system.get_component(ReEDSRegion, name=region_name)
    except Exception as exact_error:
        matches = [
            region
            for region in system.get_components(ReEDSRegion)
            if region.name.casefold() == region_name.casefold()
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise ValueError(f"Multiple regions match {region_name!r} case-insensitively") from exact_error
        raise


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

    try:
        region_name = get_row_field(row, "region")
        if region_name is None:
            return Err(ValueError("Row missing required 'region' field"))

        if context.system is None:
            return Err(ValueError("System not available in context"))
        region = get_region_by_name(context.system, str(region_name))
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


def build_resource_name(technology: str, resource_class: Any, sc_point_gid: int, year: Any) -> str:
    """Build a stable name for resource site and build components."""

    resource_class_name = str(resource_class)
    if year is None:
        return f"{technology}_{resource_class_name}_{sc_point_gid}"
    return f"{technology}_{resource_class_name}_{year}_{sc_point_gid}"


@_reeds_getter
def build_resource_component_name(row: Any, *, context: PluginContext) -> Result[str, Exception]:
    """Build a resource component name from its configured record fields."""
    _ = context
    technology = get_row_field(row, "technology")
    resource_class = get_row_field(row, "resource_class")
    sc_point_gid = get_row_field(row, "sc_point_gid")
    if technology is None or resource_class is None or sc_point_gid is None:
        return Err(ValueError("Resource row is missing name fields"))
    return Ok(
        build_resource_name(
            str(technology),
            resource_class,
            int(sc_point_gid),
            get_row_field(row, "year"),
        )
    )


@_reeds_getter
def build_resource_geo_json(row: Any, *, context: PluginContext) -> Result[dict[str, Any], Exception]:
    """Build a GeoJSON point from configured resource coordinates and identity."""
    _ = context
    latitude = get_row_field(row, "latitude")
    longitude = get_row_field(row, "longitude")
    if latitude is None or longitude is None:
        return Err(ValueError("Resource coordinates are missing"))

    properties: dict[str, Any] = {
        "name": get_row_field(row, "name"),
        "technology": get_row_field(row, "technology"),
        "sc_point_gid": get_row_field(row, "sc_point_gid"),
        "resource_class": get_row_field(row, "resource_class"),
    }
    year = get_row_field(row, "year")
    if year is not None:
        properties["year"] = year
    return Ok(
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [longitude, latitude]},
            "properties": properties,
        }
    )


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
    """Lookup the alphabetically first region of an interface."""

    if context.system is None:
        return Err(ValueError("System not available in context"))
    from_region = get_row_field(row, "from_region")
    to_region = get_row_field(row, "to_region")
    if not from_region or not to_region:
        return Err(ValueError("Transmission row missing region identifiers"))
    return lookup_region(
        {"region": min(str(from_region), str(to_region))},
        context=context,
    )


@_reeds_getter
def lookup_to_region(row: Any, *, context: PluginContext) -> Result[ReEDSRegion, Exception]:
    """Lookup the alphabetically second region of an interface."""

    if context.system is None:
        return Err(ValueError("System not available in context"))
    from_region = get_row_field(row, "from_region")
    to_region = get_row_field(row, "to_region")
    if not from_region or not to_region:
        return Err(ValueError("Transmission row missing region identifiers"))
    return lookup_region(
        {"region": max(str(from_region), str(to_region))},
        context=context,
    )


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
    """Build a symmetric line name from sorted from/to regions and line type."""

    try:
        from_region = get_row_field(row, "from_region")
        to_region = get_row_field(row, "to_region")
        line_type = get_row_field(row, "trtype")

        if not from_region or not to_region or not line_type:
            return Err(ValueError("Transmission row missing identifiers for line name"))

        regions = sorted([str(from_region), str(to_region)])
        return Ok(f"{regions[0]}_{regions[1]}_{line_type}")
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
    """Build asymmetric FromTo_ToFrom from forward capacity and reverse capacity.

    Expects:
    - 'capacity'         : forward direction rating (MW) → to_from (positive)
    - 'reverse_capacity' : reverse direction rating (MW) → from_to (positive)

    Falls back to symmetric if 'reverse_capacity' is absent.
    """
    try:
        forward = get_row_field(row, "capacity")
        if forward is None:
            forward = get_row_field(row, "value")
        if forward is None:
            return Err(ValueError("Transmission row missing 'capacity' field"))

        reverse = get_row_field(row, "reverse_capacity")
        if reverse is None:
            reverse = forward

        return Ok(FromTo_ToFrom(from_to=abs(float(reverse)), to_from=abs(float(forward))))
    except Exception as e:
        return Err(e)
