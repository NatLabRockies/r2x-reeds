"""Public parser regressions for configuration-owned input and field overrides."""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import polars as pl
import pytest

from r2x_core import DataStore, PluginContext, PluginError, System
from r2x_reeds import ReEDSConfig, ReEDSParser
from r2x_reeds.models import (
    ReEDSDemand,
    ReEDSEmission,
    ReEDSGenerator,
    ReEDSRegion,
    ReEDSStorage,
    ReEDSThermalGenerator,
    ReEDSVariableGenerator,
)
from r2x_reeds.plugin_config import GeneratorClassificationOverride
from tests.test_parser_current_core import configure_csv_sources, copy_package_config

pytestmark = [pytest.mark.integration, pytest.mark.polars]


def load_records(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_records(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text(json.dumps(records), encoding="utf-8")


def update_csv_source(records: list[dict[str, Any]], name: str, relative_path: str) -> None:
    source = next(record for record in records if record["name"] == name)
    source["relative_fpath"] = relative_path
    reader: dict[str, Any] = source.get("reader", {})
    source["reader"] = {"format": "csv", **({"options": reader["options"]} if "options" in reader else {})}


def prepare_case(reeds_run_path: Path, tmp_path: Path) -> tuple[Path, Path]:
    run_path = tmp_path / "run"
    shutil.copytree(reeds_run_path, run_path)
    config_path = copy_package_config(tmp_path)
    configure_csv_sources(config_path, include_all=True)
    return run_path, config_path


def run_parser(
    run_path: Path,
    config_path: Path,
    *,
    excluded_techs: list[str] | None = None,
    classification_overrides: list[GeneratorClassificationOverride] | None = None,
) -> System:
    config = ReEDSConfig(
        solve_year=2032,
        weather_year=2012,
        excluded_techs=excluded_techs,
        generator_classification_overrides=classification_overrides or [],
        config_path_override=config_path,
    )
    context = PluginContext(config=config, store=DataStore(path=run_path))
    result = ReEDSParser.from_context(context).run()
    if result.system is None:
        msg = "ReEDS parser returned no System"
        raise AssertionError(msg)
    return result.system


def test_parser_uses_configured_generator_sources_and_field_mapping(
    reeds_run_path: Path, tmp_path: Path
) -> None:
    run_path, config_path = prepare_case(reeds_run_path, tmp_path)
    outputs = run_path / "outputs"
    inputs = run_path / "inputs_case"
    (outputs / "cap_ivrt.csv").write_text(
        "i,v,r,t,Value,fuel_type\nGas-CC,init-1,p1,2032,100,gas\n", encoding="utf-8"
    )
    (outputs / "heat-rate-selected.csv").write_text(
        "i,v,r,t,Value\nGas-CC,init-1,p1,2032,123456\n", encoding="utf-8"
    )
    (outputs / "forced-outages-selected.csv").write_text("i,Value\nGas-CC,0.31\n", encoding="utf-8")
    (outputs / "planned-outages-selected.csv").write_text("i,Value\nGas-CC,0.42\n", encoding="utf-8")
    (outputs / "vom-selected.csv").write_text("i,v,r,t,Value\nGas-CC,init-1,p1,2032,23.5\n", encoding="utf-8")
    (outputs / "startup-selected.csv").write_text("*i,$2004/MW\nGas-CC,17.5\n", encoding="utf-8")
    (inputs / "maxage-selected.csv").write_text("Gas-CC,99\n", encoding="utf-8")
    (inputs / "ramprate-selected.csv").write_text("Gas-CC,0.25\n", encoding="utf-8")

    mapping_path = config_path / "file_mapping.json"
    mapping = load_records(mapping_path)
    for name, path in [
        ("heat_rate", "outputs/heat-rate-selected.csv"),
        ("forced_outages", "outputs/forced-outages-selected.csv"),
        ("planned_outages", "outputs/planned-outages-selected.csv"),
        ("cost_vom", "outputs/vom-selected.csv"),
        ("startcost", "outputs/startup-selected.csv"),
        ("ramprate", "inputs_case/ramprate-selected.csv"),
    ]:
        update_csv_source(mapping, name, path)
    maxage = next(record for record in mapping if record["name"] == "maxage")
    maxage["relative_fpath"] = "inputs_case/maxage-selected.csv"
    generator_thermal_rows = next(record for record in mapping if record["name"] == "generator_thermal_rows")
    generator_thermal_rows["proc_spec"]["steps"].append(
        {
            "op": "with_columns",
            "columns": {
                "maxage_years": "max_age",
                "mapped_vom": "vom_cost",
            },
        }
    )
    write_records(mapping_path, mapping)

    rules_path = config_path / "parser_rules.json"
    rules = load_records(rules_path)
    thermal = next(rule for rule in rules if rule.get("component_type") == "ReEDSThermalGenerator")
    thermal["fields"]["max_age"] = "maxage_years"
    thermal["fields"]["vom_cost"] = "mapped_vom"
    write_records(rules_path, rules)

    system = run_parser(run_path, config_path, excluded_techs=[])

    generator = system.get_component(ReEDSThermalGenerator, "gas-cc_init-1_p1_2032")
    assert generator.capacity == 100.0
    assert generator.heat_rate == 123456.0
    assert generator.forced_outage_rate == 0.31
    assert generator.planned_outage_rate == 0.42
    assert generator.vom_cost == 23.5
    assert generator.max_age == 99
    assert generator.ramp_rate == 0.25
    assert generator.startup_cost == 17.5


def test_category_and_exclusion_overrides_control_generator_outputs(
    reeds_run_path: Path, tmp_path: Path
) -> None:
    run_path, config_path = prepare_case(reeds_run_path, tmp_path)
    (run_path / "outputs" / "cap_ivrt.csv").write_text(
        "i,v,r,t,Value\nGas-CC,init-1,p1,2032,100\nGas-CT,init-1,p1,2032,50\n",
        encoding="utf-8",
    )
    defaults_path = config_path / "defaults.json"
    defaults = json.loads(defaults_path.read_text(encoding="utf-8"))
    defaults["reserve_products"] = []
    defaults_path.write_text(json.dumps(defaults), encoding="utf-8")
    system = run_parser(
        run_path,
        config_path,
        excluded_techs=["gas-ct"],
        classification_overrides=[GeneratorClassificationOverride(technology="gas-cc", category="wind")],
    )

    generators = list(system.get_components(ReEDSGenerator))
    assert len(generators) == 1
    assert type(generators[0]) is ReEDSVariableGenerator
    assert (generators[0].name, generators[0].category, generators[0].capacity) == (
        "gas-cc_p1_2032",
        "wind",
        100.0,
    )


def write_renewable_profile(path: Path, /, *, columns: list[str], values: np.ndarray) -> None:
    """Write the named-index HDF5 layout used by ReEDS capacity-factor profiles."""
    timestamps = (
        (np.datetime64("2012-01-01") + np.arange(values.shape[0]) * np.timedelta64(1, "h"))
        .astype("datetime64[s]")
        .astype("S19")
    )
    with h5py.File(path, "w") as handle:
        handle.create_dataset("columns", data=np.asarray(columns, dtype="S32"))
        handle.create_dataset("data", data=values)
        handle.create_dataset("index_0", data=timestamps)
        handle.create_dataset("index_names", data=np.asarray(["datetime"], dtype="S8"))


def test_renewable_profile_attaches_to_a_matched_thermal_category_override(
    reeds_run_path: Path, tmp_path: Path
) -> None:
    run_path, config_path = prepare_case(reeds_run_path, tmp_path)
    outputs = run_path / "outputs"
    (outputs / "cap_ivrt.csv").write_text(
        "i,v,r,t,Value,fuel_type\nGas-CC,init-1,p1,2032,100,gas\n", encoding="utf-8"
    )
    (outputs / "heat-rate-renewable.csv").write_text(
        "i,v,r,t,Value\nGas-CC,init-1,p1,2032,10\n", encoding="utf-8"
    )
    write_renewable_profile(
        run_path / "inputs_case" / "recf.h5",
        columns=["gas-cc|p1"],
        values=np.full((8760, 1), 0.5),
    )

    defaults_path = config_path / "defaults.json"
    defaults = json.loads(defaults_path.read_text(encoding="utf-8"))
    defaults["reserve_products"] = []
    defaults_path.write_text(json.dumps(defaults), encoding="utf-8")
    mapping_path = config_path / "file_mapping.json"
    mapping = load_records(mapping_path)
    update_csv_source(mapping, "heat_rate", "outputs/heat-rate-renewable.csv")
    write_records(mapping_path, mapping)

    system = run_parser(
        run_path,
        config_path,
        excluded_techs=[],
        classification_overrides=[
            GeneratorClassificationOverride(
                technology="gas-cc",
                category="thermal",
                is_dispatchable=True,
            )
        ],
    )

    generator = system.get_component(ReEDSThermalGenerator, "gas-cc_init-1_p1_2032")
    series = system.get_time_series(generator, name="max_active_power")
    assert generator.category == "gas-cc"
    assert series.length == 8760
    assert series.initial_timestamp.year == 2012
    np.testing.assert_array_equal(series.data, np.full(8760, 50.0))


def test_storage_source_override_keeps_duration_and_energy_cost_mapping(
    reeds_run_path: Path, tmp_path: Path
) -> None:
    run_path, config_path = prepare_case(reeds_run_path, tmp_path)
    outputs = run_path / "outputs"
    (outputs / "cap_ivrt.csv").write_text("i,v,r,t,Value\nbattery_4,init-1,p1,2032,100\n", encoding="utf-8")
    (outputs / "storage-duration-selected.csv").write_text("i,value\nbattery_4,5\n", encoding="utf-8")
    (outputs / "cost_cap.csv").write_text("i,t,Value\nbattery_4,2032,200\n", encoding="utf-8")
    (outputs / "cost_cap_energy.csv").write_text("i,t,Value\nbattery_4,2032,30\n", encoding="utf-8")

    mapping_path = config_path / "file_mapping.json"
    mapping = load_records(mapping_path)
    duration = copy.deepcopy(next(record for record in mapping if record["name"] == "storage_duration"))
    duration.update(
        name="storage_duration_selected",
        relative_fpath="outputs/storage-duration-selected.csv",
        reader={"format": "csv"},
    )
    duration_index = next(
        index for index, record in enumerate(mapping) if record["name"] == "generator_storage_duration"
    )
    mapping.insert(duration_index, duration)
    selector = next(record for record in mapping if record["name"] == "generator_storage_duration")
    selector["source_selection"]["sources"] = ["storage_duration_selected"]
    write_records(mapping_path, mapping)

    system = run_parser(run_path, config_path, excluded_techs=[])

    storage = system.get_component(ReEDSStorage, "battery_4_init-1_p1_2032")
    assert storage.capacity == 100.0
    assert storage.storage_duration == 5.0
    assert storage.capital_cost == 200.0
    assert storage.capital_cost_energy == 30.0


def test_parser_uses_configured_biofuel_price_mapping(reeds_run_path: Path, tmp_path: Path) -> None:
    run_path, config_path = prepare_case(reeds_run_path, tmp_path)
    outputs = run_path / "outputs"
    (outputs / "cap_ivrt.csv").write_text("i,v,r,t,Value\nGas-CC,init-1,p1,2032,100\n", encoding="utf-8")
    (outputs / "heat_rate.csv").write_text("i,v,r,t,Value\nGas-CC,init-1,p1,2032,10\n", encoding="utf-8")
    (outputs / "fuel2tech.csv").write_text("f,i,Value\nbiomass,Gas-CC,True\n", encoding="utf-8")
    (outputs / "fuel_price.csv").write_text("i,r,t,Value\n", encoding="utf-8")
    (outputs / "repbioprice.csv").write_text("r,t,value\np1,2032,2.5\n", encoding="utf-8")

    system = run_parser(run_path, config_path, excluded_techs=[])

    generator = system.get_component(ReEDSThermalGenerator, "gas-cc_init-1_p1_2032")
    assert generator.fuel_type == "biomass"
    assert generator.fuel_price == 2.5


def test_parser_routes_alternate_hierarchy_and_load_profile_sources(
    reeds_run_path: Path, tmp_path: Path
) -> None:
    run_path, config_path = prepare_case(reeds_run_path, tmp_path)
    inputs = run_path / "inputs_case"
    hierarchy = pl.read_csv(inputs / "hierarchy.csv").to_dicts()
    selected_region = dict(hierarchy[0])
    selected_region["*r"] = "source-selected"
    pl.DataFrame([*hierarchy, selected_region]).write_csv(inputs / "hierarchy-selected.csv")

    regions = [f"p{index}" for index in range(1, 12)]
    load_rows = [
        ["2032", "2012-01-01T00:00:00", *("20" if region == "p1" else "1" for region in regions)],
        ["2032", "2012-01-01T01:00:00", *("22" if region == "p1" else "2" for region in regions)],
    ]
    load_path = inputs / "load-selected.csv"
    load_path.write_text(
        ",".join(["year", "datetime", *regions])
        + "\n"
        + "\n".join(",".join(row) for row in load_rows)
        + "\n",
        encoding="utf-8",
    )

    mapping_path = config_path / "file_mapping.json"
    mapping = load_records(mapping_path)
    hierarchy_source = next(record for record in mapping if record["name"] == "hierarchy")
    hierarchy_source["relative_fpath"] = "inputs_case/hierarchy-selected.csv"
    load_source = next(record for record in mapping if record["name"] == "load_profiles")
    load_source["relative_fpath"] = "inputs_case/load-selected.csv"
    load_source["reader"] = {"format": "csv", "options": {"try_parse_dates": True}}
    write_records(mapping_path, mapping)

    system = run_parser(run_path, config_path, excluded_techs=[])

    assert system.get_component(ReEDSRegion, "source-selected") is not None
    demand = system.get_component(ReEDSDemand, "p1_load_2032")
    assert demand.max_active_power == 22.0
    series = system.get_time_series(demand, name="max_active_power")
    assert list(series.data) == [20.0, 22.0]


def test_emission_rows_normalize_types_and_default_missing_sources(
    reeds_run_path: Path, tmp_path: Path
) -> None:
    run_path, config_path = prepare_case(reeds_run_path, tmp_path)
    emission_path = run_path / "outputs" / "emission-rates.csv"
    emission_path.write_text("i,etype,eall,r,t,v,value\ngas-cc,,co2,p1,2032,init-1,0.25\n", encoding="utf-8")
    mapping_path = config_path / "file_mapping.json"
    mapping = load_records(mapping_path)
    emission_source = next(record for record in mapping if record["name"] == "emission_rates")
    emission_source["relative_fpath"] = "outputs/emission-rates.csv"
    emission_source["reader"] = {"format": "csv"}
    write_records(mapping_path, mapping)

    system = run_parser(run_path, config_path, excluded_techs=[])

    generator = system.get_component(ReEDSThermalGenerator, "gas-cc_init-1_p1_2032")
    emissions = system.get_supplemental_attributes_with_component(generator, ReEDSEmission)
    assert [(item.type.value, item.source.value, item.rate) for item in emissions] == [
        ("CO2", "COMBUSTION", 0.25)
    ]


def test_unknown_emission_type_still_fails_validation(reeds_run_path: Path, tmp_path: Path) -> None:
    run_path, config_path = prepare_case(reeds_run_path, tmp_path)
    emission_path = run_path / "outputs" / "emission-rates.csv"
    emission_path.write_text(
        "i,etype,eall,r,t,v,value\ngas-cc,combustion,unknown,p1,2032,init-1,0.25\n",
        encoding="utf-8",
    )
    mapping_path = config_path / "file_mapping.json"
    mapping = load_records(mapping_path)
    emission_source = next(record for record in mapping if record["name"] == "emission_rates")
    emission_source["relative_fpath"] = "outputs/emission-rates.csv"
    emission_source["reader"] = {"format": "csv"}
    write_records(mapping_path, mapping)

    with pytest.raises(PluginError) as captured:
        run_parser(run_path, config_path, excluded_techs=[])

    assert "unknown" in str(captured.value.__cause__).lower()


def test_missing_optional_emission_source_builds_without_emission_attributes(
    reeds_run_path: Path, tmp_path: Path
) -> None:
    run_path, config_path = prepare_case(reeds_run_path, tmp_path)
    mapping_path = config_path / "file_mapping.json"
    mapping = load_records(mapping_path)
    emission_source = next(record for record in mapping if record["name"] == "emission_rates")
    emission_source["relative_fpath"] = "outputs/missing-emission-rates.csv"
    emission_source["reader"] = {"format": "csv"}
    write_records(mapping_path, mapping)

    system = run_parser(run_path, config_path, excluded_techs=[])

    assert not list(system.get_supplemental_attributes(ReEDSEmission))


def test_malformed_present_optional_emission_source_is_not_skipped(
    reeds_run_path: Path, tmp_path: Path
) -> None:
    run_path, config_path = prepare_case(reeds_run_path, tmp_path)
    malformed_path = run_path / "outputs" / "malformed-emission-rates.csv"
    malformed_path.write_text("wrong,columns\\ninvalid,row\\n", encoding="utf-8")
    mapping_path = config_path / "file_mapping.json"
    mapping = load_records(mapping_path)
    emission_source = next(record for record in mapping if record["name"] == "emission_rates")
    emission_source["relative_fpath"] = "outputs/malformed-emission-rates.csv"
    emission_source["reader"] = {"format": "csv"}
    write_records(mapping_path, mapping)

    with pytest.raises(PluginError) as raised:
        run_parser(run_path, config_path, excluded_techs=[])

    assert raised.value.__cause__ is not None
