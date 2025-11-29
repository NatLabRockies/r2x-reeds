from __future__ import annotations

from types import SimpleNamespace

import pytest
from infrasys import System


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
    return SimpleNamespace(system=system, metadata=metadata)


def test_lookup_region_success(context_with_regions):
    from r2x_reeds.getters import lookup_region

    result = lookup_region(context_with_regions, {"region": "p1"})
    assert result.is_ok()
    assert result.ok().name == "p1"


def test_lookup_region_missing_field(context_with_regions):
    from r2x_reeds.getters import lookup_region

    result = lookup_region(context_with_regions, {})
    assert result.is_err()


def test_build_region_description_prefers_region_id():
    from r2x_reeds.getters import build_region_description

    result = build_region_description(SimpleNamespace(), {"region_id": "abc"})
    assert result.is_ok()
    assert result.ok() == "ReEDS region abc"


def test_build_region_description_missing_identifier():
    from r2x_reeds.getters import build_region_description

    result = build_region_description(SimpleNamespace(), {})
    assert result.is_err()


def test_build_region_description_with_namespace():
    from r2x_reeds.getters import build_region_description

    result = build_region_description(SimpleNamespace(), SimpleNamespace(region="foo"))
    assert result.is_ok()
    assert result.ok() == "ReEDS region foo"


def test_build_region_name_handles_multiple_keys():
    from r2x_reeds.getters import build_region_name

    result = build_region_name(SimpleNamespace(), {"*r": "west"})
    assert result.is_ok()
    assert result.ok() == "west"


def test_build_region_name_with_namespace():
    from r2x_reeds.getters import build_region_name

    result = build_region_name(SimpleNamespace(region="ns"), SimpleNamespace(region="ns"))
    assert result.is_ok()
    assert result.ok() == "ns"


def test_build_region_name_missing_identifier():
    from r2x_reeds.getters import build_region_name

    result = build_region_name(SimpleNamespace(), {})
    assert result.is_err()


def test_build_region_name_handles_faulty_get():
    from r2x_reeds.getters import build_region_name

    class FaultyRow:
        def __init__(self, region):
            self.region = region

        def get(self, field):
            raise RuntimeError("boom")

    result = build_region_name(SimpleNamespace(), FaultyRow("south"))
    assert result.is_ok()
    assert result.ok() == "south"


def test_compute_is_dispatchable_matches_category(context_with_regions):
    from r2x_reeds.getters import compute_is_dispatchable

    result = compute_is_dispatchable(context_with_regions, {"technology": "hyd_store"})
    assert result.is_ok()
    assert result.ok() is True


def test_compute_is_dispatchable_defaults_false(context_with_regions):
    from r2x_reeds.getters import compute_is_dispatchable

    result = compute_is_dispatchable(context_with_regions, {"technology": None})
    assert result.is_ok()
    assert result.ok() is False


def test_build_generator_name_includes_vintage():
    from r2x_reeds.getters import build_generator_name

    result = build_generator_name(SimpleNamespace(), {"technology": "wind", "vintage": "v1", "region": "p1"})
    assert result.is_ok()
    assert result.ok() == "wind_v1_p1"


def test_build_generator_name_with_namespace_row():
    from r2x_reeds.getters import build_generator_name

    result = build_generator_name(SimpleNamespace(), SimpleNamespace(technology="gas", region="p1"))
    assert result.is_ok()
    assert result.ok() == "gas_p1"


def test_build_load_and_reserve_names(context_with_regions):
    from r2x_reeds.getters import build_load_name, build_reserve_name

    load_result = build_load_name(context_with_regions, {"region": "p1"})
    reserve_result = build_reserve_name(context_with_regions, {"region": "p1", "reserve_type": "spin"})
    assert load_result.is_ok() and reserve_result.is_ok()
    assert load_result.ok() == "p1_load"
    assert reserve_result.ok() == "p1_spin"


def test_build_load_name_missing_region(context_with_regions):
    from r2x_reeds.getters import build_load_name

    result = build_load_name(context_with_regions, {})
    assert result.is_err()


def test_build_reserve_name_missing_fields(context_with_regions):
    from r2x_reeds.getters import build_reserve_name

    result = build_reserve_name(context_with_regions, {"region": "p1"})
    assert result.is_err()


def test_reserve_type_and_direction_resolution():
    from r2x_reeds.getters import resolve_reserve_direction, resolve_reserve_type
    from r2x_reeds.models import ReserveDirection, ReserveType

    type_result = resolve_reserve_type(SimpleNamespace(), {"reserve_type": "SPINNING"})
    dir_result = resolve_reserve_direction(SimpleNamespace(), {"direction": "up"})
    assert type_result.is_ok() and dir_result.is_ok()
    assert type_result.ok() == ReserveType.SPINNING
    assert dir_result.ok() == ReserveDirection.UP


def test_reserve_type_invalid_raises_err():
    from r2x_reeds.getters import resolve_reserve_type

    result = resolve_reserve_type(SimpleNamespace(), {"reserve_type": "invalid"})
    assert result.is_err()


def test_reserve_direction_missing_errors():
    from r2x_reeds.getters import resolve_reserve_direction

    result = resolve_reserve_direction(SimpleNamespace(), {})
    assert result.is_err()


