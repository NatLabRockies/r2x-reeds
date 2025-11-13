from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from infrasys import System
from infrasys.time_series_models import SingleTimeSeries

from r2x_reeds.models.components import ReEDSEmission, ReEDSGenerator, ReEDSRegion
from r2x_reeds.models.enums import EmissionType
from r2x_reeds.sysmod import break_gens


def _build_system() -> tuple[System, ReEDSRegion]:
    system = System(name="test_break_gens")
    region = ReEDSRegion(name="west")
    system.add_component(region)
    return system, region


def _add_generator(
    system: System,
    region: ReEDSRegion,
    name: str,
    category: str,
    capacity: float,
) -> ReEDSGenerator:
    generator = ReEDSGenerator(
        name=name,
        region=region,
        technology=category,
        capacity=capacity,
        category=category,
    )
    system.add_component(generator)
    return generator


def _attach_defaults(system: System, generator: ReEDSGenerator) -> None:
    system.add_supplemental_attribute(generator, ReEDSEmission(rate=1.0, emission_type=EmissionType.CO2))
    ts = SingleTimeSeries.from_array(
        data=[10.0, 12.0],
        name="fixed_load",
        initial_timestamp=datetime(year=2024, month=1, day=1),
        resolution=timedelta(hours=1),
    )
    system.add_time_series(ts, generator)


def test_break_generators_splits_and_preserves_data() -> None:
    system, region = _build_system()
    generator = _add_generator(system, region, "coal_big", "coal", 110.0)
    _attach_defaults(system, generator)

    reference = {"coal": {"avg_capacity_MW": 40}}

    break_gens.break_generators(system, reference, capacity_threshold=5)

    names = {comp.name for comp in system.get_components(ReEDSGenerator)}
    assert "coal_big" not in names
    assert {"coal_big_01", "coal_big_02", "coal_big_03"}.issubset(names)

    split = system.get_component(ReEDSGenerator, "coal_big_01")
    assert split.capacity == pytest.approx(40.0)
    assert system.has_time_series(split)
    attrs = system.get_supplemental_attributes_with_component(split, ReEDSEmission)
    assert attrs[0].rate == pytest.approx(1.0)


def test_break_generators_drops_small_remainder() -> None:
    system, region = _build_system()
    _add_generator(system, region, "coal_small_rem", "coal", 82.0)
    reference = {"coal": {"avg_capacity_MW": 40}}

    break_gens.break_generators(system, reference, capacity_threshold=5)

    names = {comp.name for comp in system.get_components(ReEDSGenerator)}
    assert {"coal_small_rem_01", "coal_small_rem_02"}.issubset(names)
    assert all("coal_small_rem_03" not in name for name in names)


def test_break_generators_respects_non_break_list() -> None:
    system, region = _build_system()
    generator = _add_generator(system, region, "wind_resource", "wind", 150.0)
    reference = {"wind": {"avg_capacity_MW": 40}}

    break_gens.break_generators(system, reference, capacity_threshold=5, non_break_techs=["wind_resource"])

    assert system.get_component(ReEDSGenerator, generator.name).capacity == pytest.approx(150.0)


def test_break_gens_uses_reference_dict(tmp_path: Path) -> None:
    system, region = _build_system()
    _add_generator(system, region, "coal_big", "coal", 120.0)
    reference = {"coal": {"avg_capacity_MW": 40}}

    break_gens.break_gens(system, pcm_defaults_dict=reference)

    assert system.get_component(ReEDSGenerator, "coal_big_01").capacity == pytest.approx(40.0)


def test_break_gens_reads_file(tmp_path: Path) -> None:
    system, region = _build_system()
    _add_generator(system, region, "coal_file", "coal", 80.0)

    reference = {"coal": {"avg_capacity_MW": 30}}
    json_path = tmp_path / "pcm_defaults.json"
    json_path.write_text(json.dumps(reference))

    break_gens.break_gens(system, pcm_defaults_fpath=str(json_path))

    names = {comp.name for comp in system.get_components(ReEDSGenerator)}
    assert {"coal_file_01", "coal_file_02"}.issubset(names)


def test_break_generators_skips_missing_category() -> None:
    system, region = _build_system()
    generator = _add_generator(system, region, "coal_miss_cat", None, 120.0)

    break_gens.break_generators(system, {"coal": {"avg_capacity_MW": 40}}, non_break_techs=[])

    assert system.get_component(ReEDSGenerator, generator.name).capacity == pytest.approx(120.0)


def test_break_generators_missing_reference() -> None:
    system, region = _build_system()
    generator = _add_generator(system, region, "coal_noref", "coal", 120.0)

    break_gens.break_generators(system, reference_generators={}, capacity_threshold=5)

    assert system.get_component(ReEDSGenerator, generator.name).capacity == pytest.approx(120.0)


def test_break_generators_missing_avg_capacity(caplog) -> None:
    system, region = _build_system()
    generator = _add_generator(system, region, "coal_noavg", "coal", 120.0)

    break_gens.break_generators(system, {"coal": {}}, capacity_threshold=5)

    assert system.get_component(ReEDSGenerator, generator.name).capacity == pytest.approx(120.0)
    assert "average_capacity" not in caplog.text.lower()


def test_break_generators_small_capacity_not_split() -> None:
    system, region = _build_system()
    generator = _add_generator(system, region, "coal_small", "coal", 30.0)
    reference = {"coal": {"avg_capacity_MW": 40}}

    break_gens.break_generators(system, reference, capacity_threshold=5)

    assert system.get_component(ReEDSGenerator, generator.name).capacity == pytest.approx(30.0)
