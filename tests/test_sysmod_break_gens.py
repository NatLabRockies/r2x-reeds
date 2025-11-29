from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from infrasys import SingleTimeSeries, System

from r2x_reeds.models.components import ReEDSEmission, ReEDSGenerator
from r2x_reeds.models.enums import EmissionType
from r2x_reeds.sysmod.break_gens import break_generators


@pytest.fixture
def system_with_region(sample_region):
    system = System(name="Test")
    system.add_component(sample_region)
    return system, sample_region


def test_break_generator_fails_with_wrong_reference_type():
    sys = System(name="Test")

    with pytest.raises(TypeError):
        break_generators(sys, 10)


def test_break_generator_fails_with_missing_file(tmp_path: Path):
    sys = System(name="Test")
    missing = tmp_path / "missing.json"

    with pytest.raises(FileNotFoundError):
        break_generators(sys, missing)


def test_break_generator_warns_on_duplicate_reference(tmp_path: Path, caplog):
    """Ensure duplicate entries in reference files log a warning but do not crash."""
    import json

    class DummySystem:
        def get_components(self, *_args, **_kwargs):
            return []

    sys = DummySystem()
    reference_path = tmp_path / "pcm_defaults.json"
    reference_path.write_text(
        json.dumps(
            [
                {"name": "battery", "avg_capacity_MW": 10},
                {"name": "battery", "avg_capacity_MW": 12},
                {"name": "wind", "avg_capacity_MW": 50},
            ]
        )
    )

    break_generators(sys, reference_path)

    assert "Duplicate entries found for key 'name'" in caplog.text


def test_break_generators_splits_and_preserves_data(system_with_region) -> None:
    """Test that break_generators correctly splits large generators while preserving data."""
    system, region = system_with_region
    original = ReEDSGenerator(
        name="gen",
        region=region,
        technology="wind",
        capacity=120.0,
        category="wind",
    )
    system.add_component(original)

    emission = ReEDSEmission(rate=1.0, type=EmissionType.CO2)
    system.add_supplemental_attribute(original, emission)
    ts = SingleTimeSeries.from_array(
        data=[1.0, 2.0],
        name="max_active_power",
        initial_timestamp=datetime(2024, 1, 1),
        resolution=timedelta(hours=1),
    )
    system.add_time_series(ts, original)
    reference = {"wind": {"avg_capacity_MW": 50}}

    break_generators(system, reference)

    generators = list(system.get_components(ReEDSGenerator))
    assert {gen.name for gen in generators} == {"gen_01", "gen_02", "gen_03"}
    assert sorted(gen.capacity for gen in generators) == [20.0, 50.0, 50.0]
    for gen in generators:
        assert gen.region is original.region
        assert gen.category == original.category
        assert gen.technology == original.technology
        assert system.has_time_series(gen)
        assert system.get_time_series(gen).data.tolist() == [1.0, 2.0]
        attrs = system.get_supplemental_attributes_with_component(gen)
        assert len(attrs) == 1
        assert attrs[0].rate == pytest.approx(1.0)


def test_break_generators_drops_small_remainder(system_with_region) -> None:
    """Test that generators below capacity_threshold are not split."""
    system, region = system_with_region
    generator = ReEDSGenerator(
        name="gen",
        region=region,
        technology="wind",
        capacity=101.0,
        category="wind",
    )
    system.add_component(generator)
    reference = {"wind": {"avg_capacity_MW": 50}}

    break_generators(system, reference)

    generators = list(system.get_components(ReEDSGenerator))
    assert {gen.name for gen in generators} == {"gen_01", "gen_02"}
    assert sorted(gen.capacity for gen in generators) == [50.0, 50.0]


def test_break_generators_respects_non_break_list(system_with_region) -> None:
    """Test that generators in non_break_techs list are not split."""
    system, region = system_with_region
    original = ReEDSGenerator(
        name="gen",
        region=region,
        technology="wind",
        capacity=120.0,
        category="wind",
    )
    system.add_component(original)
    reference = {"wind": {"avg_capacity_MW": 50}}

    break_generators(system, reference, skip_categories=["wind"])

    generators = list(system.get_components(ReEDSGenerator))
    assert generators == [original]


def test_break_gens_uses_reference_dict(system_with_region) -> None:
    """Test that break_generators works with reference dict parameter."""
    system, region = system_with_region
    generator = ReEDSGenerator(
        name="gen",
        region=region,
        technology="pv",
        capacity=95.0,
        category="solar",
    )
    system.add_component(generator)
    reference = {"solar": {"avg_capacity_MW": 40}}

    break_generators(system, reference)

    generators = list(system.get_components(ReEDSGenerator))
    assert {gen.name for gen in generators} == {"gen_01", "gen_02", "gen_03"}
    assert sorted(gen.capacity for gen in generators) == [15.0, 40.0, 40.0]


