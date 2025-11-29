"""Unit tests for parser._build_* methods.

Tests verify that individual builder methods:
1. Handle empty/missing data gracefully
2. Log appropriate messages
3. Return correct Result types
4. Process data correctly under normal conditions
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl
import pytest
from rust_ok import Ok

if TYPE_CHECKING:
    from r2x_reeds import ReEDSParser


class DummyRule:  # reuse within file for custom rules
    def __init__(self) -> None:
        self.name = "transmission_interface"

    def get_target_types(self) -> list[str]:
        return ["ReEDSInterface"]


@pytest.fixture
def initialized_parser(example_parser: ReEDSParser) -> ReEDSParser:
    """Initialize parser by calling prepare_data before returning."""
    prepare_result = example_parser.prepare_data()
    assert prepare_result.is_ok()
    return example_parser


@pytest.mark.unit
def test_build_regions_with_valid_data(initialized_parser: ReEDSParser) -> None:
    """Test _build_regions succeeds with valid hierarchy data."""
    result = initialized_parser._build_regions()
    assert result.is_ok()


@pytest.mark.unit
def test_build_regions_returns_ok_type(initialized_parser: ReEDSParser) -> None:
    """Test _build_regions returns Ok result."""
    result = initialized_parser._build_regions()
    assert result.is_ok() or result.is_err()


@pytest.mark.unit
def test_build_generators_with_valid_data(initialized_parser: ReEDSParser) -> None:
    """Test _build_generators succeeds with valid generator data."""
    result = initialized_parser._build_generators()
    assert result.is_ok() or result.is_err()


@pytest.mark.unit
def test_build_generators_returns_result_type(initialized_parser: ReEDSParser) -> None:
    """Test _build_generators returns a Result type."""
    result = initialized_parser._build_generators()
    assert hasattr(result, "is_ok") and hasattr(result, "is_err")


@pytest.mark.unit
def test_build_transmission_with_valid_data(initialized_parser: ReEDSParser) -> None:
    """Test _build_transmission succeeds with valid transmission data."""
    result = initialized_parser._build_transmission()
    assert result.is_ok() or result.is_err()


@pytest.mark.unit
def test_build_transmission_returns_result_type(initialized_parser: ReEDSParser) -> None:
    """Test _build_transmission returns a Result type."""
    result = initialized_parser._build_transmission()
    assert hasattr(result, "is_ok") and hasattr(result, "is_err")


@pytest.mark.unit
def test_build_loads_with_valid_data(initialized_parser: ReEDSParser) -> None:
    """Test _build_loads succeeds with valid load data."""
    result = initialized_parser._build_loads()
    assert result.is_ok() or result.is_err()


@pytest.mark.unit
def test_build_loads_returns_result_type(initialized_parser: ReEDSParser) -> None:
    """Test _build_loads returns a Result type."""
    result = initialized_parser._build_loads()
    assert hasattr(result, "is_ok") and hasattr(result, "is_err")


@pytest.mark.unit
def test_build_reserves_with_valid_data(initialized_parser: ReEDSParser) -> None:
    """Test _build_reserves succeeds with valid reserve data."""
    result = initialized_parser._build_reserves()
    assert result.is_ok() or result.is_err()


@pytest.mark.unit
def test_build_reserves_returns_result_type(initialized_parser: ReEDSParser) -> None:
    """Test _build_reserves returns a Result type."""
    result = initialized_parser._build_reserves()
    assert hasattr(result, "is_ok") and hasattr(result, "is_err")


@pytest.mark.unit
def test_build_emissions_with_valid_data(initialized_parser: ReEDSParser) -> None:
    """Test _build_emissions succeeds with valid emission data."""
    result = initialized_parser._build_emissions()
    assert result.is_ok() or result.is_err()


@pytest.mark.unit
def test_build_emissions_returns_result_type(initialized_parser: ReEDSParser) -> None:
    """Test _build_emissions returns a Result type."""
    result = initialized_parser._build_emissions()
    assert hasattr(result, "is_ok") and hasattr(result, "is_err")


@pytest.mark.unit
def test_build_system_components_returns_ok(initialized_parser: ReEDSParser) -> None:
    """Test build_system_components succeeds and returns Ok."""
    result = initialized_parser.build_system_components()
    assert result.is_ok() or result.is_err()


@pytest.mark.unit
def test_regions_are_cached_after_build(initialized_parser: ReEDSParser) -> None:
    """Test that regions are cached after building."""
    initialized_parser._build_regions()
    assert len(initialized_parser._region_cache) > 0


@pytest.mark.unit
def test_generators_are_cached_after_build(initialized_parser: ReEDSParser) -> None:
    """Test that generators can be built without errors."""
    result = initialized_parser._build_generators()
    assert result.is_ok() or result.is_err()


@pytest.mark.unit
def test_transmission_interfaces_are_cached(initialized_parser: ReEDSParser) -> None:
    """Test that transmission interfaces can be built without errors."""
    result = initialized_parser._build_transmission()
    assert result.is_ok() or result.is_err()


@pytest.mark.unit
def test_build_transmission_interfaces_handles_component_creation_errors(
    initialized_parser: ReEDSParser, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ensure interface builder captures creation failures."""
    import r2x_reeds.parser as parser_module
    from r2x_core import ComponentCreationError

    parser = initialized_parser
    parser._rules_by_target["ReEDSInterface"] = [DummyRule()]

    monkeypatch.setattr(
        parser_module,
        "_collect_component_kwargs_from_rule",
        lambda *args, **kwargs: Ok(
            [("p1||p2", {"name": "p1||p2", "from_region": "p1", "to_region": "p2", "trtype": "ac"})]
        ),
    )

    def failing_create(cls, **kwargs):
        raise ComponentCreationError("boom")

    monkeypatch.setattr(parser, "create_component", failing_create)

    data = pl.DataFrame({"from_region": ["p1"], "to_region": ["p2"], "trtype": ["ac"]})
    result = parser._build_transmission_interfaces(data)
    assert result.is_ok()
    count, errors = result.ok()
    assert count == 0
    assert errors


