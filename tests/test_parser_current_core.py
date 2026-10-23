from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import pytest
from pydantic import TypeAdapter

from r2x_core import (
    DataFile,
    DataReader,
    DataStore,
    DocumentSource,
    PluginContext,
    PluginError,
    System,
    build_system_from_sources,
)
from r2x_core.exceptions import ReaderError
from r2x_core.models import ParserInstruction
from r2x_reeds import ReEDSConfig, ReEDSParser
from r2x_reeds.models import ReEDSGenerator, ReEDSRegion
from r2x_reeds.models.components import (
    ReEDSDemand,
    ReEDSHydroGenerator,
    ReEDSInterface,
    ReEDSStorage,
    ReEDSThermalGenerator,
    ReEDSTransmissionLine,
    ReEDSVariableGenerator,
)

pytestmark = pytest.mark.polars


def write_current_meta(run_path: Path) -> None:
    (run_path / "meta.csv").write_text(
        "computer,repo,branch,commit,description,tag\nlocal,repo,main,abc,fixture,2026.10.04\n",
        encoding="utf-8",
    )


def copy_package_config(destination: Path) -> Path:
    config_path = destination / "alternate-config"
    shutil.copytree(ReEDSConfig.package_config_path(), config_path)
    return config_path


def run_parser_with_load_csv(
    tmp_path: Path,
    reeds_run_path: Path,
    *,
    csv_text: str,
) -> None:
    """Run the public parser with real package sources and a controlled load table."""
    run_path = tmp_path / "run"
    shutil.copytree(reeds_run_path, run_path)
    load_path = run_path / "inputs_case" / "load-profiles.csv"
    load_path.write_text(csv_text, encoding="utf-8")
    config_path = copy_package_config(tmp_path)
    configure_csv_sources(config_path)
    mapping_path = config_path / "file_mapping.json"
    files: list[dict[str, Any]] = json.loads(mapping_path.read_text(encoding="utf-8"))
    load_file = next(item for item in files if item["name"] == "load_profiles")
    load_file["relative_fpath"] = "inputs_case/load-profiles.csv"
    load_file["reader"] = {"format": "csv", "options": {"try_parse_dates": True}}
    mapping_path.write_text(json.dumps(files), encoding="utf-8")
    config = ReEDSConfig(
        solve_year=2032,
        weather_year=2012,
        case_name="load-policy-test",
        excluded_techs=[],
        config_path_override=config_path,
    )
    ReEDSParser.from_context(PluginContext(config=config, store=DataStore(path=run_path))).run()


def configure_csv_sources(
    config_path: Path,
    csv_paths: dict[str, str] | None = None,
    *,
    extra_names: set[str] | None = None,
    include_all: bool = False,
) -> None:
    """Point selected HDF5 output declarations at the fixture's equivalent CSVs."""
    mapping_path = config_path / "file_mapping.json"
    files: list[dict[str, Any]] = json.loads(mapping_path.read_text(encoding="utf-8"))
    configured_paths: dict[str, str] = csv_paths or {}
    if csv_paths is not None and not include_all:
        names = {"hierarchy", *configured_paths, *(extra_names or set())}
        if "hierarchy" in names:
            names.add("hierarchy_required")
        if "load_profiles" in names:
            names.update(
                {
                    "load_profiles_required",
                    "load_profile_values",
                    "load_profile_values_required",
                    "load_peaks",
                    "load_profile_rows",
                }
            )
        files = [item for item in files if item["name"] in names]
    for item in files:
        if item["name"] in configured_paths:
            item["relative_fpath"] = configured_paths[item["name"]]
            item["reader"] = {"format": "csv"}
        elif (csv_paths is None or include_all) and item.get("relative_fpath") == "outputs/outputs.h5":
            group = item["reader"]["options"]["group_key"]
            item["relative_fpath"] = f"outputs/{group}.csv"
            item["reader"] = {"format": "csv"}
    mapping_path.write_text(json.dumps(files), encoding="utf-8")


