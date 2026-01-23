from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from infrasys import SingleTimeSeries, System

from r2x_reeds.models.components import ReEDSEmission, ReEDSGenerator
from r2x_reeds.models.enums import EmissionType
from r2x_reeds.sysmod.break_gens import BreakGensConfig, break_generators

pytestmark = [pytest.mark.integration]


@pytest.fixture
def system_with_region(sample_region):
    system = System(name="Test", auto_add_composed_components=True)
    system.add_component(sample_region)
    return system, sample_region


def _run_break(system: System, **kwargs) -> System:
    result = break_generators(system, BreakGensConfig(**kwargs))
    assert result.is_ok()
    return result.unwrap()


def test_break_generator_fails_with_wrong_reference_type():
    sys = System(name="Test")

    result = break_generators(sys, BreakGensConfig(reference_units={"wind": "invalid"}))
    assert result.is_err()
    assert "No reference technologies" in result.unwrap_err()


def test_break_generator_fails_with_missing_file(tmp_path: Path):
    sys = System(name="Test")
    missing = tmp_path / "missing.json"

    result = break_generators(sys, BreakGensConfig(reference_units=missing))
    assert result.is_err()
    assert "Reference technologies file not found" in result.unwrap_err()


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
                {"name": "battery", "capacity_MW": 10},
                {"name": "battery", "capacity_MW": 12},
                {"name": "wind", "capacity_MW": 50},
            ]
        )
    )

    result = break_generators(sys, BreakGensConfig(reference_units=reference_path))
    assert result.is_ok()

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
    reference = {"wind": {"capacity_MW": 50}}

    _run_break(system, reference_units=reference)

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
    reference = {"wind": {"capacity_MW": 50}}

    _run_break(system, reference_units=reference)

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
    reference = {"wind": {"capacity_MW": 50}}

    _run_break(system, reference_units=reference, skip_categories=["wind"])

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
    reference = {"solar": {"capacity_MW": 40}}

    _run_break(system, reference_units=reference)

    generators = list(system.get_components(ReEDSGenerator))
    assert {gen.name for gen in generators} == {"gen_01", "gen_02", "gen_03"}
    assert sorted(gen.capacity for gen in generators) == [15.0, 40.0, 40.0]


def test_break_gens_reads_file(tmp_path: Path, system_with_region) -> None:
    """Test that break_generators can read reference data from file."""
    reference_path = tmp_path / "pcm_defaults.json"
    reference_path.write_text(json.dumps([{"name": "wind", "capacity_MW": 30}]))
    system, region = system_with_region
    generator = ReEDSGenerator(
        name="gen",
        region=region,
        technology="wind",
        capacity=70.0,
        category="wind",
    )
    system.add_component(generator)

    _run_break(system, reference_units=reference_path)

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
    reference = {"wind": {"capacity_MW": 50}}

    _run_break(system, reference_units=reference)

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
    reference = {"solar": {"capacity_MW": 50}}

    _run_break(system, reference_units=reference)

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

    _run_break(system, reference_units=reference)

    assert list(system.get_components(ReEDSGenerator)) == [generator]
    assert "`capacity_MW` not found on reference_tech" in caplog.text


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
    reference = {"wind": {"capacity_MW": 50}}

    _run_break(system, reference_units=reference)

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
    reference = {"wind": {"capacity_MW": 50}}

    _run_break(system, reference_units=reference, drop_capacity_threshold=40)

    generators = list(system.get_components(ReEDSGenerator))
    assert len(generators) == 2
    assert sorted(gen.capacity for gen in generators) == [50.0, 50.0]


def test_load_reference_units(caplog):
    from r2x_reeds.sysmod.break_gens import _load_reference_units

    _load_reference_units(reference_units=None)

    assert "No reference_units provided." in caplog.text


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
    data = [{"capacity_MW": 50}, {"name": None}]
    result = _normalize_reference_data(data, "name", "<source>")
    assert result.is_err()
    assert "Skipping reference record missing key 'name'" in caplog.text


def test_normalize_reference_data_invalid_type() -> None:
    """Ensure invalid reference data types raise TypeError."""
    from r2x_reeds.sysmod.break_gens import _normalize_reference_data

    result = _normalize_reference_data("string", "name", "<source>")
    assert result.is_err()
    assert isinstance(result.unwrap_err(), TypeError)


def test_break_generators_return_same_type(system_with_region: System, caplog) -> None:
    from r2x_reeds.models import ReEDSThermalGenerator

    sys, _ = system_with_region

    gen = ReEDSThermalGenerator.example()

    sys.add_component(gen)

    reference = {"thermal": {"capacity_MW": 50}}

    _run_break(sys, reference_units=reference, drop_capacity_threshold=40)

    assert len(list(sys.get_components(ReEDSThermalGenerator))) == 2
    assert next(sys.get_components(ReEDSThermalGenerator)).capacity == 50


