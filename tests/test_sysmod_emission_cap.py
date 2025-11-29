from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest
from infrasys import System

from r2x_reeds.models.components import ReEDSEmission, ReEDSGenerator, ReEDSRegion
from r2x_reeds.models.enums import EmissionType
from r2x_reeds.sysmod import emission_cap


def _build_system() -> tuple[System, ReEDSRegion]:
    system = System(name="test_emission_cap")
    region = ReEDSRegion(name="west")
    system.add_component(region)
    return system, region


def _add_generator(
    system: System,
    region: ReEDSRegion,
    name: str,
    technology: str = "coal",
    category: str = "coal",
    vintage: str | None = "2010",
) -> ReEDSGenerator:
    generator = ReEDSGenerator(
        name=name,
        region=region,
        technology=technology,
        capacity=150.0,
        category=category,
        vintage=vintage,
    )
    system.add_component(generator)
    return generator


def _attach_emission(system: System, generator: ReEDSGenerator, rate: float = 1.0) -> None:
    system.add_supplemental_attribute(generator, ReEDSEmission(rate=rate, type=EmissionType.CO2))


def _write_csv(path: Path, data: dict[str, list]) -> str:
    pl.DataFrame(data).write_csv(path)
    return str(path)


@pytest.mark.parametrize("with_ext", [False, True])
def test_emission_cap_scope(tmp_path: Path, with_ext: bool) -> None:
    """Integrates add_emission_cap end-to-end using real CSV inputs."""
    system, region = _build_system()
    if with_ext:
        system.ext = {}

    generator_name = "coal_2010_west"
    generator = _add_generator(system, region, generator_name)
    _attach_emission(system, generator)

    co2_cap_path = _write_csv(tmp_path / "co2_cap.csv", {"value": [1250.0]})
    switches_path = _write_csv(
        tmp_path / "switches.csv",
        {
            "switch_name": ["gsw_precombustion", "other_switch"],
            "value": ["True", "False"],
        },
    )
    emission_rates_path = _write_csv(
        tmp_path / "emission_rates.csv",
        {
            "tech": ["coal", "coal"],
            "tech_vintage": ["2010", "2010"],
            "region": ["west", "west"],
            "emission_source": ["precombustion_fuel", "combustion"],
            "emission_type": ["CO2", "CO2"],
            "rate": [0.3, 0.1],
        },
    )

    emission_cap.add_emission_cap(
        system,
        emission_cap=None,
        switches_fpath=switches_path,
        emission_rates_fpath=emission_rates_path,
        co2_cap_fpath=co2_cap_path,
    )

    storage = system.ext["emission_constraints"] if with_ext else system._emission_constraints
    constraint = storage["Annual_EmissionType.CO2_cap"]
    assert constraint["rhs_value"] == 1250.0
    assert constraint["units"] == "tonne"

    emission_attr = system.get_supplemental_attributes_with_component(generator, ReEDSEmission)[0]
    assert emission_attr.rate == pytest.approx(1.3)


def test_emission_cap_scope_missing_emissions(caplog) -> None:
    """When the system lacks emission attributes the plugin bails out early."""
    system, region = _build_system()
    _add_generator(system, region, "coal_2010_west")

    emission_cap.add_emission_cap(system, emission_cap=500.0)

    assert "Did not find any emission type" in caplog.text
    assert not hasattr(system, "_emission_constraints")


@pytest.mark.parametrize(
    "switch_input",
    [
        pl.DataFrame({"switch_name": ["gsw_precombustion"], "value": ["True"]}),
        pl.DataFrame({"flag": ["gsw_annualcapco2e"], "state": ["yes"]}),
        {"gsw_annualcapco2e": True},
    ],
)
def test_precombustion_scope(switch_input) -> None:
    """Switch-controlled precombustion addition updates generator emission rates."""
    system, region = _build_system()
    generator = _add_generator(system, region, "tech_2020_west", technology="tech")
    _attach_emission(system, generator)

    emit_rates = pl.DataFrame(
        {
            "tech": ["tech", "tech"],
            "tech_vintage": ["2020", "2020"],
            "region": ["west", "west"],
            "emission_source": ["precombustion", "combustion"],
            "emission_type": ["CO2", "CO2"],
            "rate": [0.5, 0.1],
        }
    )

    emission_cap._add_precombustion_if_enabled(system, switch_input, emit_rates)

    emission_attr = system.get_supplemental_attributes_with_component(generator, ReEDSEmission)[0]
    assert emission_attr.rate == pytest.approx(1.5)


def test_precombustion_rates_scope() -> None:
    """add_precombustion increments matched emission attributes and skips invalid rows."""
    system, region = _build_system()
    generator = _add_generator(system, region, "GEN_PRECOMB")
    _attach_emission(system, generator)

    emission_rates = pl.DataFrame(
        {
            "generator_name": ["GEN_PRECOMB", "GEN_PRECOMB", "MISSING"],
            "emission_type": ["co2", "unknown", "co2"],
            "rate": [0.3, 0.1, 0.2],
        }
    )

    applied = emission_cap.add_precombustion(system, emission_rates)
    assert applied is True

    emissions = system.get_supplemental_attributes_with_component(generator, ReEDSEmission)
    assert emissions[0].rate == pytest.approx(1.3)


def test_precombustion_scope_duplicate_attributes() -> None:
    """Duplicate emission attributes raise so callers know system data is inconsistent."""
    system, region = _build_system()
    generator = _add_generator(system, region, "GEN_DUPLICATE")
    _attach_emission(system, generator)
    _attach_emission(system, generator)

    emission_rates = pl.DataFrame(
        {"generator_name": ["GEN_DUPLICATE"], "emission_type": ["CO2"], "rate": [0.1]}
    )

    with pytest.raises(ValueError):
        emission_cap.add_precombustion(system, emission_rates)


def test_emission_constraint_scope(caplog) -> None:
    """set_emission_constraint returns early when no cap is provided."""
    system, _ = _build_system()

    emission_cap.set_emission_constraint(system, emission_cap=None)

    assert "Could not set emission cap value" in caplog.text
    assert not hasattr(system, "_emission_constraints")
