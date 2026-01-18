from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest
from infrasys import System
from infrasys.exceptions import ISNotStored

from r2x_reeds.models.components import ReEDSDemand, ReEDSGenerator, ReEDSRegion
from r2x_reeds.sysmod import electrolyzer

pytestmark = [pytest.mark.integration]


def _build_regions() -> tuple[System, ReEDSRegion, ReEDSRegion]:
    system = System(name="test_electrolyzer")
    west = ReEDSRegion(name="west")
    east = ReEDSRegion(name="east")
    system.add_component(west)
    system.add_component(east)
    return system, west, east


def _add_generator(
    system: System,
    region: ReEDSRegion,
    name: str,
    technology: str = "Hydrogen Turbine",
    category: str = "hydrogen",
) -> ReEDSGenerator:
    generator = ReEDSGenerator(
        name=name, region=region, capacity=75.0, technology=technology, category=category
    )
    system.add_component(generator)
    return generator


def _write_csv(path: Path, data: dict[str, list]) -> str:
    pl.DataFrame(data).write_csv(path)
    return str(path)


def test_electrolyzer_scope_full_flow(tmp_path: Path) -> None:
    """Integration test that adds both load and hydrogen price profiles."""
    system, west, east = _build_regions()
    west_gen = _add_generator(system, west, "Hydrogen_GEN")
    east_gen = _add_generator(system, east, "Hydrogen_OTHER")

    hour_map_path = _write_csv(
        tmp_path / "hour_map.csv",
        {
            "hour": [1, 2, 3],
            "time_index": ["2024-01-01T00:00:00", "2024-01-01T01:00:00", "2024-01-01T02:00:00"],
            "season": ["winter", "winter", "winter"],
        },
    )
    load_path = _write_csv(
        tmp_path / "electrolyzer_load.csv",
        {
            "region": ["west", "west", "east"],
            "hour": [1, 2, 1],
            "load_MW": [5.0, 3.0, 0.5],
        },
    )
    price_path = _write_csv(
        tmp_path / "h2_price.csv",
        {
            "region": ["west", "west"],
            "month": ["m1", "m2"],
            "h2_price": [2.0, 3.0],
        },
    )

    electrolyzer.add_electrolizer_load(
        system,
        weather_year=2024,
        hour_map_fpath=hour_map_path,
        electrolyzer_load_fpath=load_path,
        h2_fuel_price_fpath=price_path,
    )

    demand = system.get_component(ReEDSDemand, "west_electrolyzer")
    assert demand.max_active_power == pytest.approx(5.0)
    assert demand.ext["load_type"] == "electrolyzer"
    assert system.has_time_series(demand) is True
    assert system.has_time_series(west_gen) is True
    assert system.has_time_series(east_gen) is False


def test_electrolyzer_scope_weather_missing(tmp_path: Path, caplog) -> None:
    """Weather year is required; without it nothing is loaded."""
    system, _, _ = _build_regions()
    hour_map_path = _write_csv(
        tmp_path / "hour_map.csv",
        {"hour": [1], "time_index": ["2024-01-01T00:00:00"], "season": ["winter"]},
    )

    electrolyzer.add_electrolizer_load(system, weather_year=None, hour_map_fpath=hour_map_path)

    assert "Weather year not specified" in caplog.text
    assert not list(system.get_components(ReEDSDemand))


def test_electrolyzer_scope_missing_hour_map(tmp_path: Path, caplog) -> None:
    """Missing hour map stops the plugin before modifying the system."""
    system, _, _ = _build_regions()
    load_path = _write_csv(
        tmp_path / "electrolyzer_load.csv", {"region": ["west"], "hour": [1], "load_MW": [5.0]}
    )
    price_path = _write_csv(
        tmp_path / "h2_price.csv", {"region": ["west"], "month": ["m1"], "h2_price": [2.0]}
    )

    electrolyzer.add_electrolizer_load(
        system,
        weather_year=2024,
        hour_map_fpath=None,
        electrolyzer_load_fpath=load_path,
        h2_fuel_price_fpath=price_path,
    )

    assert "hour_map data not available" in caplog.text
    assert not list(system.get_components(ReEDSDemand))


def test_electrolyzer_scope_empty_load(caplog) -> None:
    """Empty electrolyzer load data short-circuits the helper."""
    system, west, _ = _build_regions()
    load = pl.DataFrame({"region": [], "hour": [], "load_MW": []})
    hour_map = pl.DataFrame({"hour": [1], "time_index": ["2024-01-01T00:00:00"], "season": ["winter"]})

    electrolyzer._add_electrolyzer_load(system, load, hour_map, weather_year=2024)

    assert "Electrolyzer load data is empty" in caplog.text
    with pytest.raises(ISNotStored):
        system.get_component(ReEDSDemand, f"{west.name}_electrolyzer")


def test_electrolyzer_scope_empty_price(caplog) -> None:
    """Empty hydrogen price data avoids touching generators."""
    system, west, _ = _build_regions()
    _add_generator(system, west, "Hydrogen_GEN")

    electro_prices = pl.DataFrame({"region": [], "month": [], "h2_price": []})
    electrolyzer._add_hydrogen_fuel_price(system, electro_prices, weather_year=2024)

    assert "Hydrogen fuel price data is empty" in caplog.text