def build_generator_system(
    run_path: Path,
    *,
    config: ReEDSConfig,
    default_heat_rate: float | None = None,
    fuel_base_sort: Literal["asc", "desc"] | None = None,
    generator_category_patterns: list[dict[str, object]] | None = None,
    capacity_source: str | None = None,
    required_capacity_source: bool = False,
) -> System:
    """Run the public parser with full package inputs and optional policy overrides."""
    config_path = copy_package_config(run_path)
    defaults_path = config_path / "defaults.json"
    defaults = json.loads(defaults_path.read_text(encoding="utf-8"))
    defaults["reserve_products"] = []
    if default_heat_rate is not None:
        defaults["default_values"]["default_heat_rate"] = default_heat_rate
    defaults_path.write_text(json.dumps(defaults), encoding="utf-8")
    configure_csv_sources(config_path, include_all=True)
    if fuel_base_sort is not None or capacity_source is not None or generator_category_patterns is not None:
        mapping_path = config_path / "file_mapping.json"
        files: list[dict[str, Any]] = json.loads(mapping_path.read_text(encoding="utf-8"))
        if generator_category_patterns is not None:
            category_source = next(item for item in files if item["name"] == "generator_category_patterns")
            category_source["inline_table"]["rows"] = generator_category_patterns
        if fuel_base_sort is not None:
            lookup = next(item for item in files if item["name"] == "generator_fuel_base_lookup")
            lookup["proc_spec"]["steps"][0]["by"]["technology_full"] = fuel_base_sort
        if capacity_source is not None:
            selected_capacity = next(item for item in files if item["name"] == "generator_capacity_selected")
            selected_capacity["source_selection"]["sources"] = [capacity_source]
            if required_capacity_source:
                source = next(item for item in files if item["name"] == capacity_source)
                source["info"]["requirement"] = "required"
        mapping_path.write_text(json.dumps(files), encoding="utf-8")
    config = config.model_copy(update={"config_path_override": config_path})
    context = PluginContext(config=config, store=DataStore(path=run_path))
    result = ReEDSParser.from_context(context).run()
    assert result.system is not None
    return result.system


def test_public_builder_maps_current_hierarchy_fields() -> None:
    instruction = TypeAdapter(ParserInstruction).validate_python(
        json.loads((ReEDSConfig.package_config_path() / "parser_rules.json").read_bytes())[0]
    )
    source = DocumentSource(
        [
            {
                "region_id": "p1",
                "state": "CA",
                "transmission_region": "CAISO",
                "transmission_group": "CAISO",
            },
            {"region_id": "p2", "nerc_region": "WECC_NW", "hurdle_region": "Bonneville"},
        ],
        None,
    )

    system = build_system_from_sources(
        {"hierarchy": source},
        config=ReEDSConfig(solve_year=2032, weather_year=2012),
        instructions=[instruction],
        name="hierarchy-test",
    )

    regions = {region.name: region for region in system.get_components(ReEDSRegion)}
    assert regions.keys() == {"p1", "p2"}
    assert regions["p1"].state == "CA"
    assert regions["p1"].transmission_region == "CAISO"
    assert regions["p1"].transmission_group == "CAISO"
    assert regions["p2"].nerc_region == "WECC_NW"
    assert regions["p2"].hurdle_region == "Bonneville"


def test_complete_run_uses_current_mapping_and_builds_regions(reeds_run_path: Path, tmp_path: Path) -> None:
    config_path = copy_package_config(tmp_path)
    configure_csv_sources(config_path)
    config = ReEDSConfig(
        solve_year=2032,
        weather_year=2012,
        case_name="complete-run",
        config_path_override=config_path,
    )
    context = PluginContext(config=config, store=DataStore(path=reeds_run_path))

    result = ReEDSParser.from_context(context).run()

    assert result.system is not None
    regions = {region.name: region for region in result.system.get_components(ReEDSRegion)}
    assert len(regions) == 11
    assert regions["p1"].transmission_region == "NorthernGrid"
    generators = list(result.system.get_components(ReEDSGenerator))
    assert generators
    assert any(isinstance(unit, ReEDSThermalGenerator) for unit in generators)
    assert any(isinstance(unit, ReEDSStorage) for unit in generators)
    assert any(isinstance(unit, ReEDSHydroGenerator) for unit in generators)
    gas = [unit for unit in generators if unit.technology == "gas-cc"]
    assert gas
    assert all(unit.fom_cost == 20081.0 for unit in gas)


