"""Public parser lifecycle coverage for configured Rule construction."""

from __future__ import annotations

import copy
import json
import shutil
from importlib.resources import files
from pathlib import Path

import h5py
import numpy as np
import polars as pl
import pytest

from r2x_core import (
    DataStore,
    PluginContext,
    RulePlan,
    SelectedMappingRoute,
    System,
    apply_mapping_records,
)
from r2x_reeds import ReEDSConfig, ReEDSParser
from r2x_reeds.models.components import (
    ReEDSDemand,
    ReEDSEmission,
    ReEDSGenerator,
    ReEDSHydroGenerator,
    ReEDSInterface,
    ReEDSRegion,
    ReEDSStorage,
    ReEDSThermalGenerator,
    ReEDSTransmissionLine,
    ReEDSVariableGenerator,
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


def test_public_lifecycle_uses_configured_generator_attribute_sources(
    reeds_run_path: Path,
    example_reeds_config: ReEDSConfig,
    example_data_store: DataStore,
    example_system,
    tmp_path: Path,
) -> None:
    """Generator preparation reads six configured attributes through explicit joins."""
    heat_rate_generator = next(
        generator
        for generator in example_system.get_components(ReEDSThermalGenerator)
        if generator.vintage is not None
    )
    capacity = example_data_store.read_data(
        "online_capacity",
        placeholders={
            "solve_year": example_reeds_config.solve_year,
            "weather_year": example_reeds_config.weather_year,
        },
    ).collect()
    capacity_rows = capacity.filter(
        (pl.col("technology") == heat_rate_generator.technology)
        & (pl.col("region") == heat_rate_generator.region.name)
        & (pl.col("vintage") == heat_rate_generator.vintage)
    )
    assert capacity_rows.height == 1
    capacity_row = capacity_rows.row(0, named=True)

    run_path = tmp_path / "run"
    shutil.copytree(reeds_run_path, run_path)
    selected_attributes = {
        "technology": capacity_row["technology"],
        "region": capacity_row["region"],
        "year": capacity_row["year"],
        "vintage": capacity_row["vintage"],
        "heat_rate": 123456.0,
        "forced_outage_rate": 0.31,
        "planned_outage_rate": 0.42,
        "vom_cost": 23.5,
        "maxage_years": 99,
        "startup_cost": 17.5,
    }
    pl.DataFrame([selected_attributes]).write_csv(
        run_path / "inputs_case" / "generator_attributes_selected.csv"
    )

    file_mapping = csv_file_mapping()
    file_mapping["files"].append(
        {
            "name": "selected_generator_attributes",
            "fpath": "inputs_case/generator_attributes_selected.csv",
            "info": {"is_input": False, "is_optional": False},
            "proc_spec": {
                "column_schema": {
                    "year": "int",
                    "heat_rate": "float",
                    "forced_outage_rate": "float",
                    "planned_outage_rate": "float",
                    "vom_cost": "float",
                    "maxage_years": "int",
                    "startup_cost": "float",
                }
            },
        }
    )
    table = next(item for item in file_mapping["tables"] if item["name"] == "generator_inputs")
    for join in table["joins"]:
        join["source"] = "selected_generator_attributes"
    config = example_reeds_config.model_copy(update={"asset_overrides": {"file_mapping": file_mapping}})
    store = DataStore.from_plugin_config(config, path=run_path)
    placeholders = {
        "solve_year": config.solve_year,
        "weather_year": config.weather_year,
    }
    prepared_inputs = store.read_data("generator_inputs", placeholders=placeholders).collect()
    selected_input = prepared_inputs.filter(
        (pl.col("technology") == capacity_row["technology"])
        & (pl.col("region") == capacity_row["region"])
        & (pl.col("year") == capacity_row["year"])
        & (pl.col("vintage") == capacity_row["vintage"])
    )
    assert selected_input.height == 1
    assert selected_input.select(
        "heat_rate",
        "forced_outage_rate",
        "planned_outage_rate",
        "vom_cost",
        "maxage_years",
        "startup_cost",
    ).row(0) == (123456.0, 0.31, 0.42, 23.5, 99, 17.5)
    assert prepared_inputs["heat_rate"].null_count() > 0
    context = PluginContext(config=config, store=store)
    result = ReEDSParser.from_context(context).run(ctx=context)

    assert result.system is not None
    generator = result.system.get_component(ReEDSThermalGenerator, heat_rate_generator.name)
    assert generator.heat_rate == pytest.approx(selected_attributes["heat_rate"])
    assert generator.forced_outage_rate == pytest.approx(selected_attributes["forced_outage_rate"])
    assert generator.planned_outage_rate == pytest.approx(selected_attributes["planned_outage_rate"])
    assert generator.vom_cost == pytest.approx(selected_attributes["vom_cost"])
    assert generator.startup_cost == pytest.approx(selected_attributes["startup_cost"])
    assert generator.max_age == selected_attributes["maxage_years"]
    assert generator.capacity == pytest.approx(heat_rate_generator.capacity)
    baseline_generators = {item.name: item for item in example_system.get_components(ReEDSGenerator)}
    selected_generators = {item.name: item for item in result.system.get_components(ReEDSGenerator)}
    assert selected_generators.keys() == baseline_generators.keys()
    for name, baseline in baseline_generators.items():
        selected = selected_generators[name]
        assert selected.technology == baseline.technology
        assert selected.capacity == pytest.approx(baseline.capacity)
        if baseline.fom_cost is None:
            assert selected.fom_cost is None
        else:
            assert selected.fom_cost == pytest.approx(baseline.fom_cost)

    baseline_annual_fom = sum(
        item.capacity * item.fom_cost for item in baseline_generators.values() if item.fom_cost is not None
    )
    selected_annual_fom = sum(
        item.capacity * item.fom_cost for item in selected_generators.values() if item.fom_cost is not None
    )
    assert selected_annual_fom == pytest.approx(baseline_annual_fom)


def test_generator_classification_and_exclusions_follow_effective_configuration(
    reeds_run_path: Path,
    example_reeds_config: ReEDSConfig,
    tmp_path: Path,
) -> None:
    """The configured category and exclusion policy controls generator outputs."""
    run_path = tmp_path / "run"
    shutil.copytree(reeds_run_path, run_path)
    outputs = run_path / "outputs"
    (outputs / "cap_ivrt.csv").write_text(
        "i,v,r,t,Value\nGas-CC,init-1,p1,2032,100\nGas-CT,init-1,p1,2032,50\n"
    )
    (outputs / "heat_rate.csv").write_text(
        "i,v,r,t,Value\nGas-CC,init-1,p1,2032,10\nGas-CT,init-1,p1,2032,11\n"
    )

    defaults = example_reeds_config.load_config()["defaults"]
    defaults["reserve_products"] = []
    parser_rules = copy.deepcopy(example_reeds_config.load_config()["parser_rules"])
    next(stage for stage in parser_rules["execution"] if stage["name"] == "resources")["rules"] = []
    defaults["tech_categories"]["wind"]["prefixes"].append("gas-cc")
    config = example_reeds_config.model_copy(
        update={
            "excluded_techs": ["gas-ct"],
            "asset_overrides": {
                **example_reeds_config.asset_overrides,
                "parser_rules": parser_rules,
                "file_mapping": csv_file_mapping(),
                "defaults": defaults,
            },
        }
    )
    store = DataStore.from_plugin_config(config, path=run_path)
    context = PluginContext(config=config, store=store)

    result = ReEDSParser.from_context(context).run()

    assert result.system is not None
    generators = list(result.system.get_components(ReEDSGenerator))
    assert [generator.name for generator in generators] == ["gas-cc_p1"]
    assert isinstance(generators[0], ReEDSVariableGenerator)
    assert generators[0].capacity == pytest.approx(100.0)
    assert generators[0].category == "wind"


def test_public_lifecycle_uses_configured_storage_duration_source(
    reeds_run_path: Path,
    example_reeds_config: ReEDSConfig,
    tmp_path: Path,
) -> None:
    """A prepared-table join override controls the storage component value."""
    run_path = tmp_path / "run"
    shutil.copytree(reeds_run_path, run_path)
    outputs = run_path / "outputs"
    (outputs / "cap_ivrt.csv").write_text("i,v,r,t,Value\nbattery_4,init-1,p1,2032,100\n")
    (outputs / "storage_duration.csv").write_text("i,value\nbattery_4,4\n")
    (outputs / "storage_duration_out.csv").write_text("i,v,r,t,Value\nbattery_4,init-1,p1,2032,9\n")
    (outputs / "storage_eff.csv").write_text("i,t,Value\nbattery_4,2032,0.8\n")
    (outputs / "storage_duration_alternate.csv").write_text("i,value\nbattery_4,5\n")

    file_mapping = csv_file_mapping()
    alternate_source = copy.deepcopy(
        next(item for item in file_mapping["files"] if item["name"] == "storage_duration")
    )
    alternate_source.update(name="alternate_storage_duration", fpath="outputs/storage_duration_alternate.csv")
    file_mapping["files"].append(alternate_source)
    storage_table = next(
        item for item in file_mapping["tables"] if item["name"] == "generator_storage_inputs"
    )
    duration_join = next(join for join in storage_table["joins"] if join["source"] == "storage_duration")
    duration_join["source"] = "alternate_storage_duration"

    defaults = example_reeds_config.load_config()["defaults"]
    defaults["reserve_products"] = []
    parser_rules = copy.deepcopy(example_reeds_config.load_config()["parser_rules"])
    next(stage for stage in parser_rules["execution"] if stage["name"] == "resources")["rules"] = []
    config = example_reeds_config.model_copy(
        update={
            "asset_overrides": {
                **example_reeds_config.asset_overrides,
                "parser_rules": parser_rules,
                "file_mapping": file_mapping,
                "defaults": defaults,
            }
        }
    )
    store = DataStore.from_plugin_config(config, path=run_path)
    context = PluginContext(config=config, store=store)

    result = ReEDSParser.from_context(context).run()

    assert result.system is not None
    storage = next(result.system.get_components(ReEDSStorage))
    assert storage.storage_duration == 5.0
    assert storage.capacity == 100.0


def test_public_generator_preparation_uses_configured_ramp_and_heat_recipe(
    reeds_run_path: Path,
    example_reeds_config: ReEDSConfig,
    tmp_path: Path,
) -> None:
    """Configured recipes control ramp source routing and thermal fallback policy."""
    run_path = tmp_path / "run"
    shutil.copytree(reeds_run_path, run_path)
    outputs = run_path / "outputs"
    (outputs / "cap_ivrt.csv").write_text(
        "i,v,r,t,Value\n"
        "Gas-CC,init-1,p1,2032,100\n"
        "Gas-CC,init-1,p3,2032,200\n"
        "Gas-CC,init-2,p1,2032,50\n"
        "upv_1,new1,p1,2032,25\n"
    )
    (outputs / "heat_rate.csv").write_text(
        "i,v,r,t,Value\n"
        "Gas-CC,init-1,p1,2032,12\n"
        "Gas-CC,init-1,p3,2032,\n"
        "Gas-CC,init-2,p1,2032,\n"
        "upv_1,new1,p1,2032,\n"
    )
    (run_path / "inputs_case" / "ramprate_alternate.csv").write_text("Gas-CC,0.25\n")

    file_mapping = csv_file_mapping()
    alternate_ramp = copy.deepcopy(next(item for item in file_mapping["files"] if item["name"] == "ramprate"))
    alternate_ramp.update(name="alternate_ramprate", fpath="inputs_case/ramprate_alternate.csv")
    file_mapping["files"].append(alternate_ramp)
    ramp_table = next(
        item for item in file_mapping["tables"] if item["name"] == "non_variable_generator_rows"
    )
    next(join for join in ramp_table["joins"] if join["source"] == "ramprate")["source"] = (
        "alternate_ramprate"
    )
    heat_table = ramp_table
    heat_table["proc_spec"]["fill_null_by_group"][0]["fallback"] = 27.0

    defaults = example_reeds_config.load_config()["defaults"]
    defaults["reserve_products"] = []
    parser_rules = copy.deepcopy(example_reeds_config.load_config()["parser_rules"])
    next(stage for stage in parser_rules["execution"] if stage["name"] == "resources")["rules"] = []
    config = example_reeds_config.model_copy(
        update={
            "asset_overrides": {
                **example_reeds_config.asset_overrides,
                "parser_rules": parser_rules,
                "file_mapping": file_mapping,
                "defaults": defaults,
            }
        }
    )
    store = DataStore.from_plugin_config(config, path=run_path)
    context = PluginContext(config=config, store=store)
    result = ReEDSParser.from_context(context).run()

    generators = list(result.system.get_components(ReEDSThermalGenerator))
    init_one = next(generator for generator in generators if generator.vintage == "init-1")
    init_two = next(generator for generator in generators if generator.vintage == "init-2")
    assert init_one.heat_rate == pytest.approx(12.0)
    assert init_one.ramp_rate == pytest.approx(0.25)
    assert init_two.heat_rate == pytest.approx(27.0)
    assert init_two.ramp_rate == pytest.approx(0.25)


def test_public_biofuel_price_expands_to_mapped_generator(
    reeds_run_path: Path,
    example_reeds_config: ReEDSConfig,
    tmp_path: Path,
) -> None:
    """Regional biofuel prices expand to mapped technologies through configured joins."""
    run_path = tmp_path / "run"
    shutil.copytree(reeds_run_path, run_path)
    outputs = run_path / "outputs"
    (outputs / "cap_ivrt.csv").write_text("i,v,r,t,Value\nGas-CC,init-1,p1,2032,100\n")
    (outputs / "heat_rate.csv").write_text("i,v,r,t,Value\nGas-CC,init-1,p1,2032,10\n")
    (outputs / "fuel_price.csv").write_text("i,r,t,Value\n")
    (outputs / "fuel2tech.csv").write_text("f,i,Value\nbiomass,Gas-CC,True\n")
    (outputs / "repbioprice.csv").write_text("r,t,value\np1,2032,2.5\n")

    defaults = example_reeds_config.load_config()["defaults"]
    defaults["reserve_products"] = []
    parser_rules = copy.deepcopy(example_reeds_config.load_config()["parser_rules"])
    next(stage for stage in parser_rules["execution"] if stage["name"] == "resources")["rules"] = []
    config = example_reeds_config.model_copy(
        update={
            "asset_overrides": {
                **example_reeds_config.asset_overrides,
                "parser_rules": parser_rules,
                "file_mapping": csv_file_mapping(),
                "defaults": defaults,
            }
        }
    )
    store = DataStore.from_plugin_config(config, path=run_path)
    context = PluginContext(config=config, store=store)
    result = ReEDSParser.from_context(context).run()

    generator = next(result.system.get_components(ReEDSThermalGenerator))
    assert generator.capacity == 100.0
    assert generator.fuel_type == "biomass"
    assert generator.fuel_price == pytest.approx(2.5)


def test_public_lifecycle_fills_default_when_heat_rate_source_is_missing(
    reeds_run_path: Path,
    example_reeds_config: ReEDSConfig,
    tmp_path: Path,
) -> None:
    """An absent optional heat-rate file still reaches the configured fallback."""
    run_path = tmp_path / "run"
    shutil.copytree(reeds_run_path, run_path)
    outputs = run_path / "outputs"
    (outputs / "cap_ivrt.csv").write_text("i,v,r,t,Value\nGas-CC,init-1,p1,2032,100\n")
    (outputs / "heat_rate.csv").unlink()

    defaults = example_reeds_config.load_config()["defaults"]
    defaults["reserve_products"] = []
    parser_rules = copy.deepcopy(example_reeds_config.load_config()["parser_rules"])
    next(stage for stage in parser_rules["execution"] if stage["name"] == "resources")["rules"] = []
    config = example_reeds_config.model_copy(
        update={
            "asset_overrides": {
                **example_reeds_config.asset_overrides,
                "parser_rules": parser_rules,
                "file_mapping": csv_file_mapping(),
                "defaults": defaults,
            }
        }
    )
    store = DataStore.from_plugin_config(config, path=run_path)
    context = PluginContext(config=config, store=store)
    result = ReEDSParser.from_context(context).run()

    generator = next(result.system.get_components(ReEDSThermalGenerator))
    assert generator.capacity == 100.0
    assert generator.heat_rate == 10.0


def test_public_fuel_mapping_precedence_is_configurable(
    reeds_run_path: Path,
    example_reeds_config: ReEDSConfig,
    tmp_path: Path,
) -> None:
    """A configured mapping tie-breaker controls base-technology fuel selection."""
    run_path = tmp_path / "run"
    shutil.copytree(reeds_run_path, run_path)
    outputs = run_path / "outputs"
    (outputs / "cap_ivrt.csv").write_text("i,v,r,t,Value\nGas-CC_case,init-1,p1,2032,100\n")
    (outputs / "heat_rate.csv").write_text("i,v,r,t,Value\nGas-CC_case,init-1,p1,2032,10\n")
    (outputs / "fuel_price.csv").write_text("i,r,t,Value\nGas-CC_case,p1,2032,7\n")
    (outputs / "fuel2tech.csv").write_text("f,i,Value\nnaturalgas,Gas-CC,True\nh2ct,Gas-CC_H2-CT,True\n")

    file_mapping = csv_file_mapping()
    fuel_table = next(item for item in file_mapping["tables"] if item["name"] == "generator_fuel_inputs")
    mapping_join = next(join for join in fuel_table["joins"] if join["source"] == "fuel_tech_map")
    mapping_join["select_first"]["order_by"] = {"technology_full": "desc"}
    defaults = example_reeds_config.load_config()["defaults"]
    defaults["reserve_products"] = []
    parser_rules = copy.deepcopy(example_reeds_config.load_config()["parser_rules"])
    next(stage for stage in parser_rules["execution"] if stage["name"] == "resources")["rules"] = []
    config = example_reeds_config.model_copy(
        update={
            "asset_overrides": {
                **example_reeds_config.asset_overrides,
                "parser_rules": parser_rules,
                "file_mapping": file_mapping,
                "defaults": defaults,
            }
        }
    )
    store = DataStore.from_plugin_config(config, path=run_path)
    context = PluginContext(config=config, store=store)
    result = ReEDSParser.from_context(context).run()

    generator = next(result.system.get_components(ReEDSThermalGenerator))
    assert generator.capacity == 100.0
    assert generator.fuel_type == "h2ct"
    assert generator.fuel_price == 7.0


def test_public_generator_mappings_read_canonical_age_and_vom_fields(
    example_reeds_config: ReEDSConfig,
    example_data_store: DataStore,
) -> None:
    """All packaged mappings consume canonical maxage_years and vom_cost fields."""
    system = System(name="generator max age mappings")
    system.add_component(ReEDSRegion(name="p1"))
    context = PluginContext(config=example_reeds_config, store=example_data_store)
    context.system = system
    context.target_system = system
    parser_rules = json.loads(
        files("r2x_reeds").joinpath("config/parser_rules.json").read_text(encoding="utf-8")
    )
    plan_result = RulePlan.from_mapping(parser_rules, context=context)
    assert plan_result.is_ok(), plan_result.err()

    mappings = [
        (ReEDSGenerator, "base", "imports"),
        (ReEDSThermalGenerator, "thermal", "thermal"),
        (ReEDSVariableGenerator, "variable", "solar"),
        (ReEDSStorage, "storage", "pumped_storage"),
        (ReEDSHydroGenerator, "hydro", "hydro"),
    ]
    records = [
        {
            "technology": technology,
            "region": "p1",
            "vintage": "2030",
            "capacity": 1.0,
            "category": route_key,
            "categories": route_key,
            "maxage_years": 99,
            "vom_cost": 23.75,
            "heat_rate": 10.0,
            "fuel_type": "gas",
            "storage_duration": 4.0,
            "round_trip_efficiency": 0.8,
            "is_dispatchable": technology == "hydro",
            "ext": {},
        }
        for _, technology, route_key in mappings
    ]
    result = apply_mapping_records(
        records,
        plan=plan_result.unwrap(),
        route=SelectedMappingRoute(name="generators"),
        context=context,
    )

    assert result.is_ok(), result.err()
    assert result.unwrap().converted == len(mappings)
    for component_type, technology, _ in mappings:
        generator = system.get_component(component_type, f"{technology}_2030_p1")
        assert generator.max_age == 99
        assert generator.vom_cost == pytest.approx(23.75)


def test_generator_inputs_select_overridden_degraded_capacity_and_fail_when_missing(
    reeds_run_path: Path,
    example_reeds_config: ReEDSConfig,
    example_data_store: DataStore,
    tmp_path: Path,
) -> None:
    """Use the configured degraded source and do not fall back when it is missing."""
    run_path = tmp_path / "run"
    shutil.copytree(reeds_run_path, run_path)
    placeholders = {
        "solve_year": example_reeds_config.solve_year,
        "weather_year": example_reeds_config.weather_year,
    }
    normal_capacity = example_data_store.read_data("online_capacity", placeholders=placeholders).collect()
    normal_row = normal_capacity.row(0, named=True)
    degraded_path = run_path / "outputs" / "cap_deg_alternate.csv"
    degraded_row = {
        "i": normal_row["technology"],
        "r": normal_row["region"],
        "t": normal_row["year"],
        "v": normal_row["vintage"],
        "value": normal_row["capacity"] * 2,
    }
    pl.DataFrame([degraded_row]).write_csv(degraded_path)
    pl.DataFrame([{**degraded_row, "value": normal_row["capacity"] * 3}]).write_csv(
        run_path / "outputs" / "cap_deg_ivrt.csv"
    )

    file_mapping = csv_file_mapping()
    alternate_source = copy.deepcopy(
        next(item for item in file_mapping["files"] if item["name"] == "online_capacity_degraded")
    )
    alternate_source.update(name="alternate_degraded_capacity", fpath="outputs/cap_deg_alternate.csv")
    alternate_source["info"]["is_optional"] = False
    file_mapping["files"].append(alternate_source)
    generator_table = next(item for item in file_mapping["tables"] if item["name"] == "generator_inputs")
    generator_table["source"] = "alternate_degraded_capacity"

    config = example_reeds_config.model_copy(update={"asset_overrides": {"file_mapping": file_mapping}})
    store = DataStore.from_plugin_config(config, path=run_path)

    selected_capacity = store.read_table("generator_inputs", placeholders=placeholders).collect()
    normal_source = store.read_data("online_capacity", placeholders=placeholders).collect()

    assert selected_capacity.height == 1
    assert selected_capacity["capacity"].item() == pytest.approx(normal_row["capacity"] * 2)
    normal_selected = normal_source.filter(
        (pl.col("technology") == normal_row["technology"])
        & (pl.col("region") == normal_row["region"])
        & (pl.col("year") == normal_row["year"])
        & (pl.col("vintage") == normal_row["vintage"])
    )
    assert normal_selected.height == 1
    assert normal_selected["capacity"].item() == pytest.approx(normal_row["capacity"])
    degraded_path.unlink()
    with pytest.raises(ValueError, match=r"alternate_degraded_capacity.*cap_deg_alternate.csv"):
        store.read_table("generator_inputs", placeholders=placeholders)


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
    load_profile_values = next(
        table for table in file_mapping["tables"] if table["name"] == "load_profile_values"
    )
    load_profile_values["source"] = "alternate_load_profiles"

    region_rule = next(rule for rule in parser_rules["rules"] if rule["name"] == "region")
    region_rule["source"]["dataset"] = "alternate_hierarchy_table"
    parser_rules["required_datasets"] = [
        "alternate_hierarchy_table",
        "load_peaks",
        "load_profile_rows",
        "renewable_profile_rows",
    ]

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
    original_profiles = store.read_data(
        "load_profiles", placeholders={"solve_year": 2032, "weather_year": 2012}
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
    assert selected_profiles["p1"].max() == pytest.approx(2 * original_profiles["p1"].max())
    assert p1_load.max_active_power == pytest.approx(float(selected_profiles["p1"].max()))
    np.testing.assert_allclose(system.get_time_series(p1_load).data, expected_profile)


def test_load_rule_rejects_a_physical_profile_source(
    reeds_config: ReEDSConfig, data_store: DataStore
) -> None:
    """Load construction and profile attachment must share a prepared-table source."""
    config_dir = Path(__file__).parents[1] / "src" / "r2x_reeds" / "config"
    parser_rules = json.loads((config_dir / "parser_rules.json").read_text())
    load_rule = next(rule for rule in parser_rules["rules"] if rule["name"] == "load")
    load_rule["source"]["dataset"] = "load_profiles"
    config = reeds_config.model_copy(
        update={
            "asset_overrides": {
                "file_mapping": csv_file_mapping(),
                "parser_rules": parser_rules,
            }
        }
    )
    store = DataStore.from_plugin_config(config, path=data_store.folder)
    context = PluginContext(config=config, store=store)

    result = ReEDSParser.from_context(context).on_validate_config()

    assert result.is_err()
    assert "Load Rule dataset 'load_profiles' must reference a prepared table" in str(result.err())


def test_load_rule_rejects_nullable_peak_output(reeds_config: ReEDSConfig, data_store: DataStore) -> None:
    """Load Rule tables must reject all-null regional peak values."""
    config_dir = Path(__file__).parents[1] / "src" / "r2x_reeds" / "config"
    parser_rules = json.loads((config_dir / "parser_rules.json").read_text())
    file_mapping = csv_file_mapping()
    load_peaks = next(table for table in file_mapping["tables"] if table["name"] == "load_peaks")
    load_peaks.pop("non_null_columns")
    config = reeds_config.model_copy(
        update={
            "asset_overrides": {
                "file_mapping": file_mapping,
                "parser_rules": parser_rules,
            }
        }
    )
    store = DataStore.from_plugin_config(config, path=data_store.folder)
    context = PluginContext(config=config, store=store)

    result = ReEDSParser.from_context(context).on_validate_config()

    assert result.is_err()
    assert "must declare non-null columns" in str(result.err())


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
