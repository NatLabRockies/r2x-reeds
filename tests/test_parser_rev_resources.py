"""Parser tests for reV/supply-curve resource components."""

from __future__ import annotations

import polars as pl
import pytest
from infrasys.location import GeographicInfo

from r2x_core import System
from r2x_reeds.getters import build_resource_name
from r2x_reeds.models import ReEDSResourceBuild, ReEDSResourceSite, ReEDSVariableGenerator
from r2x_reeds.parser import _coerce_optional_bool, _coerce_optional_float, _coerce_optional_int

pytestmark = [pytest.mark.unit]


def _prepare_parser(parser, sample_region):
    system = System(name="test")
    system.add_component(sample_region)
    parser._ctx.system = system
    parser._region_cache = {sample_region.name: sample_region}
    parser._resource_supply_curve_datasets = ("upv",)
    return system


def _resource_frames(include_selected: bool = True) -> dict[str, pl.LazyFrame | None]:
    source = pl.DataFrame(
        {
            "sc_point_gid": [416, 796, 797],
            "resource_class": [1, 1, 1],
            "capacity": [341.13, 920.14, 629.61],
            "capacity_factor": [0.1877, 0.1913, 0.1855],
            "region": ["p1", "p1", "p1"],
            "supply_curve_cost_per_mw": [577564.52875, 743009.39875, 823633.64125],
        }
    ).lazy()
    candidate = pl.DataFrame(
        {
            "sc_gid": [0, 4, 5],
            "sc_point_gid": [416, 796, 797],
            "latitude": [48.994427, 48.900375, 48.927494],
            "longitude": [-122.73455, -122.688286, -122.5285],
            "region": ["p1", "p1", "p1"],
            "resource_class": [1, 1, 1],
            "bin": [18, 25, 26],
            "available_capacity": [254.5761171604243, 686.6734177143724, 469.85664464240193],
            "existing_capacity": [0.0, 0.0, 0.0],
            "online_year": [0, 0, 0],
            "retire_year": [0, 0, 0],
            "supply_curve_cost_per_mw": [1165487.0620945962, 1317865.7838392514, 1339301.1627872088],
        }
    ).lazy()
    selected = (
        pl.DataFrame(
            {
                "year": [2009],
                "sc_gid": [0],
                "sc_point_gid": [416],
                "latitude": [48.994427],
                "longitude": [-122.73455],
                "region": ["p1"],
                "resource_class": [1],
                "bin": [18],
                "supply_curve_cost_per_mw": [1165487.0620945962],
                "built_capacity": [0.3731343025384888],
                "investment_bool": [1],
            }
        ).lazy()
        if include_selected
        else None
    )
    return {
        "upv_supply_curve": source,
        "df_sc_in_upv": candidate,
        "df_sc_out_upv_reduced": selected,
    }


def test_resource_components_preserve_candidates_and_selected_rows(parser, sample_region):
    system = _prepare_parser(parser, sample_region)
    generator = ReEDSVariableGenerator(
        name="upv_p1",
        region=sample_region,
        technology="upv",
        capacity=10.0,
        resource_class="class1",
    )
    system.add_component(generator)

    frames = _resource_frames(include_selected=True)
    parser.read_data_file = lambda name: frames.get(name)  # type: ignore[assignment]

    result = parser._build_resource_components(system)

    assert not result.is_err()

    sites = list(system.get_components(ReEDSResourceSite))
    builds = list(system.get_components(ReEDSResourceBuild))
    generators = list(system.get_components(ReEDSVariableGenerator))

    assert len(sites) == 3
    assert len(builds) == 1
    assert len(generators) == 1
    assert generators[0].capacity == 10.0
    assert generators[0].name == "upv_p1"

    first_site = sites[0]
    assert first_site.sc_point_gid == 416
    assert first_site.resource_class == "1"
    assert first_site.capacity == 341.13
    assert first_site.available_capacity == pytest.approx(254.5761171604243)
    assert first_site.capacity_factor == pytest.approx(0.1877)
    site_geo = system.get_supplemental_attributes_with_component(first_site, GeographicInfo)
    assert len(site_geo) == 1
    assert site_geo[0].geo_json["geometry"]["coordinates"] == pytest.approx([-122.73455, 48.994427])

    first_build = builds[0]
    assert first_build.year == 2009
    assert first_build.sc_point_gid == 416
    assert first_build.built_capacity == pytest.approx(0.3731343025384888)
    assert first_build.investment_bool is True
    assert first_build.capacity == 341.13
    assert first_build.available_capacity == pytest.approx(254.5761171604243)
    build_geo = system.get_supplemental_attributes_with_component(first_build, GeographicInfo)
    assert len(build_geo) == 1
    assert build_geo[0].geo_json["properties"]["year"] == 2009