def test_public_parser_aggregates_variable_capacity_and_preserves_unknown_fom(
    reeds_run_path: Path, tmp_path: Path
) -> None:
    """The typed builder aggregates matching solar rows without inventing unknown FOM."""
    run_path = tmp_path / "run"
    shutil.copytree(reeds_run_path, run_path)
    (run_path / "outputs" / "cap_ivrt.csv").write_text(
        "i,v,r,t,Value\nupv_1,new1,p1,2032,10\nupv_1,new2,p1,2032,30\n",
        encoding="utf-8",
    )
    (run_path / "inputs_case" / "plantcharout.csv").write_text(
        "*i,t,variable,value\nGas-CC,2032,fom,20081\n",
        encoding="utf-8",
    )
    config_path = copy_package_config(tmp_path)
    configure_csv_sources(config_path, include_all=True)
    config = ReEDSConfig(
        solve_year=2032,
        weather_year=2012,
        case_name="variable-generator-aggregation",
        config_path_override=config_path,
    )
    context = PluginContext(config=config, store=DataStore(path=run_path))

    result = ReEDSParser.from_context(context).run()

    assert result.system is not None
    generators = list(result.system.get_components(ReEDSVariableGenerator))
    assert [(item.name, item.capacity, item.fom_cost) for item in generators] == [("upv_1_p1", 40.0, None)]


def test_public_parser_builds_generators_from_processed_current_sources(
    reeds_run_path: Path, tmp_path: Path
) -> None:
    run_path = tmp_path / "run"
    shutil.copytree(reeds_run_path, run_path)
    outputs = run_path / "outputs"
    (outputs / "cap_ivrt.csv").write_text(
        "i,v,r,t,Value\nGas-CC,init-1,p1,2032,100\nupv_1,new1,p1,2032,10\n"
        "upv_1,new2,p1,2032,30\nupv_1,new1,p1,2029,99\n",
        encoding="utf-8",
    )
    (outputs / "heat_rate.csv").write_text("i,v,r,t,Value\nGas-CC,init-1,p1,2032,12\n", encoding="utf-8")
    (outputs / "fuel2tech.csv").write_text("f,i,Value\nGAS,Gas-CC,c_bool(True)\n", encoding="utf-8")
    config = ReEDSConfig(solve_year=2032, weather_year=2012, case_name="generator-test")

    system = build_generator_system(run_path, config=config)

    thermal = list(system.get_components(ReEDSThermalGenerator))
    variable = list(system.get_components(ReEDSVariableGenerator))
    assert [
        (item.name, item.technology, item.capacity, item.heat_rate, item.fuel_type) for item in thermal
    ] == [("gas-cc_init-1_p1", "gas-cc", 100.0, 12.0, "gas")]
    assert [(item.name, item.technology, item.capacity) for item in variable] == [("upv_1_p1", "upv_1", 40.0)]


