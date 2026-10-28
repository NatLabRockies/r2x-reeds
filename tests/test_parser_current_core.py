from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import h5py
import numpy as np
import polars as pl
import pytest
from infrasys.time_series_models import SingleTimeSeries
from pydantic import TypeAdapter

from r2x_core import (
    DataStore,
    DocumentSource,
    PluginContext,
    PluginError,
    System,
    TabularSource,
    assemble_tables,
    build_system_from_sources,
)
from r2x_core.exceptions import ReaderError
from r2x_core.models import ParserInstruction
from r2x_core.polars_adapter import PolarsTabularBackend
from r2x_reeds import ReEDSConfig, ReEDSParser
from r2x_reeds.models import ReEDSGenerator, ReEDSRegion, ReEDSReserve
from r2x_reeds.models.components import (
    ReEDSDemand,
    ReEDSEmission,
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
    solve_year: int | list[int] = 2032,
    weather_year: int | list[int] = 2012,
) -> System:
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
    load_file["columns"] = [
        {
            "name": column,
            "dtype": "datetime" if column == "datetime" else "int64" if column == "year" else "float64",
        }
        for column in csv_text.splitlines()[0].split(",")
    ]
    mapping_path.write_text(json.dumps(files), encoding="utf-8")
    config = ReEDSConfig(
        solve_year=solve_year,
        weather_year=weather_year,
        case_name="load-policy-test",
        excluded_techs=[],
        config_path_override=config_path,
    )
    result = ReEDSParser.from_context(PluginContext(config=config, store=DataStore(path=run_path))).run()
    assert result.system is not None
    return result.system


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
                    "requested_solve_weather_year_rows",
                    "load_profiles_required",
                    "load_profile_peak_validation",
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
            if group in {"tran_cap_energy", "tranloss"}:
                for column in item.get("columns", []):
                    if column["name"] == "Value":
                        column["name"] = "value"
            item["reader"] = {"format": "csv"}
    mapping_path.write_text(json.dumps(files), encoding="utf-8")


