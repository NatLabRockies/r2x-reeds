"""Tests for technology-specific component models."""

import pytest
from pydantic import ValidationError


def test_thermal_generator_requires_heat_rate(sample_region):
    from r2x_reeds.models.components import ReEDSThermalGenerator

    with pytest.raises(ValidationError) as exc_info:
        ReEDSThermalGenerator(
            name="test",
            region=sample_region,
            technology="gas-cc",
            capacity=100.0,
            fuel_type="naturalgas",
        )
    assert "heat_rate" in str(exc_info.value)


def test_thermal_generator_requires_fuel_type(sample_region):
    from r2x_reeds.models.components import ReEDSThermalGenerator

    with pytest.raises(ValidationError) as exc_info:
        ReEDSThermalGenerator(
            name="test",
            region=sample_region,
            technology="gas-cc",
            capacity=100.0,
            heat_rate=7.5,
        )
    assert "fuel_type" in str(exc_info.value)


def test_storage_generator_requires_duration(sample_region):
    from r2x_reeds.models.components import ReEDSStorage

    with pytest.raises(ValidationError) as exc_info:
        ReEDSStorage(
            name="test",
            region=sample_region,
            technology="battery_li",
            capacity=100.0,
            round_trip_efficiency=0.85,
        )
    assert "storage_duration" in str(exc_info.value)


def test_storage_generator_requires_efficiency(sample_region):
    from r2x_reeds.models.components import ReEDSStorage

    with pytest.raises(ValidationError) as exc_info:
        ReEDSStorage(
            name="test",
            region=sample_region,
            technology="battery_li",
            capacity=100.0,
            storage_duration=4.0,
        )
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

    with pytest.raises(ValidationError) as exc_info:
        ReEDSHydroGenerator(
            name="test",
            region=sample_region,
            technology="hyd",
            capacity=200.0,
        )
    assert "is_dispatchable" in str(exc_info.value)


def test_consuming_tech_requires_electricity_efficiency(sample_region):
    from r2x_reeds.models.components import ReEDSConsumingTechnology

    with pytest.raises(ValidationError) as exc_info:
        ReEDSConsumingTechnology(
            name="test",
            region=sample_region,
            technology="electrolyzer",
            capacity=100.0,
        )
    assert "electricity_efficiency" in str(exc_info.value)


def test_h2_storage_requires_storage_type(sample_region):
    from r2x_reeds.models.components import ReEDSH2Storage

    with pytest.raises(ValidationError) as exc_info:
        ReEDSH2Storage(
            name="test",
            region=sample_region,
            capacity=1000.0,
        )
    assert "storage_type" in str(exc_info.value)


def test_h2_pipeline_requires_distance(sample_region):
    from r2x_reeds.models.components import ReEDSH2Pipeline

    with pytest.raises(ValidationError) as exc_info:
        ReEDSH2Pipeline(
            name="test",
            from_region=sample_region,
            to_region=sample_region,
            capacity=500.0,
        )
    assert "distance_km" in str(exc_info.value)


def test_thermal_generator_valid(thermal_generator):
    assert thermal_generator.heat_rate == 7.5
    assert thermal_generator.fuel_type == "naturalgas"
    assert thermal_generator.ramp_rate == 0.5
    assert thermal_generator.startup_cost == 50.0


def test_renewable_generator_valid(renewable_generator):
    assert renewable_generator.technology == "upv"
    assert renewable_generator.inverter_loading_ratio == 1.3
    assert renewable_generator.resource_class == "class1"


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