def test_public_parser_builds_storage_and_hydro_from_typed_sources(
    reeds_run_path: Path, tmp_path: Path
) -> None:
    run_path = tmp_path / "run"
    shutil.copytree(reeds_run_path, run_path)
    outputs = run_path / "outputs"
    (outputs / "cap_ivrt.csv").write_text(
        "i,v,r,t,Value\nbattery_4,new1,p1,2032,20\nhydD,new1,p1,2032,40\nhydND,new1,p1,2032,50\n",
        encoding="utf-8",
    )
    (outputs / "storage_duration.csv").write_text("i,Value\nbattery_4,4\n", encoding="utf-8")
    (outputs / "storage_eff.csv").write_text("i,t,Value\nbattery_4,2032,0.8\n", encoding="utf-8")
    config = ReEDSConfig(solve_year=2032, weather_year=2012, case_name="hydro-storage-test")

    system = build_generator_system(run_path, config=config)

    storage = list(system.get_components(ReEDSStorage))
    hydro = {unit.technology: unit for unit in system.get_components(ReEDSHydroGenerator)}
    assert [
        (unit.name, unit.capacity, unit.storage_duration, unit.round_trip_efficiency) for unit in storage
    ] == [("battery_4_new1_p1", 20.0, 4.0, 0.8)]
    assert hydro["hydd"].is_dispatchable is True
    assert hydro["hydnd"].is_dispatchable is False


@pytest.mark.parametrize(
    ("excluded_override", "capacity", "include_imports", "expected_capacity"),
    [
        (None, 5.0, False, None),
        ([], 5.0, True, 5.0),
        ([], 1e-9, True, 0.0),
    ],
    ids=["default-exclusions", "empty-list-overrides-defaults", "tiny-capacity-normalizes-to-zero"],
)
def test_public_parser_preserves_exclusion_and_tiny_capacity_policy(
    reeds_run_path: Path,
    tmp_path: Path,
    excluded_override: list[str] | None,
    capacity: float,
    include_imports: bool,
    expected_capacity: float | None,
) -> None:
    run_path = tmp_path / "run"
    shutil.copytree(reeds_run_path, run_path)
    (run_path / "outputs" / "cap_ivrt.csv").write_text(
        f"i,v,r,t,Value\ncan-imports,new1,p1,2032,{capacity}\nupv_1,new1,p1,2032,1\n",
        encoding="utf-8",
    )
    config = ReEDSConfig(
        solve_year=2032,
        weather_year=2012,
        case_name="generator-policy-test",
        excluded_techs=excluded_override,
    )

    system = build_generator_system(run_path, config=config)

    imports = [unit for unit in system.get_components(ReEDSGenerator) if type(unit) is ReEDSGenerator]
    if include_imports:
        assert [(unit.technology, unit.capacity) for unit in imports] == [("can-imports", expected_capacity)]
    else:
        assert imports == []
    assert [unit.name for unit in system.get_components(ReEDSVariableGenerator)] == ["upv_1_p1"]


def test_public_parser_reports_a_missing_required_hierarchy_file(tmp_path: Path) -> None:
    write_current_meta(tmp_path)
    config_path = copy_package_config(tmp_path)
    mapping_path = config_path / "file_mapping.json"
    configured_files: list[dict[str, Any]] = json.loads(mapping_path.read_text(encoding="utf-8"))
    mapping = [next(item for item in configured_files if item["name"] == "hierarchy")]
    mapping_path.write_text(json.dumps(mapping), encoding="utf-8")
    config = ReEDSConfig(
        solve_year=2032,
        weather_year=2012,
        case_name="missing-hierarchy",
        config_path_override=config_path,
    )
    context = PluginContext(config=config, store=DataStore(path=tmp_path))

    with pytest.raises(PluginError, match=r"hierarchy\.csv") as captured:
        ReEDSParser.from_context(context).run()

    assert isinstance(captured.value.__cause__, FileNotFoundError)


def test_public_parser_loads_defaults_from_instance_config_directory(tmp_path: Path) -> None:
    write_current_meta(tmp_path)
    config_path = copy_package_config(tmp_path)
    (config_path / "defaults.json").write_text("[]", encoding="utf-8")
    config = ReEDSConfig(
        solve_year=2032,
        weather_year=2012,
        config_path_override=config_path,
    )
    context = PluginContext(config=config, store=DataStore(path=tmp_path))

    with pytest.raises(PluginError, match="defaults configuration") as captured:
        ReEDSParser.from_context(context).run()

    assert isinstance(captured.value.__cause__, ValueError)