def build_generator_system(
    run_path: Path,
    *,
    config: ReEDSConfig,
    default_heat_rate: float | None = None,
    fuel_base_sort: Literal["asc", "desc"] | None = None,
    required_capacity_source: bool = False,
    generator_capacity_source: Literal["standard", "degraded"] = "standard",
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
    if fuel_base_sort is not None:
        mapping_path = config_path / "table_mapping.json"
        tables: list[dict[str, Any]] = json.loads(mapping_path.read_text(encoding="utf-8"))
        lookup = next(item for item in tables if item["name"] == "generator_fuel_base_lookup")
        sort = next(operation for operation in lookup["operations"] if operation["operation"] == "sort")
        sort["descending"] = fuel_base_sort == "desc"
        mapping_path.write_text(json.dumps(tables), encoding="utf-8")
    if required_capacity_source:
        mapping_path = config_path / "file_mapping.json"
        files: list[dict[str, Any]] = json.loads(mapping_path.read_text(encoding="utf-8"))
        source_name = (
            "online_capacity_degraded" if generator_capacity_source == "degraded" else "online_capacity"
        )
        source = next(item for item in files if item["name"] == source_name)
        source["info"]["requirement"] = "required"
        mapping_path.write_text(json.dumps(files), encoding="utf-8")
    config = config.model_copy(
        update={
            "config_path_override": config_path,
            "generator_capacity_source": generator_capacity_source,
        }
    )
    context = PluginContext(config=config, store=DataStore(path=run_path))
    result = ReEDSParser.from_context(context).run()
    assert result.system is not None
    return result.system


def test_public_parser_uses_configured_table_mapping_before_parser_rules(
    reeds_run_path: Path, tmp_path: Path
) -> None:
    config_path = copy_package_config(tmp_path)
    configure_csv_sources(config_path)
    custom_tables = [
        {
            "name": "reserve_requirement_rows",
            "operations": [
                {
                    "operation": "rows",
                    "schema": [
                        {"name": "datetime", "dtype": "datetime"},
                        {"name": "name", "dtype": "string"},
                        {"name": "requirement", "dtype": "float64"},
                        {"name": "solve_year", "dtype": "int64"},
                    ],
                    "values": [
                        {
                            "datetime": "2012-01-01T00:00:00",
                            "name": "NorthernGrid_SPINNING",
                            "requirement": 17.25,
                            "solve_year": 2032,
                        },
                        {
                            "datetime": "2012-01-01T01:00:00",
                            "name": "NorthernGrid_SPINNING",
                            "requirement": 18.5,
                            "solve_year": 2032,
                        },
                    ],
                }
            ],
        }
    ]
    package_mapping = json.loads(
        (ReEDSConfig.package_config_path() / "table_mapping.json").read_text(encoding="utf-8")
    )
    table_mapping_path = config_path / "table_mapping.json"
    table_mapping_path.write_text(
        json.dumps(
            [record for record in package_mapping if record["name"] != "reserve_requirement_rows"]
            + custom_tables
        ),
        encoding="utf-8",
    )
    config = ReEDSConfig(
        solve_year=2032,
        weather_year=2012,
        case_name="configured-table-mapping-test",
        excluded_techs=[],
        config_path_override=config_path,
    )

    result = ReEDSParser.from_context(
        PluginContext(config=config, store=DataStore(path=reeds_run_path))
    ).run()

    assert result.system is not None
    reserve = result.system.get_component(ReEDSReserve, "NorthernGrid_SPINNING")
    matching_series = result.system.list_time_series(
        reserve,
        name="requirement",
        solve_year=2032,
        weather_year=2012,
    )
    assert len(matching_series) == 1
    series = matching_series[0]
    assert isinstance(series, SingleTimeSeries)
    assert series.data.tolist() == [17.25, 18.5]


@pytest.mark.parametrize(
    ("mapping_contents", "expected_cause"),
    [(None, "missing"), ("{}", "malformed")],
    ids=["missing-mapping", "malformed-mapping"],
)
def test_public_parser_rejects_missing_or_malformed_table_mapping(
    reeds_run_path: Path,
    tmp_path: Path,
    mapping_contents: str | None,
    expected_cause: Literal["missing", "malformed"],
) -> None:
    config_path = copy_package_config(tmp_path)
    configure_csv_sources(config_path)
    table_mapping_path = config_path / "table_mapping.json"
    if mapping_contents is None:
        table_mapping_path.unlink()
    else:
        table_mapping_path.write_text(mapping_contents, encoding="utf-8")
    config = ReEDSConfig(
        solve_year=2032,
        weather_year=2012,
        case_name="invalid-table-mapping-test",
        config_path_override=config_path,
    )

    with pytest.raises(PluginError) as captured:
        ReEDSParser.from_context(PluginContext(config=config, store=DataStore(path=reeds_run_path))).run()

    if expected_cause == "missing":
        assert isinstance(captured.value.__cause__, FileNotFoundError)
        assert captured.value.__cause__.filename == str(table_mapping_path)
        assert isinstance(captured.value.__cause__.__cause__, FileNotFoundError)
        assert "copy the current package configuration" in str(captured.value)
        assert "reapply customizations" in str(captured.value)
    else:
        assert isinstance(captured.value.__cause__, ValueError)
        assert "valid list" in str(captured.value.__cause__)


def test_public_parser_explains_how_to_update_missing_validation_records(
    reeds_run_path: Path, tmp_path: Path
) -> None:
    """An incomplete configuration tells users how to rebuild their override."""
    config_path = copy_package_config(tmp_path)
    mapping_path = config_path / "file_mapping.json"
    records = json.loads(mapping_path.read_text(encoding="utf-8"))
    records = [record for record in records if record["name"] != "generator_fom_validation"]
    mapping_path.write_text(json.dumps(records), encoding="utf-8")
    config = ReEDSConfig(solve_year=2032, weather_year=2012, config_path_override=config_path)

    with pytest.raises(PluginError, match="Missing post-assembly validation record") as captured:
        ReEDSParser.from_context(PluginContext(config=config, store=DataStore(path=reeds_run_path))).run()

    assert "generator_fom_validation" in str(captured.value)
    assert "copy the current package configuration" in str(captured.value)
    assert "reapply customizations" in str(captured.value)


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
    assert [(item.name, item.capacity, item.fom_cost) for item in generators] == [
        ("upv_1_p1_2032", 40.0, None)
    ]


def test_duplicate_outage_lookup_does_not_multiply_generator_capacity(
    reeds_run_path: Path, tmp_path: Path
) -> None:
    """Retain the first technology lookup without duplicating contributing vintages."""
    run_path = tmp_path / "run"
    shutil.copytree(reeds_run_path, run_path)
    outputs = run_path / "outputs"
    (outputs / "cap_ivrt.csv").write_text(
        "i,v,r,t,Value\nupv_1,new1,p1,2032,10\nupv_1,new2,p1,2032,30\n", encoding="utf-8"
    )
    (outputs / "forced_outage.csv").write_text("i,Value\nupv_1,0.1\nupv_1,0.1\nupv_1,0.9\n", encoding="utf-8")
    config = ReEDSConfig(solve_year=2032, weather_year=2012, case_name="duplicate-outage-lookup")

    system = build_generator_system(run_path, config=config)

    generators = list(system.get_components(ReEDSVariableGenerator))
    assert [
        (generator.name, generator.capacity, generator.forced_outage_rate) for generator in generators
    ] == [("upv_1_p1_2032", 40.0, pytest.approx(0.1))]


def test_public_parser_handles_empty_reserve_product_configuration(
    reeds_run_path: Path, tmp_path: Path
) -> None:
    run_path = tmp_path / "run"
    shutil.copytree(reeds_run_path, run_path)
    system = build_generator_system(
        run_path,
        config=ReEDSConfig(solve_year=2032, weather_year=2012, case_name="empty-reserve-test"),
    )

    assert list(system.get_components(ReEDSReserve)) == []


def test_public_parser_keeps_solve_year_generator_states_and_profiles_separate(
    reeds_run_path: Path, tmp_path: Path
) -> None:
    run_path = tmp_path / "run"
    shutil.copytree(reeds_run_path, run_path)
    inputs = run_path / "inputs_case"
    outputs = run_path / "outputs"
    (outputs / "cap_ivrt.csv").write_text(
        "i,v,r,t,Value\n"
        "Gas-CC,init-1,p1,2032,100\nGas-CC,init-1,p1,2035,250\n"
        "upv_1,new1,p1,2032,10\nupv_1,new1,p1,2035,30\n"
        "wind-ons_1,new1,p1,2032,20\nwind-ons_1,new1,p1,2035,40\n",
        encoding="utf-8",
    )
    (outputs / "heat_rate.csv").write_text(
        "i,v,r,t,Value\nGas-CC,init-1,p1,2032,12\nGas-CC,init-1,p1,2035,14\n",
        encoding="utf-8",
    )
    (outputs / "fuel2tech.csv").write_text("f,i,Value\nGAS,Gas-CC,c_bool(True)\n", encoding="utf-8")
    (outputs / "emit_rate.csv").write_text(
        "eall,etype,i,r,t,v,Value\n"
        "co2,combustion,Gas-CC,p1,2032,init-1,0.1\n"
        "nox,process,Gas-CC,p1,2032,init-1,0.03\n"
        "co2,,Gas-CC,p1,2035,init-1,0.2\n"
        "n2o,upstream,Gas-CC,p1,2035,init-1,0.04\n",
        encoding="utf-8",
    )
    (inputs / "plantcharout.csv").write_text(
        "*i,t,variable,value\nGas-CC,2032,fom,20081\nGas-CC,2035,fom,25081\n",
        encoding="utf-8",
    )

    regions = [f"p{index}" for index in range(1, 12)]
    load_columns = np.asarray(regions, dtype="S8")
    timestamps = np.asarray(
        [
            "2012-01-01T00:00:00",
            "2012-01-01T01:00:00",
            "2013-01-01T00:00:00",
            "2013-01-01T01:00:00",
        ]
        * 2,
        dtype="S19",
    )
    load_values = np.zeros((8, len(regions)), dtype=np.float32)
    load_values[:, 0] = [10.0, 12.0, 1000.0, 1200.0, 100.0, 120.0, 2000.0, 2200.0]
    with h5py.File(inputs / "load.h5", "w") as handle:
        handle.create_dataset("columns", data=load_columns)
        handle.create_dataset("data", data=load_values)
        handle.create_dataset("index_0", data=np.asarray([2032] * 4 + [2035] * 4))
        handle.create_dataset("index_1", data=timestamps)
        handle.create_dataset("index_names", data=np.asarray(["year", "datetime"], dtype="S10"))

    (outputs / "transmission_capacity.csv").write_text(
        "r,rr,trtype,t,value\np1,p2,ac,2032,100\np2,p1,ac,2032,90\np1,p2,ac,2035,250\np2,p1,ac,2035,200\n",
        encoding="utf-8",
    )
    (outputs / "transmission_losses.csv").write_text(
        "r,rr,trtype,value\np1,p2,ac,0.05\np2,p1,ac,0.06\n", encoding="utf-8"
    )
    (outputs / "cost_hurdle_rate.csv").write_text(
        "r,rr,allt,Value\np1,p2,2032,3\np2,p1,2032,4\np1,p2,2035,7\np2,p1,2035,8\n",
        encoding="utf-8",
    )
    (inputs / "transmission_distance.csv").write_text("r,rr,miles\np1,p2,100\np2,p1,110\n", encoding="utf-8")
    (inputs / "transmission_cost_ac.csv").write_text(
        "r,rr,USD2004perMW_forward,USD2004perMW_reverse,tscbin,binwidth_USD2004\n"
        "p1,p2,3000,2800,2,10\np1,p2,2000,1800,1,10\n",
        encoding="utf-8",
    )

    with h5py.File(inputs / "recf.h5", "w") as handle:
        handle.create_dataset("columns", data=np.asarray(["upv_1|p1", "wind-ons_1|p1"], dtype="S32"))
        handle.create_dataset("data", data=np.asarray([[0.0, 0.25], [0.5, 0.5]], dtype=np.float32))
        handle.create_dataset(
            "index_0",
            data=np.asarray(["2012-01-01T00:00:00", "2012-01-01T01:00:00"], dtype="S19"),
        )
        handle.create_dataset("index_names", data=np.asarray(["datetime"], dtype="S8"))

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
        solve_year=[2032, 2035],
        weather_year=[2012, 2013],
        case_name="multi-solve-year-state-test",
        excluded_techs=[],
        config_path_override=config_path,
    )
    result = ReEDSParser.from_context(PluginContext(config=config, store=DataStore(path=run_path))).run()

    assert result.system is not None
    system = result.system
    thermal = sorted(system.get_components(ReEDSThermalGenerator), key=lambda item: item.solve_year)
    assert [(item.solve_year, item.capacity, item.fom_cost) for item in thermal] == [
        (2032, 100.0, 20081.0),
        (2035, 250.0, 25081.0),
    ]
    variable = sorted(
        system.get_components(ReEDSVariableGenerator), key=lambda item: (item.solve_year, item.technology)
    )
    assert [(item.solve_year, item.technology, item.capacity) for item in variable] == [
        (2032, "upv_1", 10.0),
        (2032, "wind-ons_1", 20.0),
        (2035, "upv_1", 30.0),
        (2035, "wind-ons_1", 40.0),
    ]
    for unit, expected_values in zip(
        variable,
        ([0.0, 5.0], [5.0, 10.0], [0.0, 15.0], [10.0, 20.0]),
        strict=True,
    ):
        profile = system.get_time_series(unit, name="max_active_power", solve_year=unit.solve_year)
        np.testing.assert_allclose(profile.data, expected_values)
        assert system.list_time_series_metadata(unit, name="max_active_power", solve_year=unit.solve_year)
    emissions = [
        system.get_supplemental_attributes_with_component(unit, supplemental_attribute_type=ReEDSEmission)
        for unit in thermal
    ]
    assert [[item.solve_year for item in attrs] for attrs in emissions] == [[2032, 2032], [2035, 2035]]
    assert [
        sorted((item.type.value, item.source.value, item.rate) for item in attrs) for attrs in emissions
    ] == [
        [("CO2", "COMBUSTION", 0.1), ("NOx", "PRECOMBUSTION", 0.03)],
        [("CO2", "COMBUSTION", 0.2), ("N2O", "PRECOMBUSTION", 0.04)],
    ]

    demands = sorted(
        (item for item in system.get_components(ReEDSDemand) if item.region.name == "p1"),
        key=lambda item: item.solve_year,
    )
    assert [(item.name, item.solve_year, item.max_active_power) for item in demands] == [
        ("p1_load_2032", 2032, 1200.0),
        ("p1_load_2035", 2035, 2200.0),
    ]
    for demand, profiles in zip(
        demands,
        (([10.0, 12.0], [1000.0, 1200.0]), ([100.0, 120.0], [2000.0, 2200.0])),
        strict=True,
    ):
        for weather_year, expected_profile in zip((2012, 2013), profiles, strict=True):
            series = system.get_time_series(
                demand,
                name="max_active_power",
                solve_year=demand.solve_year,
                weather_year=weather_year,
            )
            np.testing.assert_allclose(series.data, expected_profile)

    p1 = system.get_component(ReEDSRegion, "p1")
    reserve_expectations = {
        "SPINNING": ([0.3, 0.36], [3.0, 3.6]),
        "FLEXIBILITY": ([0.5, 1.4], [1.0, 3.2]),
        "REGULATION": ([0.35, 0.65], [1.5, 2.29]),
    }
    for reserve_type, year_profiles in reserve_expectations.items():
        reserve = system.get_component(ReEDSReserve, f"{p1.transmission_region}_{reserve_type}")
        for year, expected_values in zip((2032, 2035), year_profiles, strict=True):
            profile = system.get_time_series(
                reserve,
                name="requirement",
                solve_year=year,
                weather_year=2012,
            ).data
            expected = np.zeros(8760)
            expected[:2] = expected_values
            np.testing.assert_allclose(profile, expected)

    lines = sorted(system.get_components(ReEDSTransmissionLine), key=lambda item: item.solve_year)
    assert [
        (
            line.name,
            line.solve_year,
            line.max_active_power.from_to,
            line.max_active_power.to_from,
            line.hurdle_rate,
        )
        for line in lines
    ] == [
        ("p1_p2_ac_2032", 2032, 90.0, 100.0, 3.0),
        ("p1_p2_ac_2035", 2035, 200.0, 250.0, 7.0),
    ]


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
    ] == [("gas-cc_init-1_p1_2032", "gas-cc", 100.0, 12.0, "gas")]
    assert [(item.name, item.technology, item.capacity) for item in variable] == [
        ("upv_1_p1_2032", "upv_1", 40.0)
    ]


