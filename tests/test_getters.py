from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest

from r2x_core import PluginContext, System
from r2x_reeds import ReEDSConfig

pytestmark = [pytest.mark.unit]


@pytest.fixture
def context_with_regions(sample_region):
    system = System(name="test_getters")
    system.add_component(sample_region)
    from r2x_reeds.models import ReEDSInterface, ReEDSRegion, ReEDSReserveRegion

    other_region = ReEDSRegion(name="p2")
    system.add_component(other_region)
    reserve_region = ReEDSReserveRegion(name="rsv")
    system.add_component(reserve_region)
    interface = ReEDSInterface(name="p1||p2", from_region=sample_region, to_region=other_region)
    system.add_component(interface)
    metadata = {"tech_categories": {"hydro_dispatchable": {"prefixes": ["hyd"]}}}
    config = ReEDSConfig(solve_year=2030, weather_year=2012, case_name="test_getters")
    return cast(PluginContext, PluginContext(system=system, config=config, metadata=metadata))


@pytest.fixture
def dummy_context():
    config = ReEDSConfig(solve_year=2030, weather_year=2012, case_name="test_getters")
    return cast(PluginContext, PluginContext(system=None, config=config, metadata={}))


def test_lookup_region_success(context_with_regions):
    from r2x_reeds.getters import lookup_region

    result = lookup_region({"region": "p1"}, context=context_with_regions)
    assert result.is_ok()
    assert result.ok() is not None


def test_lookup_region_missing_field(context_with_regions):
    from r2x_reeds.getters import lookup_region

    result = lookup_region({}, context=context_with_regions)
    assert result.is_err()


def test_lookup_region_no_system(dummy_context):
    from r2x_reeds.getters import lookup_region

    # dummy_context has system=None
    result = lookup_region({"region": "p1"}, context=dummy_context)
    assert result.is_err()
    assert "System not available" in str(result.err())


def test_build_region_description_prefers_region_id(dummy_context):
    from r2x_reeds.getters import build_region_description

    result = build_region_description({"region_id": "abc"}, context=dummy_context)
    assert result.is_ok()
    assert result.ok() == "ReEDS region abc"


def test_build_region_description_missing_identifier(dummy_context):
    from r2x_reeds.getters import build_region_description

    result = build_region_description({}, context=dummy_context)
    assert result.is_err()


def test_build_region_description_with_namespace(dummy_context):
    from r2x_reeds.getters import build_region_description

    result = build_region_description(SimpleNamespace(region="foo"), context=dummy_context)
    assert result.is_ok()
    assert result.ok() == "ReEDS region foo"


def test_build_region_name_handles_multiple_keys(dummy_context):
    from r2x_reeds.getters import build_region_name

    result = build_region_name({"*r": "west"}, context=dummy_context)
    assert result.is_ok()
    assert result.ok() == "west"


def test_build_region_name_with_namespace(dummy_context):
    from r2x_reeds.getters import build_region_name

    result = build_region_name(SimpleNamespace(region="ns"), context=dummy_context)
    assert result.is_ok()
    assert result.ok() == "ns"


def test_build_region_name_missing_identifier(dummy_context):
    from r2x_reeds.getters import build_region_name

    result = build_region_name({}, context=dummy_context)
    assert result.is_err()


def test_build_region_name_handles_faulty_get(dummy_context):
    from r2x_reeds.getters import build_region_name

    class FaultyRow:
        def __init__(self, region):
            self.region = region

        def get(self, field):
            raise RuntimeError("boom")

    result = build_region_name(FaultyRow("south"), context=dummy_context)
    assert result.is_ok()
    assert result.ok() == "south"


def test_build_generator_name_includes_vintage(dummy_context):
    from r2x_reeds.getters import build_generator_name

    result = build_generator_name(
        {"technology": "wind", "vintage": "v1", "region": "p1"}, context=dummy_context
    )
    assert result.is_ok()
    assert result.ok() == "wind_v1_p1"


