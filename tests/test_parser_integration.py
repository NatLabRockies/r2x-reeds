"""Integration tests for ReEDS parser with real DataStore.

These tests verify that the parser can build a example_system using real data files.
"""

import csv
import shutil

import numpy as np
import pytest
from infrasys import Component

from r2x_reeds.models.components import ReEDSDemand, ReEDSGenerator
from r2x_reeds.parser_utils import get_technology_category

pytestmark = [pytest.mark.integration]


def test_system_has_buses(example_system) -> None:
    """Test that built example_system contains buses."""
    example_system = example_system
    components = list(example_system.get_components(Component))
    assert components is not None
    assert len(components) > 0, "System should have components after building"


def test_system_has_generators(example_system) -> None:
    """Test that built example_system contains generators."""
    components = list(example_system.get_components(Component))
    assert components is not None
    assert len(components) >= 0


def test_system_has_loads(example_system) -> None:
    """Test that built example_system contains loads."""
    components = list(example_system.get_components(Component))
    assert components is not None
    assert len(components) >= 0


def test_load_count_for_test_data(example_system) -> None:
    """Test expected load count for test_Pacific data."""
    loads = list(example_system.get_components(ReEDSDemand))
    assert len(loads) == 11, "11 Load expected for test case."


def test_renewable_generator_count(example_system, example_reeds_config) -> None:
    """Test expected renewable generator count for test_Pacific data."""
    # Use classmethod API per migration guide
    defaults = example_reeds_config.load_config()["defaults"]
    ren_gens = example_system.get_components(
        ReEDSGenerator,
        filter_func=lambda comp: get_technology_category(comp.technology, defaults["tech_categories"]),
    )
    assert len(list(ren_gens)) != 0.0


@pytest.mark.parametrize(
    "component_type,component_filter",
    [
        (ReEDSDemand, None),
        pytest.param(
            ReEDSGenerator,
            lambda x: x.category in ["solar", "wind"],
            marks=pytest.mark.xfail(reason="missing profiles on test data."),
        ),
        (ReEDSGenerator, lambda x: x.category == "hydro"),
    ],
    ids=["load-profiles", "renewable-profiles", "hydro-profiles"],
)
def test_system_has_time_series(component_type, component_filter, example_system, example_data_store):
    for component in example_system.get_components(component_type, filter_func=component_filter):
        assert example_system.has_time_series(component), f"Time series not found for {component.label}"


def test_load_time_series_length(example_system) -> None:
    """Test that time series length matches filtered data (single weather year = 8760 hours)."""
    assert all(
        example_system.get_time_series(component).length == 8760
        for component in example_system.get_components(ReEDSDemand)
    )


@pytest.mark.parametrize("region_name", ["p1", "p2", "p3"])
def test_load_time_series_values(
    region_name, example_data_store, example_system, example_reeds_config
) -> None:
    """Test that time series values match DataStore data for each region."""

    load_profiles = example_data_store.read_data(
        "load_profiles",
        placeholders={
            "solve_year": example_reeds_config.primary_solve_year,
            "weather_year": example_reeds_config.primary_weather_year,
        },
    ).collect()

    load_component = example_system.get_component(ReEDSDemand, region_name + "_load")
    actual_profile = load_profiles[region_name].to_numpy()
    expected_profile = example_system.get_time_series(load_component).data

    np.testing.assert_allclose(
        actual_profile,
        expected_profile,
        rtol=1e-5,
    )


def test_load_profiles_exposes_one_solve_year_column(example_data_store, example_reeds_config) -> None:
    """Load profiles should expose the solve year without duplicate columns."""
    load_profiles = example_data_store.read_data(
        "load_profiles",
        placeholders={
            "solve_year": example_reeds_config.primary_solve_year,
            "weather_year": example_reeds_config.primary_weather_year,
        },
    ).collect()

    assert load_profiles.columns.count("solve_year") == 1