@pytest.mark.parametrize(
    ("source", "expected_capacity"),
    [("standard", 100.0), ("degraded", 250.0)],
)
def test_public_parser_selects_the_configured_generator_capacity_source(
    reeds_run_path: Path,
    tmp_path: Path,
    source: Literal["standard", "degraded"],
    expected_capacity: float,
) -> None:
    run_path = tmp_path / "run"
    shutil.copytree(reeds_run_path, run_path)
    outputs = run_path / "outputs"
    (outputs / "cap_ivrt.csv").write_text("i,v,r,t,Value\nGas-CC,init-1,p1,2032,100\n", encoding="utf-8")
    (outputs / "cap_deg_ivrt.csv").write_text("i,v,r,t,Value\nGas-CC,init-1,p1,2032,250\n", encoding="utf-8")
    (outputs / "heat_rate.csv").write_text("i,v,r,t,Value\nGas-CC,init-1,p1,2032,12\n", encoding="utf-8")
    (outputs / "fuel2tech.csv").write_text("f,i,Value\nGAS,Gas-CC,c_bool(True)\n", encoding="utf-8")

    system = build_generator_system(
        run_path,
        config=ReEDSConfig(solve_year=2032, weather_year=2012, case_name="capacity-source-test"),
        generator_capacity_source=source,
    )

    generator = system.get_component(ReEDSThermalGenerator, "gas-cc_init-1_p1_2032")
    assert generator.capacity == expected_capacity


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
    ] == [("battery_4_new1_p1_2032", 20.0, 4.0, 0.8)]
    assert hydro["hydd"].is_dispatchable is True
    assert hydro["hydnd"].is_dispatchable is False