def test_build_generator_name_with_namespace_row(dummy_context):
    from r2x_reeds.getters import build_generator_name

    result = build_generator_name(SimpleNamespace(technology="gas", region="p1"), context=dummy_context)
    assert result.is_ok()
    assert result.ok() == "gas_p1"


def test_build_load_and_reserve_names(context_with_regions):
    from r2x_reeds.getters import build_load_name, build_reserve_name

    load_result = build_load_name({"region": "p1"}, context=context_with_regions)
    reserve_result = build_reserve_name(
        {"region": "p1", "reserve_type": "spin"}, context=context_with_regions
    )

    assert load_result.is_ok() and reserve_result.is_ok()
    assert load_result.ok() == "p1_load"
    assert reserve_result.ok() == "p1_spin"


def test_build_load_name_missing_region(context_with_regions):
    from r2x_reeds.getters import build_load_name

    result = build_load_name({}, context=context_with_regions)
    assert result.is_err()


def test_build_reserve_name_missing_fields(context_with_regions):
    from r2x_reeds.getters import build_reserve_name

    result = build_reserve_name({"region": "p1"}, context=context_with_regions)
    assert result.is_err()


def test_reserve_type_and_direction_resolution(dummy_context):
    from r2x_reeds.getters import resolve_reserve_direction, resolve_reserve_type
    from r2x_reeds.models import ReserveDirection, ReserveType

    type_result = resolve_reserve_type({"reserve_type": "SPINNING"}, context=dummy_context)
    dir_result = resolve_reserve_direction({"direction": "up"}, context=dummy_context)
    assert type_result.is_ok() and dir_result.is_ok()
    assert type_result.ok() == ReserveType.SPINNING
    assert dir_result.ok() == ReserveDirection.UP


def test_reserve_type_invalid_raises_err(dummy_context):
    from r2x_reeds.getters import resolve_reserve_type

    result = resolve_reserve_type({"reserve_type": "invalid"}, context=dummy_context)
    assert result.is_err()


def test_reserve_direction_missing_errors(dummy_context):
    from r2x_reeds.getters import resolve_reserve_direction

    result = resolve_reserve_direction({}, context=dummy_context)
    assert result.is_err()


def test_storage_defaults(dummy_context):
    from r2x_reeds.getters import get_round_trip_efficiency, get_storage_duration

    assert get_storage_duration({}, context=dummy_context).ok() == 1.0
    assert get_round_trip_efficiency({}, context=dummy_context).ok() == 1.0
    assert get_storage_duration({"storage_duration": 2}, context=dummy_context).ok() == 2.0
    assert get_round_trip_efficiency({"round_trip_efficiency": 0.9}, context=dummy_context).ok() == 0.9


def test_fuel_type_known_and_unknown(dummy_context):
    from r2x_reeds.getters import get_fuel_type

    known = get_fuel_type({"fuel_type": "NaturalGas"}, context=dummy_context)
    unknown = get_fuel_type({"fuel_type": "mystery"}, context=dummy_context)
    assert known.is_ok()
    assert known.ok() == "NaturalGas"
    assert unknown.is_ok()
    assert unknown.ok() == "mystery"


def test_get_fuel_type_thermal_defaults_to_other(dummy_context):
    from r2x_reeds.getters import get_fuel_type

    dummy_context.metadata = {"tech_categories": {"thermal": {"prefixes": ["gas"]}}}
    result = get_fuel_type({"technology": "gas-ct"}, context=dummy_context)
    assert result.is_ok()
    assert result.ok() == "OTHER"


def test_get_fuel_type_non_thermal_missing_fuel_errors(dummy_context):
    from r2x_reeds.getters import get_fuel_type

    dummy_context.metadata = {"tech_categories": {"thermal": {"prefixes": ["coal"]}}}
    result = get_fuel_type({"technology": "solar"}, context=dummy_context)
    assert result.is_err()