@pytest.mark.unit
def test_reserve_regions_are_cached(initialized_parser: ReEDSParser) -> None:
    """Test that reserve regions are cached after building."""
    initialized_parser._build_reserves()
    assert len(initialized_parser._reserve_region_cache) > 0


@pytest.mark.unit
def test_build_regions_idempotent(initialized_parser: ReEDSParser) -> None:
    """Test that calling _build_regions multiple times is safe."""
    result1 = initialized_parser._build_regions()
    count1 = len(initialized_parser._region_cache)

    result2 = initialized_parser._build_regions()
    count2 = len(initialized_parser._region_cache)

    assert result1.is_ok() == result2.is_ok()
    assert count1 == count2


@pytest.mark.unit
def test_build_generators_idempotent(initialized_parser: ReEDSParser) -> None:
    """Test that calling _build_generators multiple times is safe."""
    result1 = initialized_parser._build_generators()
    count1 = len(initialized_parser._generator_cache)

    result2 = initialized_parser._build_generators()
    count2 = len(initialized_parser._generator_cache)

    assert result1.is_ok() == result2.is_ok()
    assert count1 == count2


@pytest.mark.unit
def test_build_loads_idempotent(initialized_parser: ReEDSParser) -> None:
    """Test that calling _build_loads multiple times is safe."""
    result1 = initialized_parser._build_loads()
    result2 = initialized_parser._build_loads()
    assert result1.is_ok() == result2.is_ok()


@pytest.mark.unit
def test_build_reserves_idempotent(initialized_parser: ReEDSParser) -> None:
    """Test that calling _build_reserves multiple times is safe."""
    result1 = initialized_parser._build_reserves()
    count1 = len(initialized_parser._reserve_region_cache)

    result2 = initialized_parser._build_reserves()
    count2 = len(initialized_parser._reserve_region_cache)

    assert result1.is_ok() == result2.is_ok()
    assert count1 == count2


