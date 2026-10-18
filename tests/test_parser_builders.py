"""Public parser lifecycle coverage for configured Rule construction."""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import h5py
import numpy as np
import polars as pl
import pytest

from r2x_core import DataStore, PluginContext
from r2x_reeds import ReEDSConfig, ReEDSParser
from r2x_reeds.models.components import (
    ReEDSDemand,
    ReEDSEmission,
    ReEDSGenerator,
    ReEDSInterface,
    ReEDSRegion,
    ReEDSTransmissionLine,
)
from tests.fixtures.data_fixtures import csv_file_mapping

pytestmark = [pytest.mark.integration]


def test_public_lifecycle_builds_configured_region_transmission_and_emission_outputs(
    example_system,
) -> None:
    """Configured Rule stages preserve links and full Pacific outputs."""
    system = example_system
    regions = {region.name: region for region in system.get_components(ReEDSRegion)}
    demands = list(system.get_components(ReEDSDemand))
    interfaces = list(system.get_components(ReEDSInterface))
    lines = list(system.get_components(ReEDSTransmissionLine))
    generators = list(system.get_components(ReEDSGenerator))

    assert len(regions) == 11
    assert len(demands) == 11
    assert len(interfaces) == 17
    assert len(lines) == 17
    assert all(demand.region is regions[demand.region.name] for demand in demands)
    assert all(interface.from_region is regions[interface.from_region.name] for interface in interfaces)
    assert all(line.interface in interfaces for line in lines)

    line = system.get_component(ReEDSTransmissionLine, "p1_p2_ac")
    assert line.distance_miles == pytest.approx(132.46)
    assert line.line_cost_per_mw_mile == pytest.approx(2255.418390457496)
    assert line.losses == pytest.approx(0.01325)
    assert line.max_active_power.from_to == pytest.approx(9226.461)
    assert line.max_active_power.to_from == pytest.approx(4588.725)

    emissions = [
        attribute
        for generator in generators
        for attribute in system.get_supplemental_attributes_with_component(generator, ReEDSEmission)
    ]
    assert len(emissions) == 948


def test_public_lifecycle_routes_region_and_load_sources_through_asset_overrides(
    reeds_run_path: Path,
    tmp_path: Path,
) -> None:
    """The validated plan routes region records and load profiles to selected assets."""
    run_path = tmp_path / "run"
    shutil.copytree(reeds_run_path, run_path)
    input_case = run_path / "inputs_case"

    hierarchy_records = pl.read_csv(input_case / "hierarchy.csv").to_dicts()
    extra_region = dict(hierarchy_records[0])
    extra_region["*r"] = "source-selected"
    hierarchy_records.append(extra_region)
    alternate_hierarchy_path = input_case / "hierarchy_alternate.csv"
    pl.DataFrame(hierarchy_records).write_csv(alternate_hierarchy_path)

    alternate_load_path = input_case / "load_alternate.h5"
    shutil.copy2(input_case / "load.h5", alternate_load_path)
    with h5py.File(alternate_load_path, "r+") as load_file:
        columns = [
            column.decode() if isinstance(column, bytes) else str(column) for column in load_file["columns"]
        ]
        load_file["data"][:, columns.index("p1")] *= 2

    config_dir = Path(__file__).parents[1] / "src" / "r2x_reeds" / "config"
    file_mapping = csv_file_mapping()
    parser_rules = json.loads((config_dir / "parser_rules.json").read_text())
    physical_files = file_mapping["files"]
    alternate_hierarchy = copy.deepcopy(next(item for item in physical_files if item["name"] == "hierarchy"))
    alternate_hierarchy.update(name="alternate_hierarchy", fpath="inputs_case/hierarchy_alternate.csv")
    physical_files.append(alternate_hierarchy)
    alternate_load = copy.deepcopy(next(item for item in physical_files if item["name"] == "load_profiles"))
    alternate_load.update(name="alternate_load_profiles", fpath="inputs_case/load_alternate.h5")
    physical_files.append(alternate_load)
    file_mapping["tables"].append(
        {
            "name": "alternate_hierarchy_table",
            "source": "alternate_hierarchy",
            "required_columns": ["region_id"],
        }
    )

    region_rule = next(rule for rule in parser_rules["rules"] if rule["name"] == "region")
    region_rule["source"]["dataset"] = "alternate_hierarchy_table"
    load_rule = next(rule for rule in parser_rules["rules"] if rule["name"] == "load")
    load_rule["source"]["dataset"] = "alternate_load_profiles"
    parser_rules["required_datasets"] = ["alternate_hierarchy_table", "alternate_load_profiles"]

    config = ReEDSConfig(
        solve_year=2032,
        weather_year=2012,
        case_name="test",
        scenario="base",
        asset_overrides={"file_mapping": file_mapping, "parser_rules": parser_rules},
    )
    store = DataStore.from_plugin_config(config, path=run_path)
    selected_profiles = store.read_data(
        "alternate_load_profiles", placeholders={"solve_year": 2032, "weather_year": 2012}
    ).collect()
    context = PluginContext(config=config, store=store)
    result_context = ReEDSParser.from_context(context).run(ctx=context)

    assert result_context.system is not None
    system = result_context.system
    regions = {region.name: region for region in system.get_components(ReEDSRegion)}
    assert "source-selected" in regions
    demands = list(system.get_components(ReEDSDemand))
    assert all(demand.region is regions[demand.region.name] for demand in demands)

    p1_load = system.get_component(ReEDSDemand, "p1_load")
    expected_profile = selected_profiles["p1"].to_numpy()[:8760]
    assert p1_load.max_active_power == pytest.approx(float(selected_profiles["p1"].max()))
    np.testing.assert_allclose(system.get_time_series(p1_load).data, expected_profile)


@pytest.mark.parametrize(
    ("source", "mark_hierarchy_optional", "message"),
    [
        ({"kind": "dataset"}, False, "dataset"),
        ({"kind": "dataset", "dataset": "missing_hierarchy"}, False, "not registered"),
        ({"kind": "dataset", "dataset": "hierarchy"}, True, "marked optional"),
    ],
)
def test_rule_plan_rejects_invalid_required_region_sources(
    reeds_config: ReEDSConfig,
    data_store: DataStore,
    source: dict[str, str],
    mark_hierarchy_optional: bool,
    message: str,
) -> None:
    """Missing, unregistered, and optional region sources fail config preflight."""
    config_dir = Path(__file__).parents[1] / "src" / "r2x_reeds" / "config"
    parser_rules = json.loads((config_dir / "parser_rules.json").read_text())
    region_rule = next(rule for rule in parser_rules["rules"] if rule["name"] == "region")
    region_rule["source"] = source
    file_mapping = csv_file_mapping()
    if mark_hierarchy_optional:
        hierarchy = next(item for item in file_mapping["files"] if item["name"] == "hierarchy")
        hierarchy["info"]["is_optional"] = True

    config = reeds_config.model_copy(
        update={"asset_overrides": {"file_mapping": file_mapping, "parser_rules": parser_rules}}
    )
    store = (
        DataStore.from_plugin_config(config, path=data_store.folder)
        if mark_hierarchy_optional
        else data_store
    )
    parser = ReEDSParser.from_context(PluginContext(config=config, store=store))

    result = parser.on_validate_config()

    assert result.is_err()
    assert message in str(result.err())