def test_public_parser_preserves_invalid_mapping_validation_error(tmp_path: Path) -> None:
    write_current_meta(tmp_path)
    config_path = copy_package_config(tmp_path)
    (config_path / "file_mapping.json").write_text('[{"name":"invalid"}]', encoding="utf-8")
    config = ReEDSConfig(
        solve_year=2032,
        weather_year=2012,
        config_path_override=config_path,
    )
    context = PluginContext(config=config, store=DataStore(path=tmp_path))

    with pytest.raises(PluginError, match="requires exactly one physical path") as captured:
        ReEDSParser.from_context(context).run()

    assert isinstance(captured.value.__cause__, ValueError)


def build_transmission_case(
    reeds_run_path: Path,
    tmp_path: Path,
    *,
    capacity_rows: str | None,
    losses: str | None = None,
) -> System | None:
    """Run the public parser with controlled transmission sources and valid required inputs."""
    run_path = tmp_path / "run"
    shutil.copytree(reeds_run_path, run_path)
    inputs_case = run_path / "inputs_case"
    outputs = run_path / "outputs"
    if capacity_rows is not None:
        (outputs / "transmission_capacity.csv").write_text(capacity_rows, encoding="utf-8")
    if losses is not None:
        (outputs / "transmission_losses.csv").write_text(losses, encoding="utf-8")
    (outputs / "cost_hurdle_rate.csv").write_text(
        "r,rr,allt,Value\np1,p2,2032,3\np2,p1,2032,4\n", encoding="utf-8"
    )
    (inputs_case / "transmission_distance.csv").write_text(
        "r,rr,miles\np1,p2,100\np2,p1,110\n", encoding="utf-8"
    )
    (inputs_case / "transmission_cost_ac.csv").write_text(
        "r,rr,USD2004perMW_forward,USD2004perMW_reverse,tscbin,binwidth_USD2004\n"
        "p1,p2,3000,2800,2,10\np1,p2,2000,1800,1,10\n",
        encoding="utf-8",
    )
    config_path = copy_package_config(tmp_path)
    configure_csv_sources(
        config_path,
        {
            "transmission_capacity": "outputs/transmission_capacity.csv",
            "transmission_losses": "outputs/transmission_losses.csv",
            "cost_hurdle_rate": "outputs/cost_hurdle_rate.csv",
            "transmission_distance_cost_dc": "inputs_case/transmission_distance.csv",
            "transmission_distance_cost_ac": "inputs_case/transmission_cost_ac.csv",
        },
        include_all=True,
    )
    config = ReEDSConfig(
        solve_year=2032,
        weather_year=2012,
        case_name="transmission-test",
        excluded_techs=[],
        config_path_override=config_path,
    )
    context = PluginContext(config=config, store=DataStore(path=run_path))
    return ReEDSParser.from_context(context).run().system


def test_public_parser_builds_transmission_with_directional_and_lookup_policy(
    reeds_run_path: Path, tmp_path: Path
) -> None:
    capacity_rows = "r,rr,trtype,t,Value\np1,p2,ac,2032,100\np2,p1,ac,2032,90\np1,p2,dc,2032,70\n"
    losses = "r,rr,trtype,Value\np1,p2,ac,0.05\np2,p1,ac,0.06\np1,p2,dc,0.1\n"

    system = build_transmission_case(reeds_run_path, tmp_path, capacity_rows=capacity_rows, losses=losses)

    assert system is not None
    regions = {region.name: region for region in system.get_components(ReEDSRegion)}
    interfaces = list(system.get_components(ReEDSInterface))
    assert [(item.name, item.from_region, item.to_region) for item in interfaces] == [
        ("p1||p2", regions["p1"], regions["p2"])
    ]
    lines = {line.name: line for line in system.get_components(ReEDSTransmissionLine)}
    assert set(lines) == {"p1_p2_ac", "p1_p2_dc"}
    assert lines["p1_p2_ac"].interface is interfaces[0]
    assert lines["p1_p2_ac"].max_active_power.from_to == 90.0
    assert lines["p1_p2_ac"].max_active_power.to_from == 100.0
    assert lines["p1_p2_ac"].losses == 0.05
    assert lines["p1_p2_ac"].hurdle_rate == 3.0
    assert lines["p1_p2_ac"].distance_miles == 100.0
    assert lines["p1_p2_ac"].line_cost_per_mw_mile == 20.0
    assert lines["p1_p2_dc"].max_active_power.from_to == 70.0
    assert lines["p1_p2_dc"].max_active_power.to_from == 70.0
    assert lines["p1_p2_dc"].losses == 0.1


