from __future__ import annotations

import json
from pathlib import Path

import pytest
from infrasys import System

from r2x_reeds.models.components import (
    ReEDSGenerator,
    ReEDSHydroGenerator,
    ReEDSRegion,
    ReEDSThermalGenerator,
)
from r2x_reeds.sysmod import pcm_defaults

pytestmark = [pytest.mark.integration]


def _build_generator(name: str = "GEN1", category: str = "coal") -> tuple[System, ReEDSGenerator]:
    system = System(name="test_pcm_defaults")
    region = ReEDSRegion(name="west")
    system.add_component(region)
    generator = ReEDSGenerator(
        name=name, region=region, capacity=100.0, technology=category, category=category
    )
    system.add_component(generator)
    return system, generator


def _build_thermal_generator(
    name: str = "GEN1", category: str = "coal"
) -> tuple[System, ReEDSThermalGenerator]:
    system = System(name="test_pcm_defaults")
    region = ReEDSRegion(name="west")
    system.add_component(region)
    generator = ReEDSThermalGenerator(
        name=name,
        region=region,
        capacity=100.0,
        technology=category,
        category=category,
        heat_rate=9.0,
        fuel_type=category,
    )
    system.add_component(generator)
    return system, generator


def _build_hydro_generator(name: str = "GEN1", category: str = "hydro") -> tuple[System, ReEDSHydroGenerator]:
    system = System(name="test_pcm_defaults")
    region = ReEDSRegion(name="west")
    system.add_component(region)
    generator = ReEDSHydroGenerator(
        name=name,
        region=region,
        capacity=100.0,
        technology=category,
        category=category,
        is_dispatchable=True,
    )
    system.add_component(generator)
    return system, generator


def _run_pcm_defaults(system: System, **kwargs) -> System:
    result = pcm_defaults.add_pcm_defaults(system, pcm_defaults.PCMDefaultsConfig(**kwargs))
    assert result.is_ok()
    return result.unwrap()


def test_pcm_defaults_scope_from_dict() -> None:
    """PCM defaults dictionary populates missing generator fields."""
    system, generator = _build_generator()
    defaults = {"coal": {"heat_rate": 9.0, "vom_cost": 2.5}}

    _run_pcm_defaults(system, pcm_defaults_dict=defaults)

    assert generator.heat_rate == pytest.approx(9.0)
    assert generator.vom_cost == pytest.approx(2.5)


def test_pcm_defaults_scope_override() -> None:
    """Override flag replaces existing values."""
    system, generator = _build_generator()
    generator.vom_cost = 1.0

    _run_pcm_defaults(
        system,
        pcm_defaults_dict={"coal": {"vom_cost": 3.0}},
        pcm_defaults_override=True,
    )

    assert generator.vom_cost == pytest.approx(3.0)


def test_pcm_defaults_scope_file(tmp_path: Path) -> None:
    """Defaults can be loaded from a JSON file."""
    system, generator = _build_generator()
    defaults = {"GEN1": {"fuel_price": 4.5}}
    json_path = tmp_path / "pcm_defaults.json"
    json_path.write_text(json.dumps(defaults))

    _run_pcm_defaults(system, pcm_defaults_fpath=str(json_path))

    assert generator.fuel_price == pytest.approx(4.5)


def test_pcm_defaults_scope_file_list_format(tmp_path: Path) -> None:
    """Defaults loaded from a JSON list (name-keyed objects) are parsed correctly."""
    system, generator = _build_generator()
    defaults = [
        {"name": "GEN1", "heat_rate": 8.5, "vom_cost": 3.0},
        {"name": "other", "heat_rate": 10.0},
    ]
    json_path = tmp_path / "pcm_defaults.json"
    json_path.write_text(json.dumps(defaults))

    _run_pcm_defaults(system, pcm_defaults_fpath=str(json_path))

    assert generator.heat_rate == pytest.approx(8.5)
    assert generator.vom_cost == pytest.approx(3.0)


def test_pcm_defaults_missing_configured_file_preserves_error(tmp_path: Path) -> None:
    system, _ = _build_generator()
    result = pcm_defaults.add_pcm_defaults(
        system,
        pcm_defaults.PCMDefaultsConfig(pcm_defaults_fpath=tmp_path / "missing.json"),
    )

    assert result.is_err()
    assert isinstance(result.unwrap_err(), FileNotFoundError)


def test_pcm_defaults_scope_no_inputs(caplog) -> None:
    """Without dict or file path the plugin exits early with a warning."""
    system, _ = _build_generator()

    _run_pcm_defaults(system)

    assert "No PCM defaults file path or dict provided" in caplog.text


def test_pcm_defaults_scope_no_match(caplog) -> None:
    """Generators without matching categories are skipped."""
    system, generator = _build_generator(category="gas")

    _run_pcm_defaults(system, pcm_defaults_dict={"coal": {"heat_rate": 9.0}})

    assert generator.heat_rate is None
    assert "Could not find a matching category" in caplog.text


def test_pcm_defaults_scope_multiplication_runs() -> None:
    """Multiplication logic for complex values executes without raising."""
    system, generator = _build_generator()
    defaults = {
        "coal": {
            "start_cost_per_MW": {"a": 1.0},
            "ramp_limits": {"up": 0.2, "down": 0.2},
        }
    }

    _run_pcm_defaults(system, pcm_defaults_dict=defaults)
    assert generator.ext == {}


def test_pcm_defaults_ramp_rate_is_multiplied_thermal() -> None:
    """ramp_rate on a thermal generator is scaled by capacity, not applied as-is."""
    system, generator = _build_thermal_generator()

    _run_pcm_defaults(system, pcm_defaults_dict={"coal": {"ramp_rate": 0.01}})

    assert generator.ramp_rate == pytest.approx(100.0 * 0.01)


def test_pcm_defaults_ramp_rate_is_multiplied_hydro() -> None:
    """ramp_rate on a hydro generator is scaled by capacity, not applied as-is."""
    system, generator = _build_hydro_generator()

    _run_pcm_defaults(system, pcm_defaults_dict={"hydro": {"ramp_rate": 0.3}})

    assert generator.ramp_rate == pytest.approx(100.0 * 0.3)


@pytest.mark.parametrize("capacity", [100.0, 320.0])
@pytest.mark.parametrize(
    ("startup_cost", "override", "expected"),
    [(None, False, 79.0), (None, True, 79.0), (68.0, False, 68.0), (68.0, True, 79.0)],
)
def test_pcm_defaults_preserve_startup_cost_per_mw(
    capacity: float, startup_cost: float | None, override: bool, expected: float
) -> None:
    system, generator = _build_thermal_generator(category="gas-cc")
    generator.capacity = capacity
    generator.startup_cost = startup_cost

    _run_pcm_defaults(
        system,
        pcm_defaults_dict={"gas-cc": {"startup_cost": 79.0}},
        pcm_defaults_override=override,
    )

    assert generator.startup_cost == expected