def test_break_gens_reads_file(tmp_path: Path, system_with_region) -> None:
    """Test that break_generators can read reference data from file."""
    reference_path = tmp_path / "pcm_defaults.json"
    reference_path.write_text(json.dumps([{"name": "wind", "avg_capacity_MW": 30}]))
    system, region = system_with_region
    generator = ReEDSGenerator(
        name="gen",
        region=region,
        technology="wind",
        capacity=70.0,
        category="wind",
    )
    system.add_component(generator)

    break_generators(system, reference_path)

    generators = list(system.get_components(ReEDSGenerator))
    assert sorted(gen.capacity for gen in generators) == [10.0, 30.0, 30.0]


def test_break_generators_skips_missing_category(system_with_region) -> None:
    """Test that generators with missing category are skipped."""
    system, region = system_with_region
    generator = ReEDSGenerator(
        name="gen",
        region=region,
        technology="wind",
        capacity=120.0,
        category=None,
    )
    system.add_component(generator)
    reference = {"wind": {"avg_capacity_MW": 50}}

    break_generators(system, reference)

    assert list(system.get_components(ReEDSGenerator)) == [generator]


def test_break_generators_missing_reference(system_with_region) -> None:
    """Test that break_generators handles missing reference data gracefully."""
    system, region = system_with_region
    generator = ReEDSGenerator(
        name="gen",
        region=region,
        technology="wind",
        capacity=120.0,
        category="wind",
    )
    system.add_component(generator)
    reference = {"solar": {"avg_capacity_MW": 50}}

    break_generators(system, reference)

    assert list(system.get_components(ReEDSGenerator)) == [generator]


def test_break_generators_missing_avg_capacity(system_with_region, caplog) -> None:
    """Test that break_generators handles missing avg_capacity in reference."""
    system, region = system_with_region
    generator = ReEDSGenerator(
        name="gen",
        region=region,
        technology="wind",
        capacity=120.0,
        category="wind",
    )
    system.add_component(generator)
    reference = {"wind": {}}

    break_generators(system, reference)

    assert list(system.get_components(ReEDSGenerator)) == [generator]
    assert "avg_capacity_MW" not in caplog.text


def test_break_generators_small_capacity_not_split(system_with_region) -> None:
    """Test that small capacity generators below threshold are not split."""
    system, region = system_with_region
    generator = ReEDSGenerator(
        name="gen",
        region=region,
        technology="wind",
        capacity=40.0,
        category="wind",
    )
    system.add_component(generator)
    reference = {"wind": {"avg_capacity_MW": 50}}

    break_generators(system, reference)

    assert list(system.get_components(ReEDSGenerator)) == [generator]


@pytest.mark.slow
def test_break_generators_respects_drop_threshold(system_with_region) -> None:
    """Ensure remainder above/below threshold controls final split count."""
    system, region = system_with_region
    generator = ReEDSGenerator(
        name="gen",
        region=region,
        technology="wind",
        capacity=132.0,
        category="wind",
    )
    system.add_component(generator)
    reference = {"wind": {"avg_capacity_MW": 50}}

    break_generators(system, reference, drop_capacity_threshold=40)

    generators = list(system.get_components(ReEDSGenerator))
    assert len(generators) == 2
    assert sorted(gen.capacity for gen in generators) == [50.0, 50.0]


def test_normalize_reference_data_skips_invalid_records(caplog) -> None:
    """Ensure invalid reference records are skipped with warnings."""
    from r2x_reeds.sysmod.break_gens import _normalize_reference_data

    caplog.set_level("WARNING")
    result = _normalize_reference_data({"wind": "bad"}, "name", "<source>")
    assert result.is_err()
    assert "Skipping non-dict reference record" in caplog.text
    assert "No reference technologies" in str(result.unwrap_err())


def test_normalize_reference_data_missing_keys(caplog) -> None:
    """Ensure entries missing dedup key are skipped and reported."""
    from r2x_reeds.sysmod.break_gens import _normalize_reference_data

    caplog.set_level("WARNING")
    data = [{"avg_capacity_MW": 50}, {"name": None}]
    result = _normalize_reference_data(data, "name", "<source>")
    assert result.is_err()
    assert "Skipping reference record missing key 'name'" in caplog.text


def test_normalize_reference_data_invalid_type() -> None:
    """Ensure invalid reference data types raise TypeError."""
    from r2x_reeds.sysmod.break_gens import _normalize_reference_data

    result = _normalize_reference_data("string", "name", "<source>")
    assert result.is_err()
    assert isinstance(result.unwrap_err(), TypeError)