def test_public_parser_uses_overlapping_subset_memberships_independently_of_solar_family(
    reeds_run_path: Path, tmp_path: Path
) -> None:
    run_path = tmp_path / "run"
    shutil.copytree(reeds_run_path, run_path)
    (run_path / "outputs" / "cap_ivrt.csv").write_text(
        "i,v,r,t,Value\nupv_1,new1,p1,2032,100\ncsp1_1,new1,p1,2032,200\npvb1_1,new1,p1,2032,300\n",
        encoding="utf-8",
    )
    config_path = copy_package_config(tmp_path)
    configure_csv_sources(config_path, include_all=True)
    defaults_path = config_path / "defaults.json"
    defaults = json.loads(defaults_path.read_text(encoding="utf-8"))
    spinning = next(
        product for product in defaults["reserve_products"] if product["reserve_type"] == "SPINNING"
    )
    defaults["reserve_products"] = [spinning]
    defaults["reserve_provider_exclusions"] = [
        {"reserve_type": "SPINNING", "technology_category": "renewable"}
    ]
    defaults_path.write_text(json.dumps(defaults), encoding="utf-8")
    config = ReEDSConfig(
        solve_year=2032,
        weather_year=2012,
        case_name="subset-membership-test",
        excluded_techs=[],
        config_path_override=config_path,
    )
    system = (
        ReEDSParser.from_context(PluginContext(config=config, store=DataStore(path=run_path))).run().system
    )

    assert system is not None
    solar_units = {unit.technology: unit for unit in system.get_components(ReEDSVariableGenerator)}
    assert set(solar_units) == {"upv_1", "csp1_1", "pvb1_1"}
    assert all(unit.category == "solar" for unit in solar_units.values())
    spinning_name = f"{system.get_component(ReEDSRegion, 'p1').transmission_region}_SPINNING"
    assert solar_units["upv_1"].ext.get("reserves", []) == []
    assert solar_units["csp1_1"].ext.get("reserves", []) == []
    assert solar_units["pvb1_1"].ext["reserves"] == [spinning_name]


def test_parser_rejects_missing_characteristic_year_switch(reeds_run_path: Path, tmp_path: Path) -> None:
    """A missing required FOM year is an error, not an empty generator system."""
    run_path = tmp_path / "run"
    shutil.copytree(reeds_run_path, run_path)
    switches_path = run_path / "inputs_case" / "switches.csv"
    rows = switches_path.read_text(encoding="utf-8").splitlines(keepends=True)
    assert any(row.startswith("GSw_UpgradeChar_Year,") for row in rows)
    switches_path.write_text(
        "".join(row for row in rows if not row.startswith("GSw_UpgradeChar_Year,")), encoding="utf-8"
    )
    config = ReEDSConfig(solve_year=2032, weather_year=2012, case_name="missing-characteristic-year")

    with pytest.raises(PluginError, match="GSw_UpgradeChar_Year must be a valid integer"):
        build_generator_system(run_path, config=config)