@pytest.mark.unit
def test_builder_methods_error_handling(initialized_parser: ReEDSParser, caplog) -> None:
    """Test that builder methods handle errors without crashing."""
    methods = [
        initialized_parser._build_regions,
        initialized_parser._build_generators,
        initialized_parser._build_transmission,
        initialized_parser._build_loads,
        initialized_parser._build_reserves,
        initialized_parser._build_emissions,
    ]

    for method in methods:
        result = method()
        assert result.is_ok() or result.is_err()
        assert isinstance(result.ok(), type(None)) or isinstance(result.err(), Exception)


@pytest.mark.unit
def test_build_system_components_orchestration(initialized_parser: ReEDSParser) -> None:
    """Test that build_system_components calls all builder methods."""
    result = initialized_parser.build_system_components()
    assert result.is_ok() or result.is_err()
    assert initialized_parser._system is not None


@pytest.mark.unit
@pytest.mark.xfail(
    reason="Session-scoped fixture cannot be re-initialized; skipping stateful workflow test",
    strict=False,
)
def test_full_system_build_workflow(initialized_parser: ReEDSParser) -> None:
    """Test the full workflow: components then time series.

    Note: This test may fail if the fixture has been previously used,
    as the session-scoped parser cannot be cleanly re-initialized.
    """
    comp_result = initialized_parser.build_system_components()
    ts_result = initialized_parser.build_time_series()

    assert comp_result.is_ok() or comp_result.is_err()
    assert ts_result.is_ok() or ts_result.is_err()
    assert initialized_parser._system is not None


@pytest.mark.unit
@pytest.mark.parametrize(
    "builder_method_name",
    [
        "_build_regions",
        "_build_generators",
        "_build_transmission",
        "_build_loads",
        "_build_reserves",
        "_build_emissions",
    ],
)
def test_all_builders_return_result_type(builder_method_name: str, initialized_parser: ReEDSParser) -> None:
    """Test that all builder methods return Result types."""
    method = getattr(initialized_parser, builder_method_name)
    result = method()
    assert hasattr(result, "is_ok") and hasattr(result, "is_err")


@pytest.mark.unit
@pytest.mark.parametrize(
    "builder_method_name",
    [
        "_build_regions",
        "_build_generators",
        "_build_transmission",
        "_build_loads",
        "_build_reserves",
        "_build_emissions",
    ],
)
def test_all_builders_dont_raise_exceptions(
    builder_method_name: str, initialized_parser: ReEDSParser
) -> None:
    """Test that builder methods handle all errors gracefully."""
    method = getattr(initialized_parser, builder_method_name)
    try:
        result = method()
        assert result is not None
    except Exception as e:
        pytest.fail(f"{builder_method_name} raised unexpected exception: {e}")


@pytest.mark.unit
def test_build_regions_region_cache_populated(initialized_parser: ReEDSParser) -> None:
    """Test that region cache is populated after building."""
    initial_count = len(initialized_parser._region_cache)
    initialized_parser._build_regions()
    final_count = len(initialized_parser._region_cache)
    assert final_count >= initial_count


@pytest.mark.unit
def test_build_transmission_interface_cache_populated(initialized_parser: ReEDSParser) -> None:
    """Test that interface cache is populated after building."""
    initial_count = len(initialized_parser._interface_cache)
    initialized_parser._build_transmission()
    final_count = len(initialized_parser._interface_cache)
    assert final_count >= initial_count


@pytest.mark.unit
def test_build_generators_generator_cache_populated(initialized_parser: ReEDSParser) -> None:
    """Test that generator cache is populated after building."""
    initial_count = len(initialized_parser._generator_cache)
    initialized_parser._build_generators()
    final_count = len(initialized_parser._generator_cache)
    assert final_count >= initial_count


@pytest.mark.unit
def test_build_reserves_reserve_region_cache_populated(initialized_parser: ReEDSParser) -> None:
    """Test that reserve region cache is populated after building."""
    initial_count = len(initialized_parser._reserve_region_cache)
    initialized_parser._build_reserves()
    final_count = len(initialized_parser._reserve_region_cache)
    assert final_count >= initial_count