def test_public_parser_uses_absolute_capacity_when_reverse_row_is_absent(
    reeds_run_path: Path, tmp_path: Path
) -> None:
    system = build_transmission_case(
        reeds_run_path,
        tmp_path,
        capacity_rows="r,rr,trtype,t,Value\np1,p2,dc,2032,-70\n",
    )

    assert system is not None
    line = next(iter(system.get_components(ReEDSTransmissionLine)))
    assert line.max_active_power.from_to == 70.0
    assert line.max_active_power.to_from == 70.0


@pytest.mark.parametrize(
    "capacity_rows",
    [None, "r,rr,trtype,t,Value\n"],
    ids=["missing", "empty"],
)
def test_public_parser_skips_missing_or_empty_optional_transmission(
    reeds_run_path: Path, tmp_path: Path, capacity_rows: str | None
) -> None:
    system = build_transmission_case(reeds_run_path, tmp_path, capacity_rows=capacity_rows)

    assert system is not None
    assert list(system.get_components(ReEDSInterface)) == []
    assert list(system.get_components(ReEDSTransmissionLine)) == []


def test_public_parser_rejects_malformed_present_transmission_losses(
    reeds_run_path: Path, tmp_path: Path
) -> None:
    capacity_rows = "r,rr,trtype,t,Value\np1,p2,ac,2032,100\n"
    malformed_losses = "r,rr,Value\np1,p2,0.05\n"

    with pytest.raises(PluginError, match="trtype") as captured:
        build_transmission_case(
            reeds_run_path, tmp_path, capacity_rows=capacity_rows, losses=malformed_losses
        )

    reader_error = captured.value.__cause__
    assert isinstance(reader_error, ReaderError)
    assert isinstance(reader_error.__cause__, ValueError)


def test_public_parser_builds_peak_and_profile_from_same_load_source(
    reeds_run_path: Path, tmp_path: Path
) -> None:
    run_path = tmp_path / "run"
    shutil.copytree(reeds_run_path, run_path)
    (run_path / "outputs" / "cap_ivrt.csv").write_text(
        "i,v,r,t,Value\ncan-imports,new1,p1,2032,1\n", encoding="utf-8"
    )
    config_path = copy_package_config(tmp_path)
    configure_csv_sources(config_path)
    config = ReEDSConfig(
        solve_year=2032,
        weather_year=2012,
        case_name="load-profile-test",
        excluded_techs=[],
        config_path_override=config_path,
    )
    context = PluginContext(config=config, store=DataStore(path=run_path))

    result = ReEDSParser.from_context(context).run()

    assert result.system is not None
    demands = {demand.name: demand for demand in result.system.get_components(ReEDSDemand)}
    assert len(demands) == 11
    demand = demands["p1_load"]
    assert demand.max_active_power == pytest.approx(9985.263671875)
    profile = result.system.get_time_series(demand, name="max_active_power")
    assert profile.length == 8760
    assert profile.initial_timestamp == datetime(2012, 1, 1)
    assert profile.resolution == timedelta(hours=1)
    assert profile.data[0] == pytest.approx(7662.10546875)
    metadata = result.system.list_time_series_metadata(demand, name="max_active_power")
    assert len(metadata) == 1
    assert metadata[0].features == {"weather_year": 2012}