@pytest.mark.parametrize("invalid_scalar", [True, False], ids=["fom-error-first", "snapshot-error"])
def test_fom_validation_precedes_materialized_generator_errors(
    reeds_run_path: Path, tmp_path: Path, *, invalid_scalar: bool
) -> None:
    """Report an earlier FOM policy error before an invalid generator value is materialized."""
    run_path = tmp_path / "run"
    shutil.copytree(reeds_run_path, run_path)
    (run_path / "outputs" / "cap_ivrt.csv").write_text(
        "i,v,r,t,Value\nupv_1,new1,p1,2032,100\n", encoding="utf-8"
    )
    (run_path / "outputs" / "cost_vom.csv").write_text(
        "i,v,r,t,value\nupv_1,new1,p1,2032,not-a-number\n", encoding="utf-8"
    )
    if invalid_scalar:
        scalars_path = run_path / "inputs_case" / "scalars.csv"
        scalars = scalars_path.read_text(encoding="utf-8")
        scalars_path.write_text(scalars + "cost_fom_psh,14000,duplicate\n", encoding="utf-8")

    expected = "FOM scalar cardinality must be exactly one" if invalid_scalar else "conversion from"
    config = ReEDSConfig(solve_year=2032, weather_year=2012, case_name="fom-error-order")
    with pytest.raises(PluginError, match=expected):
        build_generator_system(run_path, config=config)


def test_public_parser_excludes_or_rejects_unsupported_consuming_technology(
    reeds_run_path: Path, tmp_path: Path
) -> None:
    run_path = tmp_path / "run"
    shutil.copytree(reeds_run_path, run_path)
    (run_path / "outputs" / "cap_ivrt.csv").write_text(
        "i,v,r,t,Value\nGas-CC,init-1,p1,2032,100\nelectrolyzer,new1,p1,2032,20\n",
        encoding="utf-8",
    )
    config = ReEDSConfig(solve_year=2032, weather_year=2012)

    system = build_generator_system(run_path, config=config)

    assert [unit.technology for unit in system.get_components(ReEDSThermalGenerator)] == ["gas-cc"]

    included_run_path = tmp_path / "included-run"
    shutil.copytree(reeds_run_path, included_run_path)
    (included_run_path / "outputs" / "cap_ivrt.csv").write_text(
        "i,v,r,t,Value\nGas-CC,init-1,p1,2032,100\nelectrolyzer,new1,p1,2032,20\n",
        encoding="utf-8",
    )
    with pytest.raises(PluginError):
        build_generator_system(included_run_path, config=config.model_copy(update={"excluded_techs": []}))


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
    assert [unit.name for unit in system.get_components(ReEDSVariableGenerator)] == ["upv_1_p1_2032"]


def test_public_parser_reports_a_missing_required_hierarchy_file(
    reeds_run_path: Path, tmp_path: Path
) -> None:
    run_path = tmp_path / "run"
    shutil.copytree(reeds_run_path, run_path)
    (run_path / "inputs_case" / "hierarchy.csv").unlink()
    write_current_meta(run_path)
    config_path = copy_package_config(tmp_path)
    configure_csv_sources(config_path, include_all=True)
    config = ReEDSConfig(
        solve_year=2032,
        weather_year=2012,
        case_name="missing-hierarchy",
        config_path_override=config_path,
    )
    context = PluginContext(config=config, store=DataStore(path=run_path))

    with pytest.raises(PluginError, match=r"hierarchy\.csv") as captured:
        ReEDSParser.from_context(context).run()

    assert isinstance(captured.value.__cause__, FileNotFoundError)
    assert "copy the current package configuration" not in str(captured.value)


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


def test_transmission_assembly_is_owned_by_the_flat_table_mapping() -> None:
    file_records = json.loads((ReEDSConfig.package_config_path() / "file_mapping.json").read_text())
    table_records = json.loads((ReEDSConfig.package_config_path() / "table_mapping.json").read_text())

    file_names = {record["name"] for record in file_records}
    table_names = {record["name"] for record in table_records}
    assert (
        not {
            "transmission_capacity_selected",
            "transmission_losses_selected",
            "cost_hurdle_rate_selected",
            "transmission_capacity_reverse",
            "transmission_joined_rows",
            "transmission_interface_rows",
            "transmission_line_rows",
        }
        & file_names
    )
    assert {
        "transmission_capacity_selected",
        "transmission_losses_selected",
        "cost_hurdle_rate_selected",
        "transmission_capacity_reverse_rows",
        "transmission_joined_rows",
        "transmission_interface_rows",
        "transmission_line_rows",
    } <= table_names

    transmission_input = next(record for record in file_records if record["name"] == "transmission_capacity")
    assert "columns" not in transmission_input
    assert [step["op"] for step in transmission_input["proc_spec"]["steps"]] == [
        "lowercase",
        "rename_columns",
        "cast_columns",
    ]
    transmission_losses = next(record for record in file_records if record["name"] == "transmission_losses")
    assert "columns" not in transmission_losses
    assert [step["op"] for step in transmission_losses["proc_spec"]["steps"]] == [
        "lowercase",
        "rename_columns",
        "cast_columns",
    ]
    capacity_selection = next(
        record for record in table_records if record["name"] == "transmission_capacity_selected"
    )
    assert [operation["operation"] for operation in capacity_selection["operations"]] == [
        "first_present",
        "join",
        "choose",
        "choose",
        "concat_strings",
        "concat_strings",
    ]
    assert capacity_selection["operations"][0]["sources"] == [
        "transmission_capacity",
        "transmission_capacity_empty",
    ]
    assert capacity_selection["operations"][1] == {
        "operation": "join",
        "source": "requested_solve_year_keys",
        "how": "inner",
        "on": ["year"],
        "columns": [],
    }
    losses_selection = next(
        record for record in table_records if record["name"] == "transmission_losses_selected"
    )
    assert losses_selection["operations"] == [
        {
            "operation": "first_present",
            "sources": ["transmission_losses", "transmission_losses_empty"],
        }
    ]

    joined = next(record for record in table_records if record["name"] == "transmission_joined_rows")
    operations = joined["operations"]
    assert [operation["operation"] for operation in operations] == [
        "join",
        "join",
        "join",
        "join",
        "join",
        "fill_null",
        "absolute",
        "absolute",
        "object",
        "divide",
    ]


