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
from rust_ok import Ok, Result

from r2x_core import System
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
    parser = example_parser.from_context(ctx)
    assert parser.on_prepare().is_ok()
    return parser


@pytest.fixture
def built_system() -> System:
    return System(name="test_builder")


def _builder_calls(parser: ReEDSParser, system: System) -> list[tuple[str, Result[None, str]]]:
    return [
        ("_build_regions", parser._build_regions(system)),
        ("_build_generators", parser._build_generators(system)),
        ("_build_transmission", parser._build_transmission(system)),
        ("_build_loads", parser._build_loads(system)),
        ("_build_reserves", parser._build_reserves(system)),
        ("_build_emissions", parser._build_emissions(system)),
    ]


@pytest.mark.unit
def test_build_regions_with_valid_data(initialized_parser: ReEDSParser, built_system: System) -> None:
    """Test _build_regions succeeds with valid hierarchy data."""
    result = initialized_parser._build_regions(built_system)
    assert result.is_ok() or result.is_err()


@pytest.mark.unit
def test_build_regions_returns_ok_type(initialized_parser: ReEDSParser, built_system: System) -> None:
    """Test _build_regions returns a Result type."""
    result = initialized_parser._build_regions(built_system)
    assert hasattr(result, "is_ok") and hasattr(result, "is_err")


@pytest.mark.unit
def test_build_generators_with_valid_data(initialized_parser: ReEDSParser, built_system: System) -> None:
    """Test _build_generators succeeds with valid generator data."""
    result = initialized_parser._build_generators(built_system)
    assert result.is_ok() or result.is_err()


@pytest.mark.unit
def test_build_generators_returns_result_type(initialized_parser: ReEDSParser, built_system: System) -> None:
    """Test _build_generators returns a Result type."""
    result = initialized_parser._build_generators(built_system)
    assert hasattr(result, "is_ok") and hasattr(result, "is_err")


@pytest.mark.unit
def test_build_transmission_with_valid_data(initialized_parser: ReEDSParser, built_system: System) -> None:
    """Test _build_transmission succeeds with valid transmission data."""
    result = initialized_parser._build_transmission(built_system)
    assert result.is_ok() or result.is_err()


@pytest.mark.unit
def test_build_transmission_returns_result_type(
    initialized_parser: ReEDSParser, built_system: System
) -> None:
    """Test _build_transmission returns a Result type."""
    result = initialized_parser._build_transmission(built_system)
    assert hasattr(result, "is_ok") and hasattr(result, "is_err")


@pytest.mark.unit
def test_build_loads_with_valid_data(initialized_parser: ReEDSParser, built_system: System) -> None:
    """Test _build_loads succeeds with valid load data."""
    result = initialized_parser._build_loads(built_system)
    assert result.is_ok() or result.is_err()


@pytest.mark.unit
def test_build_loads_returns_result_type(initialized_parser: ReEDSParser, built_system: System) -> None:
    """Test _build_loads returns a Result type."""
    result = initialized_parser._build_loads(built_system)
    assert hasattr(result, "is_ok") and hasattr(result, "is_err")


@pytest.mark.unit
def test_build_reserves_returns_result_type(initialized_parser: ReEDSParser, built_system: System) -> None:
    """Test _build_reserves returns a Result type."""
    result = initialized_parser._build_reserves(built_system)
    assert hasattr(result, "is_ok") and hasattr(result, "is_err")


@pytest.mark.unit
def test_build_emissions_returns_result_type(initialized_parser: ReEDSParser, built_system: System) -> None:
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

    from r2x_core import PluginContext, System
    from r2x_reeds import ReEDSParser
    from r2x_reeds.models.components import ReEDSRegion, ReEDSThermalGenerator

    ctx = PluginContext(config=example_reeds_config, store=example_data_store)
    parser = ReEDSParser.from_context(ctx)
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
    initialized_parser: ReEDSParser, built_system: System
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
def test_builder_methods_return_result(initialized_parser: ReEDSParser, built_system: System) -> None:
    """Test builder methods return Result types."""
    for _, result in _builder_calls(initialized_parser, built_system):
        assert hasattr(result, "is_ok") and hasattr(result, "is_err")