def test_declared_load_peaks_use_every_selected_solve_year(tmp_path: Path) -> None:
    columns = ["year", "datetime", "p1"]
    (tmp_path / "inputs_case").mkdir()
    (tmp_path / "inputs_case" / "load-profiles.csv").write_text(
        ",".join(columns)
        + "\n2030,2012-01-01T00:00:00,10\n2030,2012-01-01T01:00:00,12"
        + "\n2032,2012-01-01T00:00:00,20\n2032,2012-01-01T01:00:00,22\n",
        encoding="utf-8",
    )
    config_records: list[dict[str, Any]] = json.loads(
        (ReEDSConfig.package_config_path() / "file_mapping.json").read_bytes()
    )
    load_names = {
        "load_profiles",
        "load_profiles_required",
        "load_profile_values",
        "load_profile_values_required",
        "load_peaks",
    }
    selected = [record for record in config_records if record["name"] in load_names]
    physical_load = next(record for record in selected if record["name"] == "load_profiles")
    physical_load["relative_fpath"] = "inputs_case/load-profiles.csv"
    physical_load["reader"] = {"format": "csv", "options": {"try_parse_dates": True}}
    files = TypeAdapter(list[DataFile]).validate_python(selected)

    sources = DataReader().read_data_files(
        files,
        folder_path=tmp_path,
        placeholders={"solve_year": [2030, 2032], "weather_year": 2012},
    )

    assert sources["load_peaks"].values("region") == ["p1"]
    assert sources["load_peaks"].values("max_active_power") == [22.0]
    assert sources["load_peaks"].values("owner_name") == ["p1_load"]


def test_public_parser_rejects_missing_solve_year_load_profiles(reeds_run_path: Path, tmp_path: Path) -> None:
    columns = ["year", "datetime", *(f"p{index}" for index in range(1, 12))]
    csv_text = ",".join(columns) + "\n2030,2012-01-01T00:00:00," + ",".join("1" for _ in range(11)) + "\n"

    with pytest.raises(PluginError, match="assert step failed") as captured:
        run_parser_with_load_csv(tmp_path, reeds_run_path, csv_text=csv_text)

    assert isinstance(captured.value.__cause__, ReaderError)
    assert isinstance(captured.value.__cause__.__cause__, ValueError)


@pytest.mark.parametrize(
    ("columns", "rows", "message"),
    [
        (
            [*(f"p{index}" for index in range(1, 12))],
            [
                ["2032", "2012-01-01T00:00:00", *(["", *("10" for _ in range(10))])],
                ["2032", "2012-01-01T01:00:00", *(["", *("11" for _ in range(10))])],
            ],
            "assert step failed",
        ),
        (
            [*(f"p{index}" for index in range(1, 12)), "p999"],
            [
                ["2032", "2012-01-01T00:00:00", *("1" for _ in range(12))],
                ["2032", "2012-01-01T01:00:00", *("2" for _ in range(12))],
            ],
            "Missing reference ReEDSRegion named 'p999'",
        ),
        (
            [*(f"p{index}" for index in range(1, 12))],
            [
                ["2032", "2012-01-01T00:00:00", *("1" for _ in range(11))],
                ["2032", "2012-01-01T02:00:00", *("2" for _ in range(11))],
            ],
            "resolution does not match",
        ),
    ],
    ids=["all-null-peak", "unknown-region", "irregular-axis"],
)
def test_public_parser_rejects_invalid_load_profile_rows(
    reeds_run_path: Path,
    tmp_path: Path,
    columns: list[str],
    rows: list[list[str]],
    message: str,
) -> None:
    csv_text = ",".join(["year", "datetime", *columns]) + "\n"
    csv_text += "\n".join(",".join(row) for row in rows) + "\n"

    with pytest.raises(PluginError, match=message) as captured:
        run_parser_with_load_csv(tmp_path, reeds_run_path, csv_text=csv_text)

    assert captured.value.__cause__ is not None