def test_public_assembly_preserves_duplicate_transmission_reverse_matches(tmp_path: Path) -> None:
    backend = PolarsTabularBackend()
    capacity = TabularSource(
        pl.DataFrame(
            {
                "from_region": ["a", "a", "b"],
                "to_region": ["b", "b", "a"],
                "trtype": ["ac", "ac", "ac"],
                "year": [2032, 2032, 2032],
                "capacity": [100.0, 120.0, 90.0],
            },
            schema={
                "from_region": pl.String,
                "to_region": pl.String,
                "trtype": pl.String,
                "year": pl.Int64,
                "capacity": pl.Float64,
            },
        ).lazy(),
        backend,
    )
    empty_sources = {
        "transmission_losses": TabularSource(
            pl.DataFrame(
                schema={
                    "from_region": pl.String,
                    "to_region": pl.String,
                    "trtype": pl.String,
                    "losses": pl.Float64,
                }
            ).lazy(),
            backend,
        ),
        "cost_hurdle_rate": TabularSource(
            pl.DataFrame(
                schema={
                    "from_region": pl.String,
                    "to_region": pl.String,
                    "year": pl.Int64,
                    "cost_hurdle_rate": pl.Float64,
                }
            ).lazy(),
            backend,
        ),
        "transmission_distance_cost_ac": TabularSource(
            pl.DataFrame(
                schema={
                    "from_region": pl.String,
                    "to_region": pl.String,
                    "cost_usd_per_mw_forward": pl.Float64,
                    "cost_usd_per_mw_reverse": pl.Float64,
                    "cost_bin": pl.Int64,
                    "binwidth_usd2004": pl.Float64,
                }
            ).lazy(),
            backend,
        ),
        "transmission_distance_cost_dc": TabularSource(
            pl.DataFrame(
                schema={
                    "from_region": pl.String,
                    "to_region": pl.String,
                    "distance_miles": pl.Float64,
                }
            ).lazy(),
            backend,
        ),
    }
    sources = {
        "transmission_capacity": capacity,
        "requested_solve_year_rows": TabularSource(
            pl.DataFrame({"solve_year": [2032]}, schema={"solve_year": pl.Int64}).lazy(), backend
        ),
        **empty_sources,
    }
    package_records = json.loads(
        (ReEDSConfig.package_config_path() / "table_mapping.json").read_text(encoding="utf-8")
    )
    names = {
        "transmission_capacity_empty",
        "transmission_capacity_selected",
        "transmission_losses_empty",
        "transmission_losses_selected",
        "cost_hurdle_rate_selected",
        "requested_solve_year_keys",
        "transmission_distance_cost_ac_rows",
        "transmission_distance_cost_dc_rows",
        "transmission_capacity_reverse_rows",
        "transmission_joined_rows",
        "transmission_interface_rows",
        "transmission_line_rows",
    }
    mapping_path = tmp_path / "table_mapping.json"
    mapping_path.write_text(json.dumps([record for record in package_records if record["name"] in names]))

    tables = assemble_tables(sources, mapping_path=mapping_path, backend=backend)
    joined_rows = list(tables["transmission_joined_rows"].iter_rows())

    assert len(joined_rows) == 4
    assert [
        (row["capacity"], row["reverse_capacity"], row["from_to"], row["to_from"]) for row in joined_rows
    ] == [
        (100.0, 90.0, 90.0, 100.0),
        (120.0, 90.0, 90.0, 120.0),
        (90.0, 100.0, 100.0, 90.0),
        (90.0, 120.0, 120.0, 90.0),
    ]


def test_public_parser_builds_transmission_with_directional_and_lookup_policy(
    reeds_run_path: Path, tmp_path: Path
) -> None:
    capacity_rows = "r,rr,trtype,t,value\np1,p2,ac,2032,100\np2,p1,ac,2032,90\np1,p2,dc,2032,70\n"
    losses = "r,rr,trtype,value\np1,p2,ac,0.05\np2,p1,ac,0.06\np1,p2,dc,0.1\n"

    system = build_transmission_case(reeds_run_path, tmp_path, capacity_rows=capacity_rows, losses=losses)

    assert system is not None
    regions = {region.name: region for region in system.get_components(ReEDSRegion)}
    interfaces = list(system.get_components(ReEDSInterface))
    assert [(item.name, item.from_region, item.to_region) for item in interfaces] == [
        ("p1||p2", regions["p1"], regions["p2"])
    ]
    lines = {line.name: line for line in system.get_components(ReEDSTransmissionLine)}
    assert set(lines) == {"p1_p2_ac_2032", "p1_p2_dc_2032"}
    assert lines["p1_p2_ac_2032"].solve_year == 2032
    assert lines["p1_p2_ac_2032"].interface is interfaces[0]
    assert lines["p1_p2_ac_2032"].max_active_power.from_to == 90.0
    assert lines["p1_p2_ac_2032"].max_active_power.to_from == 100.0
    assert lines["p1_p2_ac_2032"].losses == 0.05
    assert lines["p1_p2_ac_2032"].hurdle_rate == 3.0
    assert lines["p1_p2_ac_2032"].distance_miles == 100.0
    assert lines["p1_p2_ac_2032"].line_cost_per_mw_mile == 20.0
    assert lines["p1_p2_dc_2032"].max_active_power.from_to == 70.0
    assert lines["p1_p2_dc_2032"].max_active_power.to_from == 70.0
    assert lines["p1_p2_dc_2032"].losses == 0.1