def test_storage_defaults():
    from r2x_reeds.getters import get_round_trip_efficiency, get_storage_duration

    assert get_storage_duration(SimpleNamespace(), {}).ok() == 1.0
    assert get_round_trip_efficiency(SimpleNamespace(), {}).ok() == 1.0
    assert get_storage_duration(SimpleNamespace(), {"storage_duration": 2}).ok() == 2.0
    assert get_round_trip_efficiency(SimpleNamespace(), {"round_trip_efficiency": 0.9}).ok() == 0.9


def test_fuel_type_known_and_unknown():
    from r2x_reeds.getters import get_fuel_type

    known = get_fuel_type(SimpleNamespace(), {"fuel_type": "NaturalGas"})
    unknown = get_fuel_type(SimpleNamespace(), {"fuel_type": "mystery"})
    assert known.is_ok()
    assert known.ok() == "naturalgas"
    assert unknown.is_err()


def test_get_fuel_type_missing_field_errors():
    from r2x_reeds.getters import get_fuel_type

    result = get_fuel_type(SimpleNamespace(), {})
    assert result.is_err()


def test_emission_type_and_source_resolution():
    from r2x_reeds.getters import resolve_emission_source, resolve_emission_type
    from r2x_reeds.models import EmissionSource

    type_result = resolve_emission_type(SimpleNamespace(), {"emission_type": "co2"})
    source_result = resolve_emission_source(SimpleNamespace(), {"emission_source": None})
    assert type_result.is_ok()
    assert source_result.is_ok()
    assert source_result.ok() == EmissionSource.COMBUSTION


def test_emission_type_unknown_errors():
    from r2x_reeds.getters import resolve_emission_type

    result = resolve_emission_type(SimpleNamespace(), {"emission_type": "unknown"})
    assert result.is_err()


def test_emission_source_unknown_errors():
    from r2x_reeds.getters import resolve_emission_source

    result = resolve_emission_source(SimpleNamespace(), {"emission_source": "mystery"})
    assert result.is_err()


def test_lookup_from_and_to_region(context_with_regions):
    from r2x_reeds.getters import lookup_from_region, lookup_to_region

    from_result = lookup_from_region(context_with_regions, {"from_region": "p1"})
    to_result = lookup_to_region(context_with_regions, {"to_region": "p2"})
    assert from_result.is_ok() and to_result.is_ok()
    assert from_result.ok().name == "p1"
    assert to_result.ok().name == "p2"


def test_lookup_reserve_region_success(context_with_regions):
    from r2x_reeds.getters import lookup_reserve_region

    result = lookup_reserve_region(context_with_regions, {"region": "rsv"})
    assert result.is_ok()
    assert result.ok().name == "rsv"


def test_lookup_reserve_region_missing_field(context_with_regions):
    from r2x_reeds.getters import lookup_reserve_region

    result = lookup_reserve_region(context_with_regions, {})
    assert result.is_err()


def test_lookup_region_missing_field_errors(context_with_regions):
    from r2x_reeds.getters import lookup_to_region

    result = lookup_to_region(context_with_regions, {})
    assert result.is_err()


def test_transmission_interface_and_line_names():
    from r2x_reeds.getters import build_transmission_interface_name, build_transmission_line_name

    interface_result = build_transmission_interface_name(
        SimpleNamespace(), {"from_region": "b", "to_region": "a"}
    )
    line_result = build_transmission_line_name(
        SimpleNamespace(), {"from_region": "a", "to_region": "b", "trtype": "ac"}
    )
    assert interface_result.is_ok() and line_result.is_ok()
    assert interface_result.ok() == "a||b"
    assert line_result.ok() == "a_b_ac"


def test_build_transmission_interface_name_missing_fields():
    from r2x_reeds.getters import build_transmission_interface_name

    result = build_transmission_interface_name(SimpleNamespace(), {"from_region": "p1"})
    assert result.is_err()


def test_build_transmission_line_name_missing_fields():
    from r2x_reeds.getters import build_transmission_line_name

    result = build_transmission_line_name(SimpleNamespace(), {"from_region": "a", "to_region": "b"})
    assert result.is_err()


def test_lookup_transmission_interface(context_with_regions):
    from r2x_reeds.getters import lookup_transmission_interface

    row = {"from_region": "p1", "to_region": "p2"}
    result = lookup_transmission_interface(context_with_regions, row)
    assert result.is_ok()
    assert result.ok().name == "p1||p2"


def test_lookup_transmission_interface_missing_identifiers(context_with_regions):
    from r2x_reeds.getters import lookup_transmission_interface

    row = {"from_region": "p1"}
    result = lookup_transmission_interface(context_with_regions, row)
    assert result.is_err()


def test_build_transmission_flow_with_capacity():
    from r2x_reeds.getters import build_transmission_flow
    from r2x_reeds.models import FromTo_ToFrom

    result = build_transmission_flow(SimpleNamespace(), {"capacity": 100})
    assert result.is_ok()
    flow = result.ok()
    assert isinstance(flow, FromTo_ToFrom)
    assert flow.from_to == flow.to_from == 100.0


def test_build_transmission_flow_with_value_fallback():
    from r2x_reeds.getters import build_transmission_flow

    result = build_transmission_flow(SimpleNamespace(), {"value": 75})
    assert result.is_ok()
    assert result.ok().from_to == 75.0


def test_build_transmission_flow_missing_fields():
    from r2x_reeds.getters import build_transmission_flow

    result = build_transmission_flow(SimpleNamespace(), {})
    assert result.is_err()
