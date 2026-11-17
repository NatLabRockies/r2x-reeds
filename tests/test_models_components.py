"""Tests for technology-specific component models."""

from typing import Any

import pytest
from pydantic import ValidationError

from r2x_core import System
from r2x_core.units import UnitSpec
from r2x_reeds import ReEDSResourceBuild, ReEDSResourceClass, ReEDSResourceSite
from r2x_reeds.models import (
    ReEDSResourceBuild as ModelsReEDSResourceBuild,
)
from r2x_reeds.models import (
    ReEDSResourceClass as ModelsReEDSResourceClass,
)
from r2x_reeds.models import (
    ReEDSResourceSite as ModelsReEDSResourceSite,
)

pytestmark = [pytest.mark.unit]


def test_thermal_generator_requires_heat_rate(sample_region):
    from r2x_reeds.models.components import ReEDSThermalGenerator

    bad_input: dict[str, Any] = {
        "name": "test",
        "region": sample_region,
        "technology": "gas-cc",
        "capacity": 100.0,
        "fuel_type": "naturalgas",
    }
    with pytest.raises(ValidationError) as exc_info:
        ReEDSThermalGenerator(**bad_input)
    assert "heat_rate" in str(exc_info.value)


def test_thermal_generator_requires_fuel_type(sample_region):
    from r2x_reeds.models.components import ReEDSThermalGenerator

    bad_input: dict[str, Any] = {
        "name": "test",
        "region": sample_region,
        "technology": "gas-cc",
        "capacity": 100.0,
        "heat_rate": 7.5,
    }
    with pytest.raises(ValidationError) as exc_info:
        ReEDSThermalGenerator(**bad_input)
    assert "fuel_type" in str(exc_info.value)


def test_storage_generator_requires_duration(sample_region):
    from r2x_reeds.models.components import ReEDSStorage

    bad_input: dict[str, Any] = {
        "name": "test",
        "region": sample_region,
        "technology": "battery_li",
        "capacity": 100.0,
        "round_trip_efficiency": 0.85,
    }
    with pytest.raises(ValidationError) as exc_info:
        ReEDSStorage(**bad_input)
    assert "storage_duration" in str(exc_info.value)


def test_storage_generator_requires_efficiency(sample_region):
    from r2x_reeds.models.components import ReEDSStorage

    bad_input: dict[str, Any] = {
        "name": "test",
        "region": sample_region,
        "technology": "battery_li",
        "capacity": 100.0,
        "storage_duration": 4.0,
    }
    with pytest.raises(ValidationError) as exc_info:
        ReEDSStorage(**bad_input)
    assert "round_trip_efficiency" in str(exc_info.value)


def test_storage_efficiency_bounded(sample_region):
    from r2x_reeds.models.components import ReEDSStorage

    with pytest.raises(ValidationError):
        ReEDSStorage(
            name="test",
            region=sample_region,
            technology="battery_li",
            capacity=100.0,
            storage_duration=4.0,
            round_trip_efficiency=1.5,
        )


def test_hydro_generator_requires_dispatchable_flag(sample_region):
    from r2x_reeds.models.components import ReEDSHydroGenerator

    bad_input: dict[str, Any] = {
        "name": "test",
        "region": sample_region,
        "technology": "hyd",
        "capacity": 200.0,
    }
    with pytest.raises(ValidationError) as exc_info:
        ReEDSHydroGenerator(**bad_input)
    assert "is_dispatchable" in str(exc_info.value)


def test_consuming_tech_requires_electricity_efficiency(sample_region):
    from r2x_reeds.models.components import ReEDSConsumingTechnology

    bad_input: dict[str, Any] = {
        "name": "test",
        "region": sample_region,
        "technology": "electrolyzer",
        "capacity": 100.0,
    }
    with pytest.raises(ValidationError) as exc_info:
        ReEDSConsumingTechnology(**bad_input)
    assert "electricity_efficiency" in str(exc_info.value)


def test_h2_storage_requires_storage_type(sample_region):
    from r2x_reeds.models.components import ReEDSH2Storage

    bad_input: dict[str, Any] = {
        "name": "test",
        "region": sample_region,
        "capacity": 1000.0,
    }
    with pytest.raises(ValidationError) as exc_info:
        ReEDSH2Storage(**bad_input)
    assert "storage_type" in str(exc_info.value)


def test_h2_pipeline_requires_distance(sample_region):
    from r2x_reeds.models.components import ReEDSH2Pipeline

    bad_input: dict[str, Any] = {
        "name": "test",
        "from_region": sample_region,
        "to_region": sample_region,
        "capacity": 500.0,
    }
    with pytest.raises(ValidationError) as exc_info:
        ReEDSH2Pipeline(**bad_input)
    assert "distance_km" in str(exc_info.value)


def test_thermal_generator_valid(thermal_generator):
    assert thermal_generator.heat_rate == 7.5
    assert thermal_generator.fuel_type == "naturalgas"
    assert thermal_generator.ramp_rate == 0.5
    assert thermal_generator.startup_cost == 50.0


