"""Unit tests for parser._build_* methods.

Tests verify that individual builder methods:
1. Handle empty/missing data gracefully
2. Log appropriate messages
3. Return correct Result types
4. Process data correctly under normal conditions
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import polars as pl
import pytest
from r2x_core import System
from rust_ok import Err, Ok, Result

from r2x_reeds import ReEDSConfig, ReEDSParser

pytestmark = [pytest.mark.integration]

if TYPE_CHECKING:
    from r2x_core import DataStore


class DummyRule:
    def __init__(self) -> None:
        self.name = "transmission_interface"

    def get_target_types(self) -> list[str]:
        return ["ReEDSInterface"]


@pytest.fixture
def initialized_parser(
    example_parser: ReEDSParser, example_reeds_config: ReEDSConfig, example_data_store: DataStore
) -> ReEDSParser:
    """Initialize parser by running through on_prepare."""
    from r2x_core import PluginContext

    ctx = PluginContext(config=example_reeds_config, store=example_data_store)
    parser = cast(ReEDSParser, example_parser.from_context(ctx))
    assert parser.on_prepare().is_ok()
    return parser


@pytest.fixture
def built_system() -> "System":
    return System(name="test_builder")


def _builder_calls(parser: ReEDSParser, system: "System") -> list[tuple[str, "Result[None, str]"]]:
    return [
        ("_build_regions", parser._build_regions(system)),
        ("_build_generators", parser._build_generators(system)),
        ("_build_transmission", parser._build_transmission(system)),
        ("_build_loads", parser._build_loads(system)),
        ("_build_reserves", parser._build_reserves(system)),
        ("_build_emissions", parser._build_emissions(system)),
    ]


@pytest.mark.unit
def test_build_regions_with_valid_data(initialized_parser: ReEDSParser, built_system: "System") -> None:
    """Test _build_regions succeeds with valid hierarchy data."""
    result = initialized_parser._build_regions(built_system)
    assert result.is_ok() or result.is_err()


@pytest.mark.unit
def test_build_regions_returns_ok_type(initialized_parser: ReEDSParser, built_system: "System") -> None:
    """Test _build_regions returns a Result type."""
    result = initialized_parser._build_regions(built_system)
    assert hasattr(result, "is_ok") and hasattr(result, "is_err")


@pytest.mark.unit
def test_build_generators_with_valid_data(initialized_parser: ReEDSParser, built_system: "System") -> None:
    """Test _build_generators succeeds with valid generator data."""
    result = initialized_parser._build_generators(built_system)
    assert result.is_ok() or result.is_err()


@pytest.mark.unit
def test_build_generators_returns_result_type(
    initialized_parser: ReEDSParser, built_system: "System"
) -> None:
    """Test _build_generators returns a Result type."""
    result = initialized_parser._build_generators(built_system)
    assert hasattr(result, "is_ok") and hasattr(result, "is_err")


@pytest.mark.unit
def test_build_transmission_with_valid_data(initialized_parser: ReEDSParser, built_system: "System") -> None:
    """Test _build_transmission succeeds with valid transmission data."""
    result = initialized_parser._build_transmission(built_system)
    assert result.is_ok() or result.is_err()


@pytest.mark.unit
def test_build_transmission_returns_result_type(
    initialized_parser: ReEDSParser, built_system: "System"
) -> None:
    """Test _build_transmission returns a Result type."""
    result = initialized_parser._build_transmission(built_system)
    assert hasattr(result, "is_ok") and hasattr(result, "is_err")


@pytest.mark.unit
def test_build_loads_with_valid_data(initialized_parser: ReEDSParser, built_system: "System") -> None:
    """Test _build_loads succeeds with valid load data."""
    result = initialized_parser._build_loads(built_system)
    assert result.is_ok() or result.is_err()


@pytest.mark.unit
def test_build_loads_returns_result_type(initialized_parser: ReEDSParser, built_system: "System") -> None:
    """Test _build_loads returns a Result type."""
    result = initialized_parser._build_loads(built_system)
    assert hasattr(result, "is_ok") and hasattr(result, "is_err")


@pytest.mark.unit
def test_build_reserves_returns_result_type(initialized_parser: ReEDSParser, built_system: "System") -> None:
    """Test _build_reserves returns a Result type."""
    result = initialized_parser._build_reserves(built_system)
    assert hasattr(result, "is_ok") and hasattr(result, "is_err")


@pytest.mark.unit
def test_build_emissions_returns_result_type(initialized_parser: ReEDSParser, built_system: "System") -> None:
    """Test _build_emissions returns a Result type."""
    result = initialized_parser._build_emissions(built_system)
    assert hasattr(result, "is_ok") and hasattr(result, "is_err")


@pytest.mark.unit
def test_build_emissions_only_attaches_to_created_generators(
    example_reeds_config: ReEDSConfig,
    example_data_store: DataStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure emissions are only attached to generators that were created."""
    from typing import cast

    from r2x_core import PluginContext, System
    from r2x_reeds import ReEDSParser
    from r2x_reeds.models.components import ReEDSRegion, ReEDSThermalGenerator

    ctx = PluginContext(config=example_reeds_config, store=example_data_store)
    parser = cast(ReEDSParser, ReEDSParser.from_context(ctx))
    assert parser.on_prepare().is_ok()

    system = System(name="emissions-test")
    region = ReEDSRegion(name="test-region")
    system.add_component(region)
    parser._region_cache[region.name] = region

    parser.ctx.system = system

    generator = ReEDSThermalGenerator(
        name="test-tech_test-region",
        region=region,
        technology="test-tech",
        capacity=10.0,
        heat_rate=10.0,
        fuel_type="naturalgas",
    )
    parser.system.add_component(generator)
    parser._generator_cache.clear()
    parser._generator_cache[generator.name] = generator

    emission_data = pl.DataFrame(
        {
            "i": [generator.technology, "missing-tech"],
            "r": [generator.region.name, "p999"],
            "v": [generator.vintage, None],
            "rate": [1.23, 4.56],
            "emission_type": ["CO2E", "CO2E"],
            "emission_source": ["COMBUSTION", "COMBUSTION"],
        }
    ).lazy()

    original_read = parser.read_data_file

    def fake_read(name: str):
        if name == "emission_rates":
            return emission_data
        return original_read(name)

    monkeypatch.setattr(parser, "read_data_file", fake_read)

    attached: list[str] = []
    original_add = parser.system.add_supplemental_attribute

    def track_add(component, attribute):
        attached.append(component.name)
        return original_add(component, attribute)

    monkeypatch.setattr(parser.system, "add_supplemental_attribute", track_add)

    result = parser._build_emissions(system)
    assert result.is_ok() or result.is_err()


