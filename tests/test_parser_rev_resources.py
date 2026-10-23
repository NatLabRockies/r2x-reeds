"""Public lifecycle tests for configured reV resource preparation."""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest

from r2x_core import DataStore, PluginContext
from r2x_reeds import ReEDSConfig, ReEDSParser
from r2x_reeds.models import ReEDSGenerator, ReEDSResourceBuild, ReEDSResourceSite

pytestmark = [pytest.mark.integration, pytest.mark.polars]


def resource_config(
    reeds_config: ReEDSConfig, *, parser_rules: dict[str, object] | None = None
) -> ReEDSConfig:
    """Configure one small resource case through the effective application assets."""
    defaults = copy.deepcopy(reeds_config.load_config()["defaults"])
    defaults["reserve_products"] = []
    effective_rules = parser_rules or copy.deepcopy(reeds_config.load_config()["parser_rules"])
    resource_stage = next(stage for stage in effective_rules["execution"] if stage["name"] == "resources")
    resource_stage["rules"] = ["resource_site_upv", "resource_build_upv"]
    overrides = {
        **reeds_config.asset_overrides,
        "defaults": defaults,
        "parser_rules": effective_rules,
    }
    return reeds_config.model_copy(update={"asset_overrides": overrides})


def write_generator_fixture(outputs: Path) -> None:
    """Keep generator identity/count stable while resource settings vary."""
    (outputs / "cap_ivrt.csv").write_text("i,v,r,t,Value\nGas-CC,init-1,p1,2032,100\n")
    (outputs / "heat_rate.csv").write_text("i,v,r,t,Value\nGas-CC,init-1,p1,2032,10\n")


def run_parser(run_path: Path, config: ReEDSConfig):
    """Run the public parser lifecycle against the local real DataStore."""
    store = DataStore.from_plugin_config(config, path=run_path)
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
    resource_mapping = next(
        mapping for mapping in parser_rules["mappings"] if mapping["name"] == "resource_site"
    )
    resource_mapping["getters"].pop("name")
    resource_mapping["field_map"]["name"] = "technology"
    config = resource_config(reeds_config, parser_rules=parser_rules)

    result = run_parser(run_path, config)

    assert result.system is not None
    sites = list(result.system.get_components(ReEDSResourceSite))
    builds = list(result.system.get_components(ReEDSResourceBuild))
    generators = list(result.system.get_components(ReEDSGenerator))
    assert len(sites) == 1
    assert sites[0].name == "upv"
    assert len(builds) == 1
    assert builds[0].name == "upv_1_2009_416"
    assert len(generators) == 1
    assert generators[0].capacity == 100.0


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
    config = resource_config(reeds_config)

    result = run_parser(run_path, config)

    assert result.system is not None
    assert list(result.system.get_components(ReEDSResourceSite)) == []
    assert list(result.system.get_components(ReEDSResourceBuild)) == []
    generators = list(result.system.get_components(ReEDSGenerator))
    assert len(generators) == 1
    assert generators[0].name == "gas-cc_init-1_p1"
    assert generators[0].capacity == 100.0
