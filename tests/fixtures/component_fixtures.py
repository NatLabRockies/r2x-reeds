"""Component creation fixtures for testing."""

import pytest


@pytest.fixture
def sample_region():
    """Create a sample ReEDS region."""
    from r2x_reeds.models import ReEDSRegion

    return ReEDSRegion(
        name="p1",
        state="CA",
        nerc_region="WECC",
        transmission_region="CA_N",
        interconnect="western",
        country="USA",
    )


@pytest.fixture
def thermal_generator(sample_region):
    """Create a sample thermal generator."""
    from r2x_reeds.models import MinMax, ReEDSThermalGenerator

    return ReEDSThermalGenerator(
        name="gas-cc_init-1_p1",
        region=sample_region,
        technology="gas-cc",
        capacity=500.0,
        heat_rate=7.5,
        fuel_type="naturalgas",
        fuel_price=4.5,
        vom_cost=3.5,
        fom_cost=15000.0,
        capital_cost=1000000.0,
        forced_outage_rate=0.05,
        planned_outage_rate=0.03,
        ramp_rate=0.5,
        min_stable_level=0.4,
        startup_cost=50.0,
        capacity_factor_range=MinMax(min=0.1, max=0.9),
        max_age=40,
        vintage="init-1",
    )


@pytest.fixture
def renewable_generator(sample_region):
    """Create a sample renewable generator."""
    from r2x_reeds.models import ReEDSVariableGenerator

    return ReEDSVariableGenerator(
        name="upv_p1",
        region=sample_region,
        technology="upv",
        capacity=300.0,
        resource_class="class1",
        inverter_loading_ratio=1.3,
        max_capacity_factor=0.4,
        vom_cost=0.0,
        fom_cost=12000.0,
        capital_cost=800000.0,
    )


@pytest.fixture
def storage_generator(sample_region):
    """Create a sample storage generator."""
    from r2x_reeds.models import ReEDSStorage

    return ReEDSStorage(
        name="battery_li_p1",
        region=sample_region,
        technology="battery_li",
        capacity=100.0,
        storage_duration=4.0,
        round_trip_efficiency=0.85,
        energy_capacity=400.0,
        capital_cost=363000.0,
        capital_cost_energy=391.0,
        fom_cost=9080.0,
        fom_cost_energy=9.77,
        vom_cost=0.0,
    )


@pytest.fixture
def hydro_generator(sample_region):
    """Create a sample hydro generator."""
    from r2x_reeds.models import MinMax, ReEDSHydroGenerator

    return ReEDSHydroGenerator(
        name="hyd_p1",
        region=sample_region,
        technology="hyd",
        capacity=200.0,
        is_dispatchable=True,
        flow_range=MinMax(min=0.25, max=1.0),
        ramp_rate=1.0,
        vom_cost=0.0,
        fom_cost=18000.0,
    )


@pytest.fixture
def consuming_technology(sample_region):
    """Create a sample consuming technology."""
    from r2x_reeds.models import ReEDSConsumingTechnology

    return ReEDSConsumingTechnology(
        name="electrolyzer_p1",
        region=sample_region,
        technology="electrolyzer",
        capacity=150.0,
        capital_cost=788000.0,
        fom_cost=27500.0,
        vom_cost=0.0,
        electricity_efficiency=51.45,
        storage_transport_adder=390000.0,
    )


@pytest.fixture
def h2_storage(sample_region):
    """Create a sample H2 storage."""
    from r2x_reeds.models import ReEDSH2Storage

    return ReEDSH2Storage(
        name="h2_storage_saltcavern_p1",
        region=sample_region,
        storage_type="saltcavern",
        capacity=1000.0,
        capital_cost=26304.0,
        fom_cost=763.0,
        parasitic_load=0.008,
    )


@pytest.fixture
def h2_pipeline(sample_region):
    """Create a sample H2 pipeline."""
    from r2x_reeds.models import ReEDSH2Pipeline

    region2 = sample_region.model_copy(update={"name": "p2"})
    return ReEDSH2Pipeline(
        name="h2_pipeline_p1_p2",
        from_region=sample_region,
        to_region=region2,
        capacity=500.0,
        distance_km=100.0,
        capital_cost_per_km=34045.0,
        fom_cost_per_km=963.0,
    )


@pytest.fixture
def emission():
    """Create a sample emission attribute."""
    from r2x_reeds.models import EmissionSource, EmissionType, ReEDSEmission

    return ReEDSEmission(rate=0.45, source=EmissionSource.COMBUSTION, type=EmissionType.CO2)