def test_resource_components_skip_missing_selected_output(parser, sample_region):
    system = _prepare_parser(parser, sample_region)
    generator = ReEDSVariableGenerator(
        name="upv_p1",
        region=sample_region,
        technology="upv",
        capacity=10.0,
        resource_class="class1",
    )
    system.add_component(generator)

    frames = _resource_frames(include_selected=False)
    parser.read_data_file = lambda name: frames.get(name)  # type: ignore[assignment]

    result = parser._build_resource_components(system)

    assert not result.is_err()

    sites = list(system.get_components(ReEDSResourceSite))
    builds = list(system.get_components(ReEDSResourceBuild))
    generators = list(system.get_components(ReEDSVariableGenerator))

    assert len(sites) == 3
    assert len(builds) == 0
    assert len(generators) == 1
    assert generators[0].capacity == 10.0
    assert generators[0].name == "upv_p1"


def test_resource_defaults_and_geographic_info_helpers(parser, sample_region):
    system = _prepare_parser(parser, sample_region)

    parser._defaults = {"resource_supply_curve_datasets": ["upv", "wind-ons"]}
    assert not parser._prepare_default_metadata().is_err()
    assert parser._resource_supply_curve_datasets == ("upv", "wind-ons")

    kwargs = {
        "name": "upv_1_416",
        "technology": "upv",
        "sc_point_gid": 416,
        "resource_class": "1",
    }
    assert parser._resource_geographic_info(kwargs) is None

    skipped = parser._resource_component_kwargs(
        row={"region": "p1", "sc_point_gid": 416, "resource_class": "1"},
        technology="upv",
        selected_only=True,
        system=system,
    )
    assert skipped is None

    selected = parser._resource_component_kwargs(
        row={
            "region": "p1",
            "sc_point_gid": 416,
            "resource_class": "1",
            "year": 2009.0,
            "built_capacity": 1.5,
            "investment_bool": 1,
        },
        technology="upv",
        selected_only=True,
        system=system,
    )
    assert selected is not None
    assert selected["year"] == 2009
    assert selected["name"] == "upv_1_2009_416"


def test_resource_helpers_coerce_and_merge(parser, sample_region):
    _prepare_parser(parser, sample_region)

    assert _coerce_optional_int(True) == 1
    assert _coerce_optional_int("7") == 7
    assert _coerce_optional_int("not-an-int") is None
    assert _coerce_optional_float("2.5") == pytest.approx(2.5)
    assert _coerce_optional_float("bad") is None
    assert _coerce_optional_bool("yes") is True
    assert _coerce_optional_bool("0") is False

    base = pl.DataFrame(
        {
            "sc_point_gid": [416],
            "resource_class": [1],
            "region": ["p1"],
            "capacity": [341.13],
            "capacity_factor": [0.1877],
            "available_capacity": [None],
            "supply_curve_cost_per_mw": [577564.52875],
        }
    )
    enrichment = pl.DataFrame(
        {
            "sc_point_gid": [416],
            "resource_class": [1],
            "latitude": [48.994427],
            "longitude": [-122.73455],
            "available_capacity": [254.5761171604243],
            "existing_capacity": [0.0],
            "online_year": [0],
            "retire_year": [0],
            "bin": [18],
            "sc_gid": [0],
        }
    )

    normalized = parser._normalize_resource_frame(base, source_name="upv")
    assert normalized.columns.count("resource_class") == 1
    assert normalized.columns.count("capacity_factor") == 1
    assert normalized.columns.count("available_capacity") == 1
    assert normalized[0, "technology"] == "upv"

    legacy_aliases = parser._normalize_resource_frame(
        pl.DataFrame({"cf": [0.25], "cost_per_mw": [1200.0]}),
        source_name="wind-ofs",
    )
    assert legacy_aliases[0, "capacity_factor"] == pytest.approx(0.25)
    assert legacy_aliases[0, "supply_curve_cost"] == pytest.approx(1200.0)

    merged = parser._merge_resource_frames(normalized, enrichment, "upv")
    merged_row = merged.row(0, named=True)

    assert merged_row["available_capacity"] == pytest.approx(254.5761171604243)
    assert merged_row["capacity_factor"] == pytest.approx(0.1877)
    assert merged_row["latitude"] == pytest.approx(48.994427)
    assert merged_row["longitude"] == pytest.approx(-122.73455)
    assert merged_row["bin"] == 18
    assert merged_row["sc_gid"] == 0
    assert build_resource_name("upv", 1.0, 416, None) == "upv_1.0_416"
    assert build_resource_name("upv", "1", 416, 2009) == "upv_1_2009_416"
