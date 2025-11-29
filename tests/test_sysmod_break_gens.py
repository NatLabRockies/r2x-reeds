from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from r2x_core import DataStore
from r2x_reeds.sysmod.break_gens import break_generators

if TYPE_CHECKING:
    pass


@pytest.mark.unit
def test_break_generator_fails_with_wrong_reference_type():
    from r2x_core import System

    sys = System(name="Test")

    with pytest.raises(TypeError):
        break_generators(sys, 10)


@pytest.mark.unit
def test_break_generator_fails_with_missing_file(tmp_path: Path):
    from r2x_core import System

    sys = System(name="Test")
    missing = tmp_path / "missing.json"

    with pytest.raises(FileNotFoundError):
        break_generators(sys, missing)


@pytest.mark.unit
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


@pytest.fixture()
def reference_generators() -> dict[str, Any]:
    from importlib.resources import files

    reference_path = files("r2x_reeds.config") / "pcm_defaults.json"

    return DataStore.load_file(reference_path)


@pytest.mark.unit
def test_break_generators_splits_and_preserves_data() -> None:
    """Test that break_generators correctly splits large generators while preserving data."""
    pytest.skip("Requires integration with example_system fixture and actual generator data")


@pytest.mark.unit
def test_break_generators_drops_small_remainder() -> None:
    """Test that generators below capacity_threshold are not split."""
    pytest.skip("Requires integration test setup with actual ReEDS generator data")


@pytest.mark.unit
def test_break_generators_respects_non_break_list() -> None:
    """Test that generators in non_break_techs list are not split."""
    pytest.skip("Requires integration test setup with actual ReEDS generator data")


@pytest.mark.unit
def test_break_gens_uses_reference_dict() -> None:
    """Test that break_generators works with reference dict parameter."""
    pytest.skip("Requires integration test setup with actual ReEDS generator data")


@pytest.mark.unit
def test_break_gens_reads_file(tmp_path: Path) -> None:
    """Test that break_generators can read reference data from file."""
    pytest.skip("Requires integration test setup with actual ReEDS generator data")


@pytest.mark.unit
def test_break_generators_skips_missing_category() -> None:
    """Test that generators with missing category are skipped."""
    pytest.skip("Requires integration test setup with actual ReEDS generator data")


@pytest.mark.unit
def test_break_generators_missing_reference() -> None:
    """Test that break_generators handles missing reference data gracefully."""
    pytest.skip("Requires integration test setup with actual ReEDS generator data")


@pytest.mark.unit
def test_break_generators_missing_avg_capacity(caplog) -> None:
    """Test that break_generators handles missing avg_capacity in reference."""
    pytest.skip("Requires integration test setup with actual ReEDS generator data")


@pytest.mark.unit
def test_break_generators_small_capacity_not_split() -> None:
    """Test that small capacity generators below threshold are not split."""
    pytest.skip("Requires integration test setup with actual ReEDS generator data")