def test_break_generators_with_default_reference_units(system_with_region) -> None:
    """Test that break_generators uses default reference units when none provided."""
    sys, region = system_with_region
    # Use a tech from the default pcm_defaults.json (if it exists)
    # We'll test the code path without specifying reference_units
    generator = ReEDSGenerator(
        name="gen",
        region=region,
        technology="wind",
        capacity=100.0,
        category="notindefaults",
    )
    sys.add_component(generator)

    # Should not crash, just skip the generator
    _run_break(sys, reference_units=None)
    assert list(sys.get_components(ReEDSGenerator)) == [generator]


def test_create_split_generator_preserves_all_fields(system_with_region) -> None:
    """Test that _create_split_generator preserves all original generator fields."""
    from r2x_reeds.sysmod.break_gens import _create_split_generator

    sys, region = system_with_region
    original = ReEDSGenerator(
        name="original",
        region=region,
        technology="wind",
        capacity=100.0,
        category="wind",
        heat_rate=7.5,
        forced_outage_rate=0.05,
        planned_outage_rate=0.10,
        fuel_type="wind",
        fuel_price=0.0,
        vom_cost=25.0,
        vintage="2020",
    )

    split = _create_split_generator(sys, original, "split_01", 50.0)

    assert split.name == "split_01"
    assert split.capacity == 50.0
    assert split.region is original.region
    assert split.technology == original.technology
    assert split.category == original.category
    assert split.heat_rate == pytest.approx(7.5)
    assert split.forced_outage_rate == pytest.approx(0.05)
    assert split.planned_outage_rate == pytest.approx(0.10)
    assert split.fuel_type == "wind"
    assert split.fuel_price == pytest.approx(0.0)
    assert split.vom_cost == pytest.approx(25.0)
    assert split.vintage == "2020"


def test_create_split_generator_added_to_system(system_with_region) -> None:
    """Test that _create_split_generator adds component to system."""
    from r2x_reeds.sysmod.break_gens import _create_split_generator

    sys, region = system_with_region
    original = ReEDSGenerator(
        name="gen",
        region=region,
        technology="wind",
        capacity=100.0,
        category="wind",
    )

    split = _create_split_generator(sys, original, "gen_01", 50.0)

    components = list(sys.get_components(ReEDSGenerator))
    assert split in components
    assert split.name in {c.name for c in components}


def test_break_system_generators_no_matching_components(system_with_region) -> None:
    """Test _break_system_generators when no generators match the break_category."""
    from r2x_reeds.sysmod.break_gens import _break_system_generators

    sys, region = system_with_region
    generator = ReEDSGenerator(
        name="gen",
        region=region,
        technology="wind",
        capacity=100.0,
        category="wind",
    )
    sys.add_component(generator)
    reference = {"solar": {"capacity_MW": 50}}

    _break_system_generators(sys, reference, capacity_threshold=5, skip_categories=None)

    generators = list(sys.get_components(ReEDSGenerator))
    assert generators == [generator]


def test_break_system_generators_empty_skip_categories(system_with_region) -> None:
    """Test that empty skip_categories list is handled correctly."""
    from r2x_reeds.sysmod.break_gens import _break_system_generators

    sys, region = system_with_region
    generator = ReEDSGenerator(
        name="gen",
        region=region,
        technology="wind",
        capacity=120.0,
        category="wind",
    )
    sys.add_component(generator)
    reference = {"wind": {"capacity_MW": 50}}

    _break_system_generators(sys, reference, capacity_threshold=5, skip_categories=[])

    generators = list(sys.get_components(ReEDSGenerator))
    assert len(generators) == 3
    assert {gen.name for gen in generators} == {"gen_01", "gen_02", "gen_03"}


def test_break_generators_capacity_exactly_matches_reference(system_with_region) -> None:
    """Test generator with capacity equal to reference capacity is not split."""
    sys, region = system_with_region
    generator = ReEDSGenerator(
        name="gen",
        region=region,
        technology="wind",
        capacity=50.0,
        category="wind",
    )
    sys.add_component(generator)
    reference = {"wind": {"capacity_MW": 50}}

    _run_break(sys, reference_units=reference)

    generators = list(sys.get_components(ReEDSGenerator))
    assert generators == [generator]