def test_get_fuel_type_missing_field_errors(dummy_context):
    from r2x_reeds.getters import get_fuel_type

    result = get_fuel_type({}, context=dummy_context)
    assert result.is_err()


def test_emission_type_and_source_resolution(dummy_context):
    from r2x_reeds.getters import resolve_emission_source, resolve_emission_type
    from r2x_reeds.models import EmissionSource

    type_result = resolve_emission_type({"emission_type": "co2"}, context=dummy_context)
    source_result = resolve_emission_source({"emission_source": None}, context=dummy_context)
    assert type_result.is_ok()
    assert source_result.is_ok()
    assert source_result.ok() == EmissionSource.COMBUSTION


def test_emission_type_unknown_errors(dummy_context):
    from r2x_reeds.getters import resolve_emission_type

    result = resolve_emission_type({"emission_type": "unknown"}, context=dummy_context)
    assert result.is_err()


def test_emission_source_unknown_errors(dummy_context):
    from r2x_reeds.getters import resolve_emission_source

    result = resolve_emission_source({"emission_source": "mystery"}, context=dummy_context)
    assert result.is_err()


def test_emission_type_missing_errors(dummy_context):
    from r2x_reeds.getters import resolve_emission_type

    result = resolve_emission_type({}, context=dummy_context)
    assert result.is_err()


def test_resolve_emission_generator_identifier_success(dummy_context):
    from r2x_reeds.getters import resolve_emission_generator_identifier

    result = resolve_emission_generator_identifier({"name": "gen1"}, context=dummy_context)
    assert result.is_ok()
    assert result.ok() == "gen1"


def test_resolve_emission_generator_identifier_missing(dummy_context):
    from r2x_reeds.getters import resolve_emission_generator_identifier

    result = resolve_emission_generator_identifier({}, context=dummy_context)
    assert result.is_err()


def test_lookup_from_and_to_region(context_with_regions):
    from r2x_reeds.getters import lookup_from_region, lookup_to_region

    from_result = lookup_from_region({"from_region": "p1"}, context=context_with_regions)
    to_result = lookup_to_region({"to_region": "p2"}, context=context_with_regions)
    assert from_result.is_ok() and to_result.is_ok()
    assert from_result.ok() is not None
    assert to_result.ok() is not None


def test_lookup_reserve_region_success(context_with_regions):
    from r2x_reeds.getters import lookup_reserve_region

    result = lookup_reserve_region({"region": "rsv"}, context=context_with_regions)
    assert result.is_ok()
    assert result.ok() is not None


def test_lookup_reserve_region_missing_field(context_with_regions):
    from r2x_reeds.getters import lookup_reserve_region

    result = lookup_reserve_region({}, context=context_with_regions)
    assert result.is_err()


def test_lookup_region_missing_field_errors(context_with_regions):
    from r2x_reeds.getters import lookup_to_region

    result = lookup_to_region({}, context=context_with_regions)
    assert result.is_err()


def test_transmission_interface_and_line_names(dummy_context):
    from r2x_reeds.getters import build_transmission_interface_name, build_transmission_line_name

    interface_result = build_transmission_interface_name(
        {"from_region": "b", "to_region": "a"}, context=dummy_context
    )
    line_result = build_transmission_line_name(
        {"from_region": "a", "to_region": "b", "trtype": "ac"}, context=dummy_context
    )
    assert interface_result.is_ok() and line_result.is_ok()
    assert interface_result.ok() == "a||b"
    assert line_result.ok() == "a_b_ac"


def test_build_transmission_interface_name_missing_fields(dummy_context):
    from r2x_reeds.getters import build_transmission_interface_name

    result = build_transmission_interface_name({"from_region": "p1"}, context=dummy_context)
    assert result.is_err()


def test_build_transmission_line_name_missing_fields(dummy_context):
    from r2x_reeds.getters import build_transmission_line_name

    result = build_transmission_line_name({"from_region": "a", "to_region": "b"}, context=dummy_context)
    assert result.is_err()


