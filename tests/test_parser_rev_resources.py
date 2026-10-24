"""Public lifecycle tests for configured reV resource preparation."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from r2x_core import PluginContext
from r2x_reeds import ReEDSConfig, ReEDSParser
from r2x_reeds.models import ReEDSGenerator, ReEDSResourceBuild, ReEDSResourceSite
from tests.fixtures.data_fixtures import current_data_store

pytestmark = [pytest.mark.integration, pytest.mark.polars]


def resource_config(
    reeds_config: ReEDSConfig,
    tmp_path: Path,
    *,
    parser_rules: list[dict[str, object]] | None = None,
) -> ReEDSConfig:
    """Configure one small resource case through the public packaged-asset path."""
    config_path = tmp_path / "config"
    shutil.copytree(reeds_config.config_path, config_path)
    defaults_path = config_path / "defaults.json"
    defaults = json.loads(defaults_path.read_text())
    defaults["reserve_products"] = []
    defaults["resource_supply_curve_datasets"] = ["upv"]
    defaults_path.write_text(json.dumps(defaults))
    rules_path = config_path / "parser_rules.json"
    rules = parser_rules or json.loads(rules_path.read_text())
    rules_path.write_text(json.dumps(rules))
    return ReEDSConfig(
        solve_year=reeds_config.solve_year,
        weather_year=reeds_config.weather_year,
        case_name=reeds_config.case_name,
        scenario=reeds_config.scenario,
        config_path_override=config_path,
    )


def write_generator_fixture(outputs: Path) -> None:
    """Keep generator identity/count stable while resource settings vary."""
    (outputs / "cap_ivrt.csv").write_text("i,v,r,t,Value\nGas-CC,init-1,p1,2032,100\n")
    (outputs / "heat_rate.csv").write_text("i,v,r,t,Value\nGas-CC,init-1,p1,2032,10\n")


def run_parser(run_path: Path, config: ReEDSConfig):
    """Run the public parser lifecycle against the local real DataStore."""
    store = current_data_store(run_path)
    context = PluginContext(config=config, store=store)
    return ReEDSParser.from_context(context).run()


def test_resource_component_fields_follow_configured_rule_mapping(
    reeds_run_path: Path,
    tmp_path: Path,
    reeds_config: ReEDSConfig,
) -> None:
    """A configured resource mapping, not a parser loop, controls output names."""
    run_path = tmp_path / "run"
    shutil.copytree(reeds_run_path, run_path)
    inputs = run_path / "inputs_case"
    outputs = run_path / "outputs"
    (inputs / "supplycurve_upv.csv").write_text(
        "sc_point_gid,class,capacity,cf,region,supply_curve_cost_per_mw\n416,1,341,0.2,p1,10\n"
    )
    (outputs / "df_sc_in_upv.csv").write_text(
        "sc_point_gid,latitude,longitude,region,class,cap_avail,supply_curve_cost_per_mw\n"
        "416,48,-122,p1,1,254,20\n"
    )
    (outputs / "df_sc_out_upv_reduced.csv").write_text(
        "year,sc_point_gid,latitude,longitude,region,class,supply_curve_cost_per_mw,built_capacity,investment_bool\n"
        "2009,416,50,-123,p1,1,30,0.37,1\n"
    )
    write_generator_fixture(outputs)

    parser_rules_path = Path(__file__).parents[1] / "src" / "r2x_reeds" / "config" / "parser_rules.json"
    parser_rules = json.loads(parser_rules_path.read_text())
    resource_rule = next(rule for rule in parser_rules if rule.get("component_type") == "ReEDSResourceSite")
    resource_rule["fields"]["name"] = "technology"
    geo_rule = next(rule for rule in parser_rules if rule.get("source") == "resource_site_geo")
    geo_rule["owners"][0]["name_field"] = "technology"
    config = resource_config(reeds_config, tmp_path, parser_rules=parser_rules)

    result = run_parser(run_path, config)

    assert result.system is not None
    sites = list(result.system.get_components(ReEDSResourceSite))
    builds = list(result.system.get_components(ReEDSResourceBuild))
    generators = list(result.system.get_components(ReEDSGenerator))
    assert len(sites) == 1
    assert sites[0].name == "upv"
    assert sites[0].capacity == 341.0
    assert sites[0].available_capacity == 341.0
    assert sites[0].supply_curve_cost == 10.0
    assert len(builds) == 1
    assert builds[0].name == "upv_1_2009_416"
    assert len(generators) == 1
    assert generators[0].capacity == 100.0


def test_candidate_resource_rows_are_used_when_supply_curve_is_absent(
    reeds_run_path: Path,
    tmp_path: Path,
    reeds_config: ReEDSConfig,
) -> None:
    """Candidate rows provide sites only when that technology has no supply rows."""
    run_path = tmp_path / "run"
    shutil.copytree(reeds_run_path, run_path)
    (run_path / "inputs_case" / "supplycurve_upv.csv").unlink(missing_ok=True)
    outputs = run_path / "outputs"
    (outputs / "df_sc_in_upv.csv").write_text(
        "sc_point_gid,latitude,longitude,region,class,cap_avail,supply_curve_cost_per_mw\n"
        "416,48,-122,p1,1,254,20\n"
    )
    write_generator_fixture(outputs)

    result = run_parser(run_path, resource_config(reeds_config, tmp_path))

    assert result.system is not None
    sites = list(result.system.get_components(ReEDSResourceSite))
    assert [
        (site.name, site.capacity, site.available_capacity, site.supply_curve_cost) for site in sites
    ] == [("upv_1_416", 254.0, 254.0, 20.0)]


def test_missing_optional_resource_files_leave_generator_components_unchanged(
    reeds_run_path: Path,
    tmp_path: Path,
    reeds_config: ReEDSConfig,
) -> None:
    """Missing optional source, candidate, and selected files create no resource outputs."""
    run_path = tmp_path / "run"
    shutil.copytree(reeds_run_path, run_path)
    inputs = run_path / "inputs_case"
    outputs = run_path / "outputs"
    write_generator_fixture(outputs)
    for resource_path in (
        inputs / "supplycurve_upv.csv",
        outputs / "df_sc_in_upv.csv",
        outputs / "df_sc_out_upv_reduced.csv",
    ):
        resource_path.unlink(missing_ok=True)
    config = resource_config(reeds_config, tmp_path)

    result = run_parser(run_path, config)

    assert result.system is not None
    assert list(result.system.get_components(ReEDSResourceSite)) == []
    assert list(result.system.get_components(ReEDSResourceBuild)) == []
    generators = list(result.system.get_components(ReEDSGenerator))
    assert len(generators) == 1
    assert generators[0].name == "gas-cc_init-1_p1_2032"
    assert generators[0].capacity == 100.0