def test_break_generators_with_remainder_above_threshold(system_with_region) -> None:
    """Test that remainder strictly above threshold is created as separate generator."""
    sys, region = system_with_region
    generator = ReEDSGenerator(
        name="gen",
        region=region,
        technology="wind",
        capacity=156.0,
        category="wind",
    )
    sys.add_component(generator)
    reference = {"wind": {"capacity_MW": 50}}

    _run_break(sys, reference_units=reference, drop_capacity_threshold=5)

    generators = list(sys.get_components(ReEDSGenerator))
    # 156 / 50 = 3 splits with 6 MW remainder, remainder > 5 so it's included
    assert {gen.name for gen in generators} == {"gen_01", "gen_02", "gen_03", "gen_04"}
    assert sorted(gen.capacity for gen in generators) == [6.0, 50.0, 50.0, 50.0]


def test_break_generators_multiple_generators_in_system(system_with_region) -> None:
    """Test breaking multiple generators with mixed matching categories."""
    sys, region = system_with_region
    wind_gen = ReEDSGenerator(
        name="wind",
        region=region,
        technology="wind",
        capacity=120.0,
        category="wind",
    )
    solar_gen = ReEDSGenerator(
        name="solar",
        region=region,
        technology="pv",
        capacity=100.0,
        category="solar",
    )
    sys.add_component(wind_gen)
    sys.add_component(solar_gen)

    reference = {"wind": {"capacity_MW": 50}}

    _run_break(sys, reference_units=reference)

    generators = list(sys.get_components(ReEDSGenerator))
    names = {gen.name for gen in generators}
    assert "wind_01" in names
    assert "wind_02" in names
    assert "wind_03" in names
    assert "solar" in names  # Not broken


def test_break_generators_with_custom_break_category(system_with_region) -> None:
    """Test break_generators with custom break_category parameter."""
    sys, region = system_with_region
    generator = ReEDSGenerator(
        name="gen",
        region=region,
        technology="wind",
        capacity=120.0,
        category="not_used",
    )
    sys.add_component(generator)

    # Use technology as the break category
    reference = {"wind": {"capacity_MW": 50}}

    _run_break(sys, reference_units=reference, break_category="technology")

    generators = list(sys.get_components(ReEDSGenerator))
    assert {gen.name for gen in generators} == {"gen_01", "gen_02", "gen_03"}


def test_load_reference_units_with_dict_input(caplog) -> None:
    """Test _load_reference_units with dict input."""
    from r2x_reeds.sysmod.break_gens import _load_reference_units

    reference = {"wind": {"capacity_MW": 50}, "solar": {"capacity_MW": 30}}

    result = _load_reference_units(reference)

    assert result.is_ok()
    data = result.unwrap()
    assert data == {
        "wind": {"capacity_MW": 50, "name": "wind"},
        "solar": {"capacity_MW": 30, "name": "solar"},
    }


def test_load_reference_units_dict_with_non_dict_values(caplog) -> None:
    """Test _load_reference_units when dict has non-dict values."""
    from r2x_reeds.sysmod.break_gens import _load_reference_units

    caplog.set_level("WARNING")
    reference = {"wind": "invalid"}

    result = _load_reference_units(reference)

    assert result.is_err()
    assert "Skipping non-dict reference record" in caplog.text


def test_normalize_reference_data_empty_list() -> None:
    """Test _normalize_reference_data with empty list."""
    from r2x_reeds.sysmod.break_gens import _normalize_reference_data

    result = _normalize_reference_data([], "name", "<source>")

    assert result.is_err()
    assert "No reference technologies" in str(result.unwrap_err())


def test_normalize_reference_data_with_dict_input_empty() -> None:
    """Test _normalize_reference_data with empty dict."""
    from r2x_reeds.sysmod.break_gens import _normalize_reference_data

    result = _normalize_reference_data({}, "name", "<source>")

    assert result.is_err()
    assert "No reference technologies" in str(result.unwrap_err())


def test_break_generators_preserves_other_attributes(system_with_region) -> None:
    """Test that breaking preserves supplemental attributes on all splits."""
    from r2x_reeds.models import ReEDSEmission
    from r2x_reeds.models.enums import EmissionType

    sys, region = system_with_region
    original = ReEDSGenerator(
        name="gen",
        region=region,
        technology="wind",
        capacity=100.0,
        category="wind",
    )
    sys.add_component(original)

    # Add multiple supplemental attributes
    emission1 = ReEDSEmission(rate=2.0, type=EmissionType.CO2)
    emission2 = ReEDSEmission(rate=0.5, type=EmissionType.NOX)
    sys.add_supplemental_attribute(original, emission1)
    sys.add_supplemental_attribute(original, emission2)

    reference = {"wind": {"capacity_MW": 50}}

    _run_break(sys, reference_units=reference)

    generators = list(sys.get_components(ReEDSGenerator))
    for gen in generators:
        attrs = sys.get_supplemental_attributes_with_component(gen)
        assert len(attrs) == 2