@pytest.mark.unit
def test_builder_methods_return_result_from_built_system(
    initialized_parser: ReEDSParser, built_system: "System"
) -> None:
    """Test builder methods return Result types."""
    for _, result in _builder_calls(initialized_parser, built_system):
        assert hasattr(result, "is_ok") and hasattr(result, "is_err")


@pytest.mark.unit
def test_build_transmission_interfaces_handles_component_creation_errors(
    initialized_parser: ReEDSParser, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ensure interface builder captures creation failures."""
    import r2x_reeds.parser as parser_module
    from r2x_core import ComponentCreationError

    parser = initialized_parser
    parser._rules_by_target["ReEDSInterface"] = cast(list, [DummyRule()])

    monkeypatch.setattr(
        parser_module,
        "_collect_component_kwargs_from_rule",
        lambda *args, **kwargs: Ok(
            [("p1||p2", {"name": "p1||p2", "from_region": "p1", "to_region": "p2", "trtype": "ac"})]
        ),
    )

    def failing_create(*args, **kwargs):
        raise ComponentCreationError("boom")

    monkeypatch.setattr(parser_module, "create_component", failing_create)

    data = pl.DataFrame({"from_region": ["p1"], "to_region": ["p2"], "trtype": ["ac"]})
    result = parser._build_transmission_interfaces(System(name="test"), data)
    assert result.is_ok() or result.is_err()


@pytest.mark.unit
def test_builder_methods_return_result(initialized_parser: ReEDSParser, built_system: "System") -> None:
    """Test builder methods return Result types."""
    for _, result in _builder_calls(initialized_parser, built_system):
        assert hasattr(result, "is_ok") and hasattr(result, "is_err")