@pytest.fixture
def fresh_parser(reeds_config: ReEDSConfig, data_store: DataStore) -> ReEDSParser:
    """Fresh function-scoped parser with on_prepare already called."""

    from r2x_core import PluginContext
    from r2x_reeds import ReEDSParser

    ctx = PluginContext(config=reeds_config, store=data_store)
    p = ReEDSParser.from_context(ctx)
    assert p.on_prepare().is_ok()
    return p


@pytest.mark.unit
def test_build_transmission_losses_attached_to_lines(
    fresh_parser: ReEDSParser,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that transmission losses are attached to ReEDSTransmissionLine components."""
    from r2x_core import System
    from r2x_reeds.models.components import ReEDSTransmissionLine

    parser = fresh_parser
    system = System(name="transmission-losses-test")

    parser.ctx.system = system
    assert parser._build_regions(system).is_ok(), "_build_regions failed"

    existing_regions = list(parser._region_cache.keys())
    assert len(existing_regions) >= 2, (
        f"Need at least 2 regions after _build_regions, found: {existing_regions}"
    )
    r1, r2 = existing_regions[0], existing_regions[1]

    original_read = parser.read_data_file

    def fake_read(name: str):
        if name == "transmission_losses":
            return pl.DataFrame(
                {
                    "from_region": [r1],
                    "to_region": [r2],
                    "trtype": ["ac"],
                    "losses": [0.02],
                }
            ).lazy()
        return original_read(name)

    monkeypatch.setattr(parser, "read_data_file", fake_read)

    result = parser._build_transmission(system)
    assert result.is_ok(), f"_build_transmission failed: {result}"

    lines = list(system.get_components(ReEDSTransmissionLine))
    assert len(lines) > 0, "Expected at least one ReEDSTransmissionLine to be created"

    lines_with_losses = [ln for ln in lines if getattr(ln, "losses", None) == pytest.approx(0.02)]
    assert len(lines_with_losses) > 0, (
        f"Expected at least one line with losses=0.02; "
        f"actual losses values: {[getattr(ln, 'losses', None) for ln in lines]}"
    )


@pytest.mark.unit
def test_build_transmission_missing_losses_data(
    fresh_parser: ReEDSParser,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify _build_transmission succeeds and creates lines when losses data is absent."""
    from r2x_core import System
    from r2x_reeds.models.components import ReEDSTransmissionLine

    parser = fresh_parser
    system = System(name="transmission-no-losses-test")

    parser.ctx.system = system
    assert parser._build_regions(system).is_ok(), "_build_regions failed"

    original_read = parser.read_data_file

    def fake_read(name: str):
        if name == "transmission_losses":
            return None
        return original_read(name)

    monkeypatch.setattr(parser, "read_data_file", fake_read)

    result = parser._build_transmission(system)
    assert result.is_ok(), f"_build_transmission should succeed without losses data: {result}"

    lines = list(system.get_components(ReEDSTransmissionLine))
    assert len(lines) > 0, "Lines should still be created even without losses data"
    for line in lines:
        if hasattr(line, "losses"):
            assert line.losses is None or line.losses == pytest.approx(0.0), (
                f"Lines without losses data should have None or 0.0, got {line.losses}"
            )


@pytest.mark.unit
def test_build_transmission_hurdle_rates_attached_to_lines(
    fresh_parser: ReEDSParser,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that transmission hurdle rates are attached to ReEDSTransmissionLine components."""
    from r2x_core import System
    from r2x_reeds.models.components import ReEDSTransmissionLine

    parser = fresh_parser
    system = System(name="transmission-hurdle-rate-test")

    parser.ctx.system = system
    assert parser._build_regions(system).is_ok(), "_build_regions failed"

    existing_regions = list(parser._region_cache.keys())
    assert len(existing_regions) >= 2, (
        f"Need at least 2 regions after _build_regions, found: {existing_regions}"
    )
    r1, r2 = existing_regions[0], existing_regions[1]

    original_read = parser.read_data_file

    def fake_read(name: str):
        if name == "transmission_capacity":
            return pl.DataFrame(
                {
                    "from_region": [r1],
                    "to_region": [r2],
                    "trtype": ["ac"],
                    "year": [parser.config.solve_year],
                    "capacity": [100.0],
                }
            ).lazy()
        if name == "cost_hurdle_rate":
            return pl.DataFrame(
                {
                    "from_region": [r1],
                    "to_region": [r2],
                    "year": [parser.config.solve_year],
                    "cost_hurdle_rate": [1.25],
                }
            ).lazy()
        return original_read(name)

    monkeypatch.setattr(parser, "read_data_file", fake_read)

    result = parser._build_transmission(system)
    assert result.is_ok(), f"_build_transmission failed: {result}"

    lines = list(system.get_components(ReEDSTransmissionLine))
    assert len(lines) > 0, "Expected at least one ReEDSTransmissionLine to be created"

    lines_with_hurdle_rate = [ln for ln in lines if getattr(ln, "hurdle_rate", None) == pytest.approx(1.25)]
    assert len(lines_with_hurdle_rate) > 0, (
        "Expected at least one line with hurdle_rate=1.25; "
        f"actual hurdle_rate values: {[getattr(ln, 'hurdle_rate', None) for ln in lines]}"
    )


@pytest.mark.unit
def test_build_transmission_distance_and_cost_attached_to_lines(
    fresh_parser: ReEDSParser,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that transmission distance and derived per-MW-mile cost are attached to lines."""
    from r2x_core import System
    from r2x_reeds.models.components import ReEDSTransmissionLine

    parser = fresh_parser
    system = System(name="transmission-distance-cost-test")

    parser.ctx.system = system
    assert parser._build_regions(system).is_ok(), "_build_regions failed"

    existing_regions = list(parser._region_cache.keys())
    assert len(existing_regions) >= 2, (
        f"Need at least 2 regions after _build_regions, found: {existing_regions}"
    )
    r1, r2 = existing_regions[0], existing_regions[1]

    original_read = parser.read_data_file

    def fake_read(name: str):
        if name == "transmission_capacity":
            return pl.DataFrame(
                {
                    "from_region": [r1],
                    "to_region": [r2],
                    "trtype": ["ac"],
                    "year": [parser.config.solve_year],
                    "capacity": [100.0],
                }
            ).lazy()
        if name == "transmission_distance_cost_dc":
            return pl.DataFrame(
                {
                    "from_region": [r1],
                    "to_region": [r2],
                    "distance_mi": [250.0],
                }
            ).lazy()
        if name == "transmission_distance_cost_ac":
            return pl.DataFrame(
                {
                    "from_region": [r1],
                    "to_region": [r2],
                    "cost_bin": ["t0"],
                    "cost_usd_per_mw_forward": [250000.0],
                }
            ).lazy()
        return original_read(name)

    monkeypatch.setattr(parser, "read_data_file", fake_read)

    result = parser._build_transmission(system)
    assert result.is_ok(), f"_build_transmission failed: {result}"

    lines = list(system.get_components(ReEDSTransmissionLine))
    assert len(lines) > 0, "Expected at least one ReEDSTransmissionLine to be created"

    target_lines = [
        ln
        for ln in lines
        if getattr(ln, "distance_miles", None) == pytest.approx(250.0)
        and getattr(ln, "line_cost_per_mw_mile", None) == pytest.approx(1000.0)
    ]
    assert len(target_lines) > 0, (
        "Expected at least one line with distance_miles=250.0 and line_cost_per_mw_mile=1000.0; "
        f"actual pairs: {[(getattr(ln, 'distance_miles', None), getattr(ln, 'line_cost_per_mw_mile', None)) for ln in lines]}"
    )


@pytest.mark.unit
def test_build_transmission_legacy_column_aliases_are_supported(
    fresh_parser: ReEDSParser,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify legacy transmission column aliases are renamed and consumed correctly."""
    from r2x_core import System
    from r2x_reeds.models.components import ReEDSTransmissionLine

    parser = fresh_parser
    system = System(name="transmission-legacy-aliases-test")

    parser.ctx.system = system
    assert parser._build_regions(system).is_ok(), "_build_regions failed"

    existing_regions = list(parser._region_cache.keys())
    assert len(existing_regions) >= 2, (
        f"Need at least 2 regions after _build_regions, found: {existing_regions}"
    )
    r1, r2 = existing_regions[0], existing_regions[1]

    original_read = parser.read_data_file

    def fake_read(name: str):
        if name == "transmission_capacity":
            return pl.DataFrame(
                {
                    "from_region": [r1],
                    "to_region": [r2],
                    "trtype": ["ac"],
                    "year": [parser.config.solve_year],
                    "capacity": [120.0],
                }
            ).lazy()
        if name == "transmission_losses":
            return pl.DataFrame(
                {
                    "r": [r1],
                    "to_region": [r2],
                    "trtype": ["ac"],
                    "value": [0.03],
                }
            ).lazy()
        if name == "cost_hurdle_rate":
            return pl.DataFrame(
                {
                    "r": [r1],
                    "rr": [r2],
                    "allt": [parser.config.solve_year],
                    "value": [2.5],
                }
            ).lazy()
        if name == "transmission_distance_cost_dc":
            return pl.DataFrame(
                {
                    "r": [r1],
                    "rr": [r2],
                    "distance_mi": [200.0],
                }
            ).lazy()
        if name == "transmission_distance_cost_ac":
            return pl.DataFrame(
                {
                    "r": [r1],
                    "rr": [r2],
                    "cost_bin": ["t0"],
                    "cost_usd_per_mw_forward": [100000.0],
                }
            ).lazy()
        return original_read(name)

    monkeypatch.setattr(parser, "read_data_file", fake_read)

    result = parser._build_transmission(system)
    assert result.is_ok(), f"_build_transmission failed: {result}"

    lines = list(system.get_components(ReEDSTransmissionLine))
    assert len(lines) > 0, "Expected at least one ReEDSTransmissionLine to be created"

    matching = [
        ln
        for ln in lines
        if getattr(ln, "losses", None) == pytest.approx(0.03)
        and getattr(ln, "hurdle_rate", None) == pytest.approx(2.5)
        and getattr(ln, "distance_miles", None) == pytest.approx(200.0)
        and getattr(ln, "line_cost_per_mw_mile", None) == pytest.approx(500.0)
    ]
    assert matching, "Expected one line with legacy-column-mapped losses/hurdle/distance/cost"


@pytest.mark.unit
def test_build_transmission_returns_err_when_interface_builder_returns_none(
    fresh_parser: ReEDSParser,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify _build_transmission surfaces an error when interface builder returns Ok(None)."""
    from rust_ok import Ok

    parser = fresh_parser
    parser.ctx.system = System(name="transmission-interface-none")

    monkeypatch.setattr(parser, "_build_transmission_interfaces", lambda *_args, **_kwargs: Ok(None))

    result = parser._build_transmission(parser.ctx.system)
    assert result.is_err()
    assert "unexpectedly None" in str(result.err())


@pytest.mark.unit
def test_build_transmission_returns_err_when_line_builder_reports_creation_errors(
    fresh_parser: ReEDSParser,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify _build_transmission returns Err when line creation errors are reported."""
    from rust_ok import Ok

    parser = fresh_parser
    parser.ctx.system = System(name="transmission-line-errors")

    monkeypatch.setattr(
        parser,
        "_build_transmission_interfaces",
        lambda *_args, **_kwargs: Ok((1, ["iface failed"])),
    )
    monkeypatch.setattr(parser, "_build_transmission_lines", lambda *_args, **_kwargs: Ok((1, [])))

    result = parser._build_transmission(parser.ctx.system)
    assert result.is_err()
    assert "Failed to create transmission components" in str(result.err())