def test_create_split_generator_with_none_values(system_with_region) -> None:
    """Test _create_split_generator preserves None values from original."""
    from r2x_reeds.sysmod.break_gens import _create_split_generator

    sys, region = system_with_region
    original = ReEDSGenerator(
        name="gen",
        region=region,
        technology="wind",
        capacity=100.0,
        category=None,
        heat_rate=None,
        fuel_type=None,
    )

    split = _create_split_generator(sys, original, "split_01", 50.0)

    assert split.category is None
    assert split.heat_rate is None
    assert split.fuel_type is None


def test_break_generators_very_large_capacity(system_with_region) -> None:
    """Test breaking very large capacity generator."""
    sys, region = system_with_region
    generator = ReEDSGenerator(
        name="gen",
        region=region,
        technology="wind",
        capacity=1000.0,
        category="wind",
    )
    sys.add_component(generator)
    reference = {"wind": {"capacity_MW": 100}}

    _run_break(sys, reference_units=reference)

    generators = list(sys.get_components(ReEDSGenerator))
    assert len(generators) == 10
    assert all(gen.capacity == 100.0 for gen in generators)


def test_break_generators_fractional_splits(system_with_region) -> None:
    """Test generator split results in expected fractional capacities."""
    sys, region = system_with_region
    generator = ReEDSGenerator(
        name="gen",
        region=region,
        technology="wind",
        capacity=175.5,
        category="wind",
    )
    sys.add_component(generator)
    reference = {"wind": {"capacity_MW": 50}}

    _run_break(sys, reference_units=reference, drop_capacity_threshold=5)

    generators = list(sys.get_components(ReEDSGenerator))
    capacities = sorted(gen.capacity for gen in generators)
    assert capacities == [25.5, 50.0, 50.0, 50.0]


def test_normalize_reference_data_list_with_mixed_types(caplog) -> None:
    """Test _normalize_reference_data with list containing mixed types."""
    from r2x_reeds.sysmod.break_gens import _normalize_reference_data

    caplog.set_level("WARNING")
    data = [
        {"name": "wind", "capacity_MW": 50},
        "invalid_string",
        {"name": "solar", "capacity_MW": 30},
    ]

    result = _normalize_reference_data(data, "name", "<source>")

    assert result.is_ok()
    assert len(result.unwrap()) == 2
    # The warning comes from _deduplicate_records in utils.py
    assert "Skipping non-dict record during deduplication" in caplog.text


def test_load_reference_units_from_json_file(tmp_path: Path) -> None:
    """Test _load_reference_units loads from JSON file correctly."""
    from r2x_reeds.sysmod.break_gens import _load_reference_units

    ref_file = tmp_path / "ref.json"
    ref_data = {"wind": {"capacity_MW": 100}, "solar": {"capacity_MW": 50}}
    ref_file.write_text(json.dumps(ref_data))

    result = _load_reference_units(ref_file)

    assert result.is_ok()
    data = result.unwrap()
    assert "wind" in data
    assert data["wind"]["capacity_MW"] == 100


def test_break_generators_with_path_string_reference(tmp_path: Path, system_with_region) -> None:
    """Test break_generators with reference as string path."""
    sys, region = system_with_region
    generator = ReEDSGenerator(
        name="gen",
        region=region,
        technology="wind",
        capacity=120.0,
        category="wind",
    )
    sys.add_component(generator)

    ref_file = tmp_path / "ref.json"
    ref_data = {"wind": {"capacity_MW": 50}}
    ref_file.write_text(json.dumps(ref_data))

    _run_break(sys, reference_units=str(ref_file))

    generators = list(sys.get_components(ReEDSGenerator))
    assert {gen.name for gen in generators} == {"gen_01", "gen_02", "gen_03"}


def test_normalize_reference_data_dict_preserves_keys(caplog) -> None:
    """Test _normalize_reference_data preserves top-level dict keys as name."""
    from r2x_reeds.sysmod.break_gens import _normalize_reference_data

    data = {
        "wind": {"capacity_MW": 100},
        "solar": {"capacity_MW": 50},
    }

    result = _normalize_reference_data(data, "name", "<source>")

    assert result.is_ok()
    normalized = result.unwrap()
    assert normalized["wind"]["name"] == "wind"
    assert normalized["solar"]["name"] == "solar"


def test_normalize_reference_data_dict_with_existing_name(caplog) -> None:
    """Test _normalize_reference_data with existing name field in dict."""
    from r2x_reeds.sysmod.break_gens import _normalize_reference_data

    data = {
        "wind": {"name": "wind_custom", "capacity_MW": 100},
    }

    result = _normalize_reference_data(data, "name", "<source>")

    assert result.is_ok()
    normalized = result.unwrap()
    # The key in the result will be the name field value
    assert "wind_custom" in normalized
    assert normalized["wind_custom"]["name"] == "wind_custom"
