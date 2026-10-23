"""Public resource precedence regressions with source-specific CSV schemas."""

import json
import shutil
from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest
from infrasys.location import GeographicInfo

from r2x_core import DataStore, PluginContext
from r2x_reeds import ReEDSConfig, ReEDSParser
from r2x_reeds.models import ReEDSGenerator, ReEDSResourceBuild, ReEDSResourceSite
from tests.test_parser_current_core import configure_csv_sources, copy_package_config, write_current_meta

pytestmark = [pytest.mark.integration, pytest.mark.polars]


@pytest.fixture
def resource_run_path(reeds_run_path: Path, tmp_path: Path) -> Iterator[Path]:
    """Keep each controlled resource case independent and release copied data."""
    with TemporaryDirectory(prefix="resources-", dir=tmp_path) as directory:
        run_path = Path(directory) / "run"
        shutil.copytree(reeds_run_path, run_path)
        yield run_path


@pytest.mark.parametrize("source_has_rows", [True, False], ids=["source-primary", "empty-source"])
def test_resource_precedence_uses_real_file_aliases_and_preserves_selected_values(
    resource_run_path: Path, reeds_config: ReEDSConfig, source_has_rows: bool
) -> None:
    """Source rows own site values, while selected rows own build values."""
    inputs = resource_run_path / "inputs_case"
    outputs = resource_run_path / "outputs"
    source_header = "sc_point_gid,class,capacity,cf,region,supply_curve_cost_per_mw\n"
    source_rows = "416,1,341,0.2,p1,10\n" if source_has_rows else ""
    (inputs / "supplycurve_upv.csv").write_text(source_header + source_rows)
    candidate_rows = "0,416,48,-122,p1,1,18,254,0,0,0,20\n"
    if source_has_rows:
        candidate_rows += "1,417,47,-121,p1,1,19,300,0,0,0,25\n"
    (outputs / "df_sc_in_upv.csv").write_text(
        "sc_gid,sc_point_gid,latitude,longitude,region,class,bin,cap_avail,existing_capacity,"
        "online_year,retire_year,supply_curve_cost_per_mw\n" + candidate_rows
    )
    (outputs / "df_sc_out_upv_reduced.csv").write_text(
        "year,sc_gid,sc_point_gid,latitude,longitude,region,class,bin,supply_curve_cost_per_mw,"
        "built_capacity,investment_bool\n"
        "2009,0,416,50,-123,p1,1,18,30,0.37,1\n"
    )
    (outputs / "cap_ivrt.csv").write_text("i,v,r,t,Value\ncan-imports,init-1,p1,2032,100\n")
    write_current_meta(resource_run_path)
    config_path = copy_package_config(resource_run_path)
    defaults_path = config_path / "defaults.json"
    defaults = json.loads(defaults_path.read_text(encoding="utf-8"))
    defaults["resource_supply_curve_datasets"] = ["upv"]
    defaults_path.write_text(json.dumps(defaults), encoding="utf-8")
    configure_csv_sources(
        config_path,
        {"online_capacity": "outputs/cap_ivrt.csv"},
        include_all=True,
    )
    config = ReEDSConfig(
        solve_year=2032,
        weather_year=2012,
        case_name="resource-precedence-test",
        excluded_techs=[],
        config_path_override=config_path,
    )
    context = PluginContext(config=config, store=DataStore(path=resource_run_path))

    result = ReEDSParser.from_context(context).run()

    assert result.system is not None
    system = result.system
    sites = list(system.get_components(ReEDSResourceSite))
    builds = list(system.get_components(ReEDSResourceBuild))
    assert len(sites) == 1
    assert len(builds) == 1
    expected_capacity = 341.0 if source_has_rows else 254.0
    site = sites[0]
    build = builds[0]
    assert site.name == "upv_1_416"
    assert site.capacity == expected_capacity
    assert site.available_capacity == expected_capacity
    assert site.supply_curve_cost == (10.0 if source_has_rows else 20.0)
    assert build.name == "upv_1_2009_416"
    assert build.capacity == expected_capacity
    assert build.available_capacity == expected_capacity
    assert build.supply_curve_cost == 30.0
    assert build.built_capacity == 0.37
    assert build.investment_bool is True
    site_geography = system.get_supplemental_attributes_with_component(site, GeographicInfo)
    build_geography = system.get_supplemental_attributes_with_component(build, GeographicInfo)
    assert len(site_geography) == 1
    assert len(build_geography) == 1
    assert site_geography[0].geo_json["geometry"]["coordinates"] == [-122.0, 48.0]
    assert build_geography[0].geo_json["geometry"]["coordinates"] == [-123.0, 50.0]
    assert build_geography[0].geo_json["properties"]["year"] == 2009
    generators = list(system.get_components(ReEDSGenerator))
    assert len(generators) == 1
    assert generators[0].capacity == 100.0