@pytest.mark.parametrize("fixture_name", ["thermal_generator", "hydro_generator"])
@pytest.mark.parametrize("ramp_rate", [None, 0.05, 1.0, 3.0])
def test_generator_ramp_rate_units_and_json_round_trip(request, fixture_name, ramp_rate, tmp_path):
    generator = request.getfixturevalue(fixture_name)
    generator.ramp_rate = ramp_rate
    specs = [
        metadata
        for metadata in type(generator).model_fields["ramp_rate"].metadata
        if isinstance(metadata, UnitSpec)
    ]
    assert len(specs) == 1
    assert specs[0].unit == "fraction/min"
    assert specs[0].base is None

    system = System(name="ramp-round-trip", auto_add_composed_components=True)
    system.add_component(generator)
    path = tmp_path / "system.json"
    system.to_json(path)
    restored_system = System.from_json(path)
    restored = restored_system.get_component(type(generator), generator.name)

    assert restored.ramp_rate == ramp_rate
    assert restored.capacity == generator.capacity


def test_renewable_generator_valid(renewable_generator):
    assert renewable_generator.technology == "upv"
    assert renewable_generator.inverter_loading_ratio == 1.3
    assert renewable_generator.resource_class == "class1"


def test_resource_site_valid_and_exported(sample_region):
    assert ReEDSResourceSite is ModelsReEDSResourceSite
    assert ReEDSResourceClass is ModelsReEDSResourceClass

    site = ReEDSResourceSite(
        name="upv_1_416",
        technology="upv",
        region=sample_region,
        sc_point_gid=416,
        resource_class="1",
        capacity=341.13,
        available_capacity=254.58,
        capacity_factor=0.1877,
        supply_curve_cost=577564.52875,
    )

    assert site.region == sample_region
    assert site.sc_point_gid == 416
    assert site.resource_class == "1"
    assert site.capacity == 341.13
    assert site.available_capacity == 254.58
    assert site.capacity_factor == 0.1877
    assert site.supply_curve_cost == 577564.52875


def test_resource_build_valid_and_exported(sample_region):
    assert ReEDSResourceBuild is ModelsReEDSResourceBuild

    build = ReEDSResourceBuild(
        name="upv_1_2009_416",
        technology="upv",
        region=sample_region,
        sc_point_gid=416,
        resource_class="1",
        year=2009,
        built_capacity=0.3731343025384888,
        investment_bool=True,
        capacity=341.13,
        available_capacity=254.58,
        capacity_factor=0.1877,
        supply_curve_cost=577564.52875,
    )

    assert build.year == 2009
    assert build.built_capacity == 0.3731343025384888
    assert build.investment_bool is True
    assert build.sc_point_gid == 416
    assert build.supply_curve_cost == 577564.52875


def test_storage_generator_valid(storage_generator):
    assert storage_generator.storage_duration == 4.0
    assert storage_generator.round_trip_efficiency == 0.85
    assert storage_generator.energy_capacity == 400.0


def test_hydro_generator_valid(hydro_generator):
    assert hydro_generator.is_dispatchable is True
    assert hydro_generator.flow_range.min == 0.25
    assert hydro_generator.ramp_rate == 1.0


def test_consuming_technology_valid(consuming_technology):
    assert consuming_technology.electricity_efficiency == 51.45
    assert consuming_technology.storage_transport_adder == 390000.0


def test_emission_optional_pollutants():
    from r2x_reeds.models.components import ReEDSEmission
    from r2x_reeds.models.enums import EmissionSource, EmissionType

    emission = ReEDSEmission(rate=0.45, type=EmissionType.CO2)
    assert emission.rate == 0.45
    assert emission.type == EmissionType.CO2
    assert emission.source == EmissionSource.COMBUSTION


def test_base_generator_inheritance(thermal_generator):
    from r2x_reeds.models.components import ReEDSGenerator

    assert isinstance(thermal_generator, ReEDSGenerator)
    assert thermal_generator.capacity == 500.0
    assert thermal_generator.region.name == "p1"


def test_generator_negative_capacity_invalid(sample_region):
    from r2x_reeds.models.components import ReEDSThermalGenerator

    with pytest.raises(ValidationError):
        ReEDSThermalGenerator(
            name="test",
            region=sample_region,
            technology="gas-cc",
            capacity=-100.0,
            heat_rate=7.5,
            fuel_type="naturalgas",
        )


def test_generator_outage_rate_bounded(sample_region):
    from r2x_reeds.models.components import ReEDSThermalGenerator

    with pytest.raises(ValidationError):
        ReEDSThermalGenerator(
            name="test",
            region=sample_region,
            technology="gas-cc",
            capacity=100.0,
            heat_rate=7.5,
            fuel_type="naturalgas",
            forced_outage_rate=1.5,
        )