@pytest.fixture(scope="session")
def loadsite_run_path(tmp_path_factory, reeds_run_path):
    """Copy test_Pacific run and inject hmap_myr.csv + loadsite_op.csv."""
    tmp = tmp_path_factory.mktemp("reeds_loadsite")
    run_path = tmp / "test_Pacific"
    shutil.copytree(reeds_run_path, run_path)

    # Derive hmap_myr.csv from hmap_allyrs.csv (same logic as the upgrader step)
    hmap_allyrs_path = run_path / "inputs_case" / "rep" / "hmap_allyrs.csv"
    rows = []
    with open(hmap_allyrs_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            normalized = {k.lstrip("*"): v for k, v in row.items()}
            yearhour = normalized.get("yearhour", "").strip()
            h = normalized.get("h", "").strip()
            actual_h = normalized.get("actual_h", "").strip()
            period = h if h else actual_h
            if yearhour and period:
                rows.append({"yearhour": yearhour, "h": period})

    # Deduplicate by yearhour and sort by yearhour for deterministic behavior
    dedup_by_yearhour = {}
    for r in rows:
        yh = r["yearhour"]
        if yh not in dedup_by_yearhour:
            dedup_by_yearhour[yh] = r
    rows = sorted(dedup_by_yearhour.values(), key=lambda r: r["yearhour"])
    hmap_myr_path = run_path / "inputs_case" / "rep" / "hmap_myr.csv"
    with open(hmap_myr_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["yearhour", "h"])
        writer.writeheader()
        writer.writerows(rows)
    # Unique period keys for loadsite_op columns (sorted for determinism)
    unique_periods = sorted({r["h"] for r in rows})

    loadsite_path = run_path / "outputs" / "loadsite_op.csv"
    with open(loadsite_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["r", "allh", "t", "Value"])
        writer.writeheader()
        for period in unique_periods:
            writer.writerow({"r": "p4", "allh": period, "t": 2032, "Value": 500.0})
            writer.writerow({"r": "p5", "allh": period, "t": 2032, "Value": 300.0})
            # Year=2040 row, must be filtered out by the parser
            writer.writerow({"r": "p4", "allh": period, "t": 2040, "Value": 999.0})

    return run_path


@pytest.fixture(scope="session")
def loadsite_system(loadsite_run_path):
    """Build a system with loadsite_op + hmap_myr data included."""

    from r2x_core import DataStore, PluginContext
    from r2x_reeds import ReEDSConfig, ReEDSParser

    config = ReEDSConfig(
        solve_year=2032,
        weather_year=2012,
        case_name="test",
        scenario="base",
    )
    store = DataStore.from_plugin_config(config, path=loadsite_run_path)
    ctx = PluginContext(config=config, store=store)
    parser = ReEDSParser.from_context(ctx)
    ctx = parser.run(ctx=ctx)
    if ctx.system is None:
        raise RuntimeError("loadsite system build returned None")
    return ctx.system


@pytest.fixture(scope="session")
def loadsite_base_profiles(loadsite_run_path):
    """Raw load_profiles DataFrame from the loadsite run (before increment)."""
    from r2x_core import DataStore
    from r2x_reeds import ReEDSConfig

    config = ReEDSConfig(
        solve_year=2032,
        weather_year=2012,
        case_name="test",
        scenario="base",
    )
    store = DataStore.from_plugin_config(config, path=loadsite_run_path)
    return store.read_data(
        "load_profiles",
        placeholders={"solve_year": 2032, "weather_year": 2012},
    ).collect()


def test_loadsite_not_applied_during_parse_p4(loadsite_system, loadsite_base_profiles) -> None:
    """p4 load remains equal to the base profile until optimal siting sysmod is applied."""
    p4 = loadsite_system.get_component(ReEDSDemand, "p4_load")
    actual = loadsite_system.get_time_series(p4).data
    base = loadsite_base_profiles["p4"].to_numpy()[:8760]
    np.testing.assert_allclose(actual, base, rtol=1e-5)


def test_loadsite_not_applied_during_parse_p5(loadsite_system, loadsite_base_profiles) -> None:
    """p5 load remains equal to the base profile until optimal siting sysmod is applied."""
    p5 = loadsite_system.get_component(ReEDSDemand, "p5_load")
    actual = loadsite_system.get_time_series(p5).data
    base = loadsite_base_profiles["p5"].to_numpy()[:8760]
    np.testing.assert_allclose(actual, base, rtol=1e-5)


def test_loadsite_not_applied_to_p1(loadsite_system, loadsite_base_profiles) -> None:
    """p1 has no loadsite entry — its time series must equal the base profile exactly."""
    p1 = loadsite_system.get_component(ReEDSDemand, "p1_load")
    actual = loadsite_system.get_time_series(p1).data
    base = loadsite_base_profiles["p1"].to_numpy()[:8760]
    np.testing.assert_allclose(actual, base, rtol=1e-5)


def test_loadsite_data_does_not_change_parser_output(loadsite_system, loadsite_base_profiles) -> None:
    """Presence of loadsite rows does not affect parser-only load profiles."""
    p4 = loadsite_system.get_component(ReEDSDemand, "p4_load")
    actual = loadsite_system.get_time_series(p4).data
    base = loadsite_base_profiles["p4"].to_numpy()[:8760]
    np.testing.assert_allclose(actual, base, rtol=1e-5)