def test_lookup_transmission_interface(context_with_regions):
    from r2x_reeds.getters import lookup_transmission_interface

    row = {"from_region": "p1", "to_region": "p2"}
    result = lookup_transmission_interface(row, context=context_with_regions)
    assert result.is_ok()
    assert result.ok() is not None


def test_lookup_transmission_interface_missing_identifiers(context_with_regions):
    from r2x_reeds.getters import lookup_transmission_interface

    row = {"from_region": "p1"}
    result = lookup_transmission_interface(row, context=context_with_regions)
    assert result.is_err()


def test_build_transmission_flow_with_capacity(dummy_context):
    from r2x_reeds.getters import build_transmission_flow
    from r2x_reeds.models import FromTo_ToFrom

    result = build_transmission_flow({"capacity": 100}, context=dummy_context)
    assert result.is_ok()
    flow = result.ok()
    assert flow is not None
    assert isinstance(flow, FromTo_ToFrom)
    assert flow.from_to == flow.to_from == 100.0


def test_build_transmission_flow_with_value_fallback(dummy_context):
    from r2x_reeds.getters import build_transmission_flow

    result = build_transmission_flow({"value": 75}, context=dummy_context)
    assert result.is_ok()
    assert result.ok() is not None


def test_build_transmission_flow_missing_fields(dummy_context):
    from r2x_reeds.getters import build_transmission_flow

    result = build_transmission_flow({}, context=dummy_context)
    assert result.is_err()


class ExplodingRow:
    def __getattr__(self, name):
        raise RuntimeError("boom")

    def get(self, name):
        raise RuntimeError("boom")


def test_getters_surface_internal_exceptions(context_with_regions):
    from r2x_reeds.getters import (
        build_generator_name,
        build_load_name,
        build_region_description,
        build_region_name,
        build_reserve_name,
        build_transmission_interface_name,
        build_transmission_line_name,
        compute_is_dispatchable,
        get_round_trip_efficiency,
        get_storage_duration,
        resolve_emission_source,
        resolve_emission_type,
        resolve_reserve_direction,
        resolve_reserve_type,
    )

    bad_row = ExplodingRow()
    context = cast(
        PluginContext,
        PluginContext(system=context_with_regions.system, config=context_with_regions.config, metadata={}),
    )

    assert build_region_description(bad_row, context=context).is_err()
    assert build_region_name(bad_row, context=context).is_err()
    assert compute_is_dispatchable(bad_row, context=context).is_err()
    assert build_generator_name(bad_row, context=context).is_err()
    assert build_load_name(bad_row, context=context).is_err()
    assert build_reserve_name(bad_row, context=context).is_err()
    assert resolve_reserve_type(bad_row, context=context).is_err()
    assert resolve_reserve_direction(bad_row, context=context).is_err()
    assert get_storage_duration(bad_row, context=context).is_err()
    assert get_round_trip_efficiency(bad_row, context=context).is_err()
    assert resolve_emission_type(bad_row, context=context).is_err()
    assert resolve_emission_source(bad_row, context=context).is_err()
    assert build_transmission_interface_name(bad_row, context=context).is_err()
    assert build_transmission_line_name(bad_row, context=context).is_err()


def test_lookup_transmission_interface_and_flow_errors(dummy_context):
    from r2x_reeds.getters import build_transmission_flow, lookup_transmission_interface

    bad_context = cast(
        PluginContext,
        PluginContext(system=None, config=dummy_context.config, metadata={}),
    )
    row = {"from_region": "p1", "to_region": "p2", "trtype": "ac", "capacity": "bad"}

    flow_result = build_transmission_flow({"capacity": "not-a-number"}, context=dummy_context)
    assert flow_result.is_err()

    lookup_result = lookup_transmission_interface(row, context=bad_context)
    assert lookup_result.is_err()
