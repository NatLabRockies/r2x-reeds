"""Public parser output coverage for linked ReEDS components and emissions."""

import pytest

from r2x_reeds.models.components import (
    ReEDSDemand,
    ReEDSEmission,
    ReEDSGenerator,
    ReEDSInterface,
    ReEDSRegion,
    ReEDSTransmissionLine,
)

pytestmark = [pytest.mark.integration, pytest.mark.polars]


def test_public_lifecycle_builds_regions_transmission_and_emission_outputs(example_system) -> None:
    """The declarative build retains linked Pacific outputs and generator emissions."""
    system = example_system
    regions = {region.name: region for region in system.get_components(ReEDSRegion)}
    demands = list(system.get_components(ReEDSDemand))
    interfaces = list(system.get_components(ReEDSInterface))
    lines = list(system.get_components(ReEDSTransmissionLine))
    generators = list(system.get_components(ReEDSGenerator))

    assert len(regions) == 11
    assert len(demands) == 11
    assert len(interfaces) == 17
    assert len(lines) == 17
    assert all(demand.region is regions[demand.region.name] for demand in demands)
    assert all(interface.from_region is regions[interface.from_region.name] for interface in interfaces)
    assert all(line.interface in interfaces for line in lines)

    line = system.get_component(ReEDSTransmissionLine, "p1_p2_ac")
    assert line.distance_miles == pytest.approx(132.46)
    assert line.line_cost_per_mw_mile == pytest.approx(2255.418390457496)
    assert line.losses == pytest.approx(0.01325)
    assert line.max_active_power.from_to == pytest.approx(9226.461)
    assert line.max_active_power.to_from == pytest.approx(4588.725)

    emissions = [
        attribute
        for generator in generators
        for attribute in system.get_supplemental_attributes_with_component(generator, ReEDSEmission)
    ]
    assert len(emissions) == 948