def test_public_parser_uses_absolute_capacity_when_reverse_row_is_absent(
    reeds_run_path: Path, tmp_path: Path
) -> None:
    system = build_transmission_case(
        reeds_run_path,
        tmp_path,
        capacity_rows="r,rr,trtype,t,value\np1,p2,dc,2032,-70\n",
    )

    assert system is not None
    line = next(iter(system.get_components(ReEDSTransmissionLine)))
    assert line.max_active_power.from_to == 70.0
    assert line.max_active_power.to_from == 70.0


@pytest.mark.parametrize(
    "capacity_rows",
    [None, "r,rr,trtype,t,value\n"],
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
    capacity_rows = "r,rr,trtype,t,value\np1,p2,ac,2032,100\n"
    malformed_losses = "r,rr,value\np1,p2,0.05\n"

    with pytest.raises(PluginError, match="trtype") as captured:
        build_transmission_case(
            reeds_run_path, tmp_path, capacity_rows=capacity_rows, losses=malformed_losses
        )

    reader_error = captured.value.__cause__
    assert isinstance(reader_error, ReaderError)
    assert isinstance(reader_error.__cause__, ValueError)


def test_load_table_mapping_outputs_parser_ready_solve_year_owners(tmp_path: Path) -> None:
    backend = PolarsTabularBackend()
    sources = {
        "load_profiles": TabularSource(
            pl.DataFrame(
                {
                    "datetime": [
                        datetime(2012, 1, 1),
                        datetime(2012, 1, 1, 1),
                        datetime(2013, 1, 1),
                        datetime(2013, 1, 1, 1),
                    ],
                    "solve_year": [2030, 2030, 2032, 2032],
                    "weather_year": [2012, 2012, 2013, 2013],
                    "p1": [10.0, 12.0, 20.0, 22.0],
                },
                schema={
                    "datetime": pl.Datetime("us"),
                    "solve_year": pl.Int64,
                    "weather_year": pl.Int64,
                    "p1": pl.Float64,
                },
            ).lazy(),
            backend,
        ),
        "requested_solve_weather_year_rows": TabularSource(
            pl.DataFrame(
                {"solve_year": [2030, 2032], "weather_year": [2012, 2013]},
                schema={"solve_year": pl.Int64, "weather_year": pl.Int64},
            ).lazy(),
            backend,
        ),
        "load_owner_names": TabularSource(
            pl.DataFrame(
                {
                    "region": ["p1", "p1"],
                    "solve_year": [2030, 2032],
                    "owner_name": ["p1_load_2030", "p1_load_2032"],
                },
                schema={
                    "region": pl.String,
                    "solve_year": pl.Int64,
                    "owner_name": pl.String,
                },
            ).lazy(),
            backend,
        ),
    }
    package_mapping = json.loads(
        (ReEDSConfig.package_config_path() / "table_mapping.json").read_text(encoding="utf-8")
    )
    load_mapping = [
        record
        for record in package_mapping
        if record["name"] in {"load_profile_values", "load_peaks", "load_profile_rows"}
    ]
    mapping_path = tmp_path / "table_mapping.json"
    mapping_path.write_text(json.dumps(load_mapping), encoding="utf-8")

    tables = assemble_tables(sources, mapping_path=mapping_path, backend=backend)

    assert list(tables["load_peaks"].iter_rows()) == [
        {
            "region": "p1",
            "solve_year": 2030,
            "max_active_power": 12.0,
            "owner_name": "p1_load_2030",
        },
        {
            "region": "p1",
            "solve_year": 2032,
            "max_active_power": 22.0,
            "owner_name": "p1_load_2032",
        },
    ]
    profile_rows = list(tables["load_profile_rows"].iter_rows())
    assert [(row["owner_name"], row["weather_year"], row["value"]) for row in profile_rows] == [
        ("p1_load_2030", 2012, 10.0),
        ("p1_load_2030", 2012, 12.0),
        ("p1_load_2032", 2013, 20.0),
        ("p1_load_2032", 2013, 22.0),
    ]


def test_hydro_month_completeness_requires_twelve_distinct_nonnull_values(tmp_path: Path) -> None:
    """Only complete, unique monthly profiles reach the public hydro table."""
    backend = PolarsTabularBackend()
    months = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    hours = [744, 696, 744, 720, 744, 720, 744, 744, 720, 744, 720, 744]
    calendar = pl.DataFrame(
        {"month": months, "month_number": range(1, 13), "hours": hours},
        schema={"month": pl.String, "month_number": pl.Int64, "hours": pl.Int64},
    )
    hydro_rows: list[dict[str, object]] = []
    for month_number, month in enumerate(months, start=1):
        hydro_rows.append(
            {
                "technology": "complete",
                "region": "p1",
                "solve_year": 2032,
                "month": month,
                "hydro_cf": month_number / 100,
            }
        )

    def make_hydro_row(technology: str, month: str, value: float | None) -> dict[str, object]:
        return {
            "technology": technology,
            "region": "p1",
            "solve_year": 2032,
            "month": month,
            "hydro_cf": value,
        }

    additional_hydro_rows = [
        make_hydro_row("duplicate", "jan", 0.1),
        make_hydro_row("duplicate", "jan", 0.15),
    ]
    additional_hydro_rows.extend(make_hydro_row("duplicate", month, 0.2) for month in months[1:11])
    additional_hydro_rows.extend(make_hydro_row("missing", month, 0.3) for month in months[:11])
    additional_hydro_rows.extend(
        make_hydro_row("null-value", month, None if month == "dec" else 0.4) for month in months
    )
    hydro_rows.extend(additional_hydro_rows)
    sources = {
        "hydro_cf": TabularSource(
            pl.DataFrame(
                hydro_rows,
                schema={
                    "technology": pl.String,
                    "region": pl.String,
                    "solve_year": pl.Int64,
                    "month": pl.String,
                    "hydro_cf": pl.Float64,
                },
            ).lazy(),
            backend,
        ),
        "hydro_weather_calendar": TabularSource(calendar.lazy(), backend),
    }
    config_path = ReEDSConfig.package_config_path()
    package_records = json.loads((config_path / "table_mapping.json").read_text(encoding="utf-8"))
    names = {
        "hydro_monthly_values",
        "hydro_month_counts",
        "hydro_month_distinct_counts",
        "hydro_month_complete",
        "hydro_complete_months",
    }
    mapping = [record for record in package_records if record["name"] in names]
    assert {record["name"] for record in mapping} == names
    mapping_path = tmp_path / "hydro-table-mapping.json"
    mapping_path.write_text(json.dumps(mapping), encoding="utf-8")

    tables = assemble_tables(sources, mapping_path=mapping_path, backend=backend)

    rows = list(tables["hydro_complete_months"].iter_rows())
    assert [(row["technology"], row["month_number"], row["hours"], row["hydro_cf"]) for row in rows] == [
        ("complete", month_number, hours[month_number - 1], month_number / 100)
        for month_number in range(1, 13)
    ]


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
    demand = demands["p1_load_2032"]
    assert demand.max_active_power == pytest.approx(9985.263671875)
    profile = result.system.get_time_series(demand, name="max_active_power")
    assert profile.length == 8760
    assert profile.initial_timestamp == datetime(2012, 1, 1)
    assert profile.resolution == timedelta(hours=1)
    assert profile.data[0] == pytest.approx(7662.10546875)
    metadata = result.system.list_time_series_metadata(demand, name="max_active_power")
    assert len(metadata) == 1
    assert metadata[0].features == {"solve_year": 2032, "weather_year": 2012}


def test_public_parser_keeps_load_peaks_for_every_selected_solve_year(
    reeds_run_path: Path, tmp_path: Path
) -> None:
    columns = ["year", "datetime", *(f"p{index}" for index in range(1, 12))]
    rows = [
        [2030, "2012-01-01T00:00:00", 10, *([1] * 10)],
        [2030, "2012-01-01T01:00:00", 12, *([2] * 10)],
        [2032, "2012-01-01T00:00:00", 20, *([3] * 10)],
        [2032, "2012-01-01T01:00:00", 22, *([4] * 10)],
    ]
    csv_text = ",".join(columns) + "\n" + "\n".join(",".join(map(str, row)) for row in rows) + "\n"

    system = run_parser_with_load_csv(
        tmp_path,
        reeds_run_path,
        csv_text=csv_text,
        solve_year=[2030, 2032],
    )

    demands = sorted(system.get_components(ReEDSDemand), key=lambda demand: demand.solve_year or 0)
    p1_demands = [demand for demand in demands if demand.region.name == "p1"]
    assert [(demand.name, demand.max_active_power) for demand in p1_demands] == [
        ("p1_load_2030", 12.0),
        ("p1_load_2032", 22.0),
    ]
    for demand, expected_values in zip(p1_demands, ([10.0, 12.0], [20.0, 22.0]), strict=True):
        matching_series = system.list_time_series(
            demand,
            name="max_active_power",
            solve_year=demand.solve_year,
            weather_year=2012,
        )
        assert len(matching_series) == 1
        series = matching_series[0]
        assert isinstance(series, SingleTimeSeries)
        assert series.data.tolist() == expected_values


def test_public_parser_rejects_missing_weather_year_load_profiles(
    reeds_run_path: Path, tmp_path: Path
) -> None:
    columns = ["year", "datetime", *(f"p{index}" for index in range(1, 12))]
    csv_text = ",".join(columns) + "\n"
    csv_text += "2032,2012-01-01T00:00:00," + ",".join("1" for _ in range(11)) + "\n"
    csv_text += "2032,2012-01-01T01:00:00," + ",".join("2" for _ in range(11)) + "\n"

    with pytest.raises(PluginError, match="Every requested solve-year/weather-year pair") as captured:
        run_parser_with_load_csv(
            tmp_path,
            reeds_run_path,
            csv_text=csv_text,
            weather_year=[2012, 2050],
        )

    assert isinstance(captured.value.__cause__, ReaderError)
    assert isinstance(captured.value.__cause__.__cause__, ValueError)


def test_public_parser_rejects_missing_solve_year_load_profiles(reeds_run_path: Path, tmp_path: Path) -> None:
    columns = ["year", "datetime", *(f"p{index}" for index in range(1, 12))]
    csv_text = ",".join(columns) + "\n2030,2012-01-01T00:00:00," + ",".join("1" for _ in range(11)) + "\n"

    with pytest.raises(PluginError, match="Every requested solve-year/weather-year pair") as captured:
        run_parser_with_load_csv(tmp_path, reeds_run_path, csv_text=csv_text)

    assert isinstance(captured.value.__cause__, ReaderError)
    assert isinstance(captured.value.__cause__.__cause__, ValueError)


def test_public_parser_rejects_present_empty_load_profiles(reeds_run_path: Path, tmp_path: Path) -> None:
    columns = ["year", "datetime", *(f"p{index}" for index in range(1, 12))]
    csv_text = ",".join(columns) + "\n"

    with pytest.raises(PluginError, match="Every requested solve-year/weather-year pair") as captured:
        run_parser_with_load_csv(tmp_path, reeds_run_path, csv_text=csv_text)

    assert isinstance(captured.value.__cause__, ReaderError)
    assert isinstance(captured.value.__cause__.__cause__, ValueError)


def test_public_parser_rejects_load_profiles_without_region_columns(
    reeds_run_path: Path, tmp_path: Path
) -> None:
    csv_text = "year,datetime\n2032,2012-01-01T00:00:00\n"

    with pytest.raises(PluginError, match="unpivot requires at least one value column"):
        run_parser_with_load_csv(tmp_path, reeds_run_path, csv_text=csv_text)


@pytest.mark.parametrize(
    ("columns", "rows", "message"),
    [
        (
            [*(f"p{index}" for index in range(1, 12))],
            [
                ["2032", "2012-01-01T00:00:00", *(["", *("10" for _ in range(10))])],
                ["2032", "2012-01-01T01:00:00", *(["", *("11" for _ in range(10))])],
            ],
            "Load profiles must contain a non-null value for each region and solve year",
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
