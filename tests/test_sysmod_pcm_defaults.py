from __future__ import annotations

import json
from pathlib import Path

import pytest
from infrasys import System

from r2x_reeds.models.components import ReEDSGenerator, ReEDSRegion
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


def test_pcm_defaults_scope_from_dict() -> None:
    """PCM defaults dictionary populates missing generator fields."""
    system, generator = _build_generator()
    defaults = {"coal": {"heat_rate": 9.0, "vom_cost": 2.5}}

    pcm_defaults.add_pcm_defaults(system, pcm_defaults_dict=defaults)

    assert generator.heat_rate == pytest.approx(9.0)
    assert generator.vom_cost == pytest.approx(2.5)


def test_pcm_defaults_scope_override() -> None:
    """Override flag replaces existing values."""
    system, generator = _build_generator()
    generator.vom_cost = 1.0

    pcm_defaults.add_pcm_defaults(
        system,
        pcm_defaults_dict={"coal": {"vom_cost": 3.0}},
        pcm_defaults_override=True,
    )

    assert generator.vom_cost == pytest.approx(3.0)


def test_pcm_defaults_scope_file(tmp_path: Path) -> None:
    """Defaults can be loaded from JSON files via DataStore."""
    system, generator = _build_generator()
    defaults = {"GEN1": {"fuel_price": 4.5}}
    json_path = tmp_path / "pcm_defaults.json"
    json_path.write_text(json.dumps(defaults))

    pcm_defaults.add_pcm_defaults(system, pcm_defaults_fpath=str(json_path))

    assert generator.fuel_price == pytest.approx(4.5)


def test_pcm_defaults_scope_no_inputs(caplog) -> None:
    """Without dict or file path the plugin exits early with a warning."""
    system, _ = _build_generator()

    pcm_defaults.add_pcm_defaults(system)

    assert "No PCM defaults file path or dict provided" in caplog.text


def test_pcm_defaults_scope_no_match(caplog) -> None:
    """Generators without matching categories are skipped."""
    system, generator = _build_generator(category="gas")

    pcm_defaults.add_pcm_defaults(system, pcm_defaults_dict={"coal": {"heat_rate": 9.0}})

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

    pcm_defaults.add_pcm_defaults(system, pcm_defaults_dict=defaults)
    assert generator.ext == {}
