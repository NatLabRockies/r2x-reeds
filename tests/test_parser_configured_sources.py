"""Public parser regressions for configuration-owned input and field overrides."""

from __future__ import annotations

import copy
import json
import shutil
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import polars as pl
import pytest

from r2x_core import (
    DataFile,
    DataReader,
    DataStore,
    PluginContext,
    PluginError,
    SourceAvailability,
    System,
    TableMappingRecord,
    TabularSource,
    assemble_tables,
)
from r2x_core.exceptions import ReaderError
from r2x_core.polars_adapter import PolarsTabularBackend
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


def assemble_generator_category_tables(
    capacity: pl.DataFrame,
    subsets: pl.DataFrame,
    *,
    overrides: list[GeneratorClassificationOverride] | None = None,
    excluded_technologies: list[str] | None = None,
) -> Mapping[str, TabularSource]:
    """Execute configured generator policy tables through the public assembler."""
    config_path = ReEDSConfig.package_config_path()
    capacity_schema = {
        "region": ("p1", pl.String),
        "vintage": ("init-1", pl.String),
        "year": (2032, pl.Int64),
        "capacity": (1.0, pl.Float64),
        "fuel_type": (None, pl.String),
    }
    capacity_frame = capacity.with_columns(
        [
            pl.lit(value, dtype=dtype).alias(name)
            for name, (value, dtype) in capacity_schema.items()
            if name not in capacity.columns
        ]
    )
    return assemble_tables(
        {
            "generator_capacity_selected": TabularSource(capacity_frame.lazy(), PolarsTabularBackend()),
            "fom_technology_subsets": TabularSource(subsets.lazy(), PolarsTabularBackend()),
            "requested_solve_year_rows": TabularSource(
                pl.DataFrame({"solve_year": [2032]}, schema={"solve_year": pl.Int64}).lazy(),
                PolarsTabularBackend(),
            ),
        },
        mapping_path=config_path / "table_mapping.json",
        backend=PolarsTabularBackend(),
        placeholders={
            "generator_classification_override_rows": [
                override.model_dump(mode="json") for override in overrides or []
            ],
            "excluded_technology_rows": [
                {"technology_key": technology.casefold(), "excluded": True}
                for technology in excluded_technologies or []
            ],
        },
        table_names=[
            "generator_category_by_technology",
            "generator_category_memberships",
            "generator_category_hydro_flags",
        ],
    )


def validate_generator_category_hydro(tables: Mapping[str, TabularSource]) -> None:
    """Run configured hydro validation against assembled category flags."""
    records = load_records(ReEDSConfig.package_config_path() / "file_mapping.json")
    validation = next(record for record in records if record["name"] == "generator_category_hydro_validation")
    DataReader().read_data_files(
        [DataFile.model_validate(validation)],
        folder_path=Path.cwd(),
        initial_sources={"generator_category_hydro_flags": tables["generator_category_hydro_flags"]},
    )


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


@pytest.mark.parametrize(
    ("source_format", "physical_value_column"),
    [
        pytest.param("hdf5", "Value", id="hdf5-uppercase-value"),
        pytest.param("csv", "value", id="csv-lowercase-value"),
    ],
)
def test_generator_heat_rate_table_accepts_hdf_and_csv_value_casing(
    tmp_path: Path, source_format: str, physical_value_column: str
) -> None:
    """Normalize both supported native value spellings before table assembly."""
    config_path = ReEDSConfig.package_config_path()
    file_records = load_records(config_path / "file_mapping.json")
    heat_rate = copy.deepcopy(next(record for record in file_records if record["name"] == "heat_rate"))
    solve_years = next(record for record in file_records if record["name"] == "requested_solve_year_rows")
    output_path = tmp_path / "outputs"
    output_path.mkdir()
    if source_format == "hdf5":
        with h5py.File(str(output_path / "outputs.h5"), mode="w") as handle:
            group = handle.create_group("heat_rate")
            group.create_dataset(
                "columns", data=np.asarray(["i", "v", "r", "t", physical_value_column], dtype="S")
            )
            group.create_dataset("i", data=np.asarray(["Gas-CC"], dtype="S"))
            group.create_dataset("v", data=np.asarray(["init-1"], dtype="S"))
            group.create_dataset("r", data=np.asarray(["p1"], dtype="S"))
            group.create_dataset("t", data=np.asarray([2032], dtype=np.int64))
            group.create_dataset(physical_value_column, data=np.asarray([12.5], dtype=np.float64))
    else:
        heat_rate.update(
            relative_fpath="outputs/heat-rate.csv",
            reader={"format": "csv"},
        )
        (output_path / "heat-rate.csv").write_text(
            "i,v,r,t,value\nGas-CC,init-1,p1,2032,12.5\n", encoding="utf-8"
        )

    table_records = load_records(config_path / "table_mapping.json")
    table_by_name = {record["name"]: record for record in table_records}
    heat_table = copy.deepcopy(table_by_name["generator_heat_rate"])
    selector = heat_table["operations"][0]
    fallback_name = selector["sources"][-1]
    table_mapping_path = tmp_path / "table_mapping.json"
    write_records(
        table_mapping_path,
        [
            copy.deepcopy(table_by_name[fallback_name]),
            copy.deepcopy(table_by_name["generator_selected_solve_years"]),
            heat_table,
        ],
    )

    sources = DataReader().read_and_assemble_sources(
        [DataFile.model_validate(heat_rate), DataFile.model_validate(solve_years)],
        folder_path=tmp_path,
        mapping_path=table_mapping_path,
        backend=PolarsTabularBackend(),
        placeholders={"solve_year_rows": [{"solve_year": 2032}]},
    )

    assert "value" in sources["heat_rate"].fields()
    assert "Value" not in sources["heat_rate"].fields()
    assert list(sources["generator_heat_rate"].iter_rows()) == [
        {"technology": "gas-cc", "vintage": "init-1", "region": "p1", "year": 2032, "heat_rate": 12.5}
    ]


def test_category_mapping_uses_unicode_casefold_for_technology_patterns() -> None:
    """Match German sharp-s by casefold without equating dotless and dotted i."""
    capacity = pl.DataFrame({"technology": ["straße", "\u0131sparta"]}, schema={"technology": pl.String})
    subsets = pl.DataFrame(
        {"technology": ["STRASSE", "isparta"], "fossil": [True, True]},
        schema={"technology": pl.String, "fossil": pl.Boolean},
    )

    tables = assemble_generator_category_tables(capacity, subsets)

    categories = {
        row["technology"]: row["category"] for row in tables["generator_category_by_technology"].iter_rows()
    }
    assert categories == {"straße": "thermal", "\u0131sparta": None}


def test_table_mapping_preserves_boolean_and_text_category_membership_semantics() -> None:
    """Use compact declarative tables for bool true and case-insensitive text yes only."""
    technologies = ["GAS-CC", "WIND-2", "TEXT-TRUE", "NULL-FLAG", "FALSE-FLAG"]
    capacity = pl.DataFrame({"technology": technologies}, schema={"technology": pl.String})
    subsets = pl.DataFrame(
        {
            "technology": ["gas-cc", "wind-1*wind-10", "text-true", "null-flag", "false-flag"],
            "fossil": [True, False, False, False, False],
            "wind": [None, "YeS", "true", None, "false"],
        },
        schema={"technology": pl.String, "fossil": pl.Boolean, "wind": pl.String},
    )

    tables = assemble_generator_category_tables(capacity, subsets)

    categories = {
        row["technology"]: (row["category"], row["parser_supported"])
        for row in tables["generator_category_by_technology"].iter_rows()
    }
    memberships = {
        (row["technology"], row["category"]) for row in tables["generator_category_memberships"].iter_rows()
    }
    assert categories == {
        "GAS-CC": ("thermal", True),
        "WIND-2": ("wind", True),
        "TEXT-TRUE": (None, False),
        "NULL-FLAG": (None, False),
        "FALSE-FLAG": (None, False),
    }
    assert memberships == {
        ("GAS-CC", "fossil"),
        ("GAS-CC", "thermal"),
        ("WIND-2", "wind"),
    }


def test_category_mapping_distinguishes_bool_yes_text_true_null_and_false_flags() -> None:
    """Use configured tables for mixed-type flags with native membership semantics."""
    technologies = ["GAS-CC", "WIND-2", "TEXT-TRUE", "NULL-FLAG", "FALSE-FLAG"]
    capacity = pl.DataFrame({"technology": technologies}, schema={"technology": pl.String})
    subsets = pl.DataFrame(
        {
            "technology": ["gas-cc", "wind-1*wind-10", "text-true", "null-flag", "false-flag"],
            "fossil": [True, False, False, False, False],
            "wind": [None, "YeS", "true", None, "false"],
            "hydro_d": ["no"] * len(technologies),
            "hydro_nd": ["no"] * len(technologies),
        },
        schema={
            "technology": pl.String,
            "fossil": pl.Boolean,
            "wind": pl.String,
            "hydro_d": pl.String,
            "hydro_nd": pl.String,
        },
    )

    sources = assemble_generator_category_tables(capacity, subsets)

    categories = {
        row["technology"]: (row["component_family"], row["category"], row["parser_supported"])
        for row in sources["generator_category_by_technology"].iter_rows()
    }
    memberships = {
        (row["technology"], row["category"]) for row in sources["generator_category_memberships"].iter_rows()
    }
    assert categories == {
        "GAS-CC": ("thermal", "thermal", True),
        "WIND-2": ("variable", "wind", True),
        "TEXT-TRUE": (None, None, False),
        "NULL-FLAG": (None, None, False),
        "FALSE-FLAG": (None, None, False),
    }
    assert memberships == {
        ("GAS-CC", "fossil"),
        ("GAS-CC", "thermal"),
        ("WIND-2", "wind"),
    }


@pytest.mark.parametrize(
    ("dispatchable_flag", "nondispatchable_flag"),
    [
        pytest.param(True, True, id="boolean-boolean"),
        pytest.param(True, "yes", id="boolean-string"),
    ],
)
def test_category_mapping_rejects_conflicting_hydro_membership_types(
    dispatchable_flag: bool,
    nondispatchable_flag: bool | str,
) -> None:
    """Reject contradictory hydro membership regardless of each native flag dtype."""
    nondispatchable_dtype = pl.Boolean if isinstance(nondispatchable_flag, bool) else pl.String
    capacity = pl.DataFrame({"technology": ["hydro-conflict"]}, schema={"technology": pl.String})
    subsets = pl.DataFrame(
        {
            "technology": ["hydro-conflict"],
            "hydro": ["yes"],
            "hydro_d": [dispatchable_flag],
            "hydro_nd": [nondispatchable_flag],
        },
        schema={
            "technology": pl.String,
            "hydro": pl.String,
            "hydro_d": pl.Boolean,
            "hydro_nd": nondispatchable_dtype,
        },
    )
    tables = assemble_generator_category_tables(capacity, subsets)

    with pytest.raises(ReaderError, match="both dispatchable and nondispatchable hydro"):
        validate_generator_category_hydro(tables)


@pytest.mark.parametrize(
    ("dispatchable_flag", "nondispatchable_flag", "expected_dispatchable"),
    [
        pytest.param(True, False, True, id="boolean-dispatchable"),
        pytest.param(False, True, False, id="boolean-nondispatchable"),
        pytest.param("yes", "no", True, id="text-yes"),
        pytest.param("true", "false", False, id="text-true-is-not-yes"),
    ],
)
def test_category_mapping_preserves_single_hydro_flag_memberships(
    dispatchable_flag: bool | str,
    nondispatchable_flag: bool | str,
    expected_dispatchable: bool,
) -> None:
    """Treat boolean true and string yes as membership, but not string true."""
    dispatchable_dtype = pl.Boolean if isinstance(dispatchable_flag, bool) else pl.String
    nondispatchable_dtype = pl.Boolean if isinstance(nondispatchable_flag, bool) else pl.String
    capacity = pl.DataFrame({"technology": ["hydro-single"]}, schema={"technology": pl.String})
    subsets = pl.DataFrame(
        {
            "technology": ["hydro-single"],
            "hydro": ["yes"],
            "hydro_d": [dispatchable_flag],
            "hydro_nd": [nondispatchable_flag],
        },
        schema={
            "technology": pl.String,
            "hydro": pl.String,
            "hydro_d": dispatchable_dtype,
            "hydro_nd": nondispatchable_dtype,
        },
    )
    sources = assemble_generator_category_tables(capacity, subsets)

    row = next(iter(sources["generator_category_by_technology"].iter_rows()))
    validate_generator_category_hydro(sources)
    assert row["category"] == "hydro"
    assert row["is_dispatchable"] is expected_dispatchable


def test_generator_and_hydro_outputs_are_declared_in_table_mapping() -> None:
    """Keep parser-facing generator/profile assembly in the flat public mapping."""
    config_path = ReEDSConfig.package_config_path()
    file_names = {record["name"] for record in load_records(config_path / "file_mapping.json")}
    table_names = {record["name"] for record in load_records(config_path / "table_mapping.json")}
    migrated = {
        "generator_rows",
        "generator_thermal_rows",
        "generator_variable_rows",
        "generator_hydro_rows",
        "generator_storage_rows",
        "generator_import_rows",
        "generator_variable_aggregate_rows",
        "generator_reserve_membership",
        "generator_excluded_reserve_pairs",
        "hydro_profile_monthly",
        "hydro_budget_rows",
        "hydro_nondispatchable_rows",
        "hydro_adjustment_profile_monthly",
    }

    assert not file_names.intersection(migrated)
    assert migrated <= table_names
    assert "hydro_hour_month_axis" in table_names
    assert "hydro_weather_calendar" in table_names
    assert not {"hydro_hour_month_axis", "hydro_weather_calendar"} & file_names


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
    write_records(mapping_path, mapping)

    table_mapping_path = config_path / "table_mapping.json"
    table_mapping = load_records(table_mapping_path)
    generator_thermal_rows = next(
        record for record in table_mapping if record["name"] == "generator_thermal_rows"
    )
    generator_thermal_rows["columns"].update({"maxage_years": "max_age", "mapped_vom": "vom_cost"})
    write_records(table_mapping_path, table_mapping)

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
    with h5py.File(str(path), "w") as handle:
        handle.create_dataset("columns", data=np.asarray(columns, dtype="S32"))
        handle.create_dataset("data", data=values)
        handle.create_dataset("index_0", data=timestamps)
        handle.create_dataset("index_names", data=np.asarray(["datetime"], dtype="S8"))


def test_load_owner_names_are_assembled_from_native_inputs(reeds_run_path: Path) -> None:
    config_path = ReEDSConfig.package_config_path()
    records = load_records(config_path / "file_mapping.json")
    data_files = [
        DataFile.model_validate(record)
        for record in records
        if record["name"] in {"hierarchy", "requested_solve_year_rows"}
    ]

    sources = DataReader().read_data_files(
        data_files,
        folder_path=reeds_run_path,
        placeholders={"solve_year_rows": [{"solve_year": 2030}, {"solve_year": 2032}]},
    )
    tables = assemble_tables(
        sources,
        mapping_path=config_path / "table_mapping.json",
        backend=PolarsTabularBackend(),
        table_names=["load_owner_names"],
    )

    owner_names = {
        (row["region"], row["solve_year"]): row["owner_name"]
        for row in tables["load_owner_names"].iter_rows()
    }
    assert owner_names[("p1", 2030)] == "p1_load_2030"
    assert owner_names[("p1", 2032)] == "p1_load_2032"


def test_renewable_profiles_are_assembled_from_real_hdf5_headers(tmp_path: Path) -> None:
    """Unpivot the prepared native profile through the production table mapping."""
    run_path = tmp_path / "run"
    inputs = run_path / "inputs_case"
    inputs.mkdir(parents=True)
    write_renewable_profile(
        inputs / "recf.h5",
        columns=["wind-ons|p2", "solar|p1"],
        values=np.asarray([[0.1, 0.2], [0.3, 0.4], [0.5, 0.6], [0.7, 0.8]], dtype=np.float32),
    )
    with h5py.File(str(inputs / "recf.h5"), "r+") as handle:
        handle["index_0"][3] = b"2013-01-01T00:00:00"
    config_path = ReEDSConfig.package_config_path()
    file_records = load_records(config_path / "file_mapping.json")
    data_files = [
        DataFile.model_validate(record)
        for record in file_records
        if record["name"] in {"renewable_profiles_wide", "weather_hour_axis"}
    ]
    sources = DataReader().read_data_files(
        data_files,
        folder_path=run_path,
        placeholders={"primary_weather_year": 2012},
    )
    profile_source = sources["renewable_profiles_wide"]
    assert isinstance(profile_source, TabularSource)
    profile_years: set[int] = set()
    for row in profile_source.iter_rows():
        timestamp = row["datetime"]
        assert isinstance(timestamp, datetime)
        profile_years.add(timestamp.year)
    assert profile_years == {2012, 2013}
    table_records = load_records(config_path / "table_mapping.json")
    mapping = [record for record in table_records if record["name"] == "renewable_profiles"]
    assert len(mapping) == 1, "The parser-ready renewable profile table must be configured"
    assert mapping[0]["source"] == "renewable_profiles_wide"
    assert mapping[0]["operations"][:3] == [
        {
            "operation": "datetime_part",
            "column": "datetime",
            "part": "year",
            "output": "profile_weather_year",
        },
        {
            "operation": "filter",
            "column": "profile_weather_year",
            "comparison": "equals",
            "value": "{primary_weather_year}",
        },
        {"operation": "head", "n": 8760},
    ]
    mapping_path = tmp_path / "renewable-table-mapping.json"
    write_records(mapping_path, mapping)

    tables = assemble_tables(
        sources,
        mapping_path=mapping_path,
        backend=PolarsTabularBackend(),
        placeholders={"primary_weather_year": 2012},
    )

    profiles = tables["renewable_profiles"]
    rows = list(profiles.iter_rows())
    assert profiles.fields() == ["capacity_factor", "datetime", "region", "technology"]
    assert [(row["datetime"], row["region"], row["technology"]) for row in rows] == [
        (datetime(2012, 1, 1, hour), region, technology)
        for region, technology in (("p1", "solar"), ("p2", "wind-ons"))
        for hour in range(3)
    ]
    np.testing.assert_allclose([row["capacity_factor"] for row in rows], [0.2, 0.4, 0.6, 0.1, 0.3, 0.5])


def test_renewable_profile_keeps_sparse_timestamp_at_year_end(tmp_path: Path) -> None:
    """Select profile rows by timestamp year, not a synthesized hourly axis."""
    run_path = tmp_path / "run"
    inputs = run_path / "inputs_case"
    inputs.mkdir(parents=True)
    profile_path = inputs / "recf.h5"
    write_renewable_profile(
        profile_path,
        columns=["wind-ons|p2"],
        values=np.asarray([[0.75]], dtype=np.float32),
    )
    with h5py.File(str(profile_path), "r+") as handle:
        handle["index_0"][0] = b"2012-12-31T00:00:00"

    config_path = ReEDSConfig.package_config_path()
    file_records = load_records(config_path / "file_mapping.json")
    data_files = [
        DataFile.model_validate(record)
        for record in file_records
        if record["name"] in {"renewable_profiles_wide", "weather_hour_axis"}
    ]
    sources = DataReader().read_data_files(
        data_files,
        folder_path=run_path,
        placeholders={"primary_weather_year": 2012},
    )

    table = assemble_tables(
        sources,
        mapping_path=config_path / "table_mapping.json",
        backend=PolarsTabularBackend(),
        placeholders={"primary_weather_year": 2012},
        table_names=["renewable_profiles"],
    )["renewable_profiles"]

    assert list(table.iter_rows()) == [
        {
            "capacity_factor": pytest.approx(0.75),
            "datetime": datetime(2012, 12, 31),
            "region": "p2",
            "technology": "wind-ons",
        }
    ]


def test_fom_cost_table_filters_native_rows_for_all_requested_years(tmp_path: Path) -> None:
    """Select FOM values from native rows with generic table mapping operations."""
    config_path = ReEDSConfig.package_config_path()
    file_records = load_records(config_path / "file_mapping.json")
    cost_record = next(record for record in file_records if record["name"] == "cost_fom")
    input_dir = tmp_path / "inputs_case"
    input_dir.mkdir()
    (input_dir / "plantcharout.csv").write_text(
        "*i,t,variable,value\n"
        "Gas-CC,2032,FOM,12.5\n"
        "Gas-CC,2032,VOM,3\n"
        "gas-cc,2040,fom,15\n"
        "COAL,2040,FOM,20\n"
        "Gas-CC,2035,FOM,99\n",
        encoding="utf-8",
    )
    data_file = DataFile.model_validate({**cost_record, "relative_fpath": "inputs_case/plantcharout.csv"})
    solve_year_record = next(
        record for record in file_records if record["name"] == "requested_solve_year_rows"
    )
    sources = DataReader().read_data_files(
        [data_file, DataFile.model_validate(solve_year_record)],
        folder_path=tmp_path,
        placeholders={"solve_year_rows": [{"solve_year": 2032}, {"solve_year": 2040}]},
    )

    tables = assemble_tables(
        sources,
        mapping_path=config_path / "table_mapping.json",
        backend=PolarsTabularBackend(),
        placeholders={"solve_year_rows": [{"solve_year": 2032}, {"solve_year": 2040}]},
        table_names=["cost_fom_selected"],
    )

    assert list(tables["cost_fom_selected"].iter_rows()) == [
        {"fom_cost": 12.5, "technology": "gas-cc", "year": 2032},
        {"fom_cost": 15.0, "technology": "gas-cc", "year": 2040},
        {"fom_cost": 20.0, "technology": "coal", "year": 2040},
    ]
    assert tables["cost_fom_selected"].fields() == ["fom_cost", "technology", "year"]


def test_hydrogen_hdf5_sources_select_all_requested_years_in_table_mapping() -> None:
    """Normalize and filter the real hydrogen HDF5 groups through configured assembly."""
    config_path = ReEDSConfig.package_config_path()
    file_records = load_records(config_path / "file_mapping.json")
    output_names = [
        "hydrogen_production_capacity",
        "hydrogen_production_annual_load",
        "hydrogen_production_load",
    ]
    input_names = [f"{name}_input" for name in output_names]
    selected_records = [
        record for record in file_records if record["name"] in {*input_names, "requested_solve_year_rows"}
    ]
    requested_years = [2029, 2032]
    placeholders = {
        "solve_year": requested_years,
        "solve_year_rows": [{"solve_year": year} for year in requested_years],
    }
    sources = DataReader().read_data_files(
        [DataFile.model_validate(record) for record in selected_records],
        folder_path=Path(__file__).parent / "data" / "test_Upgrader",
        placeholders=placeholders,
    )

    tables = assemble_tables(
        sources,
        mapping_path=config_path / "table_mapping.json",
        backend=PolarsTabularBackend(),
        placeholders=placeholders,
        table_names=output_names,
    )

    capacity_rows = list(tables["hydrogen_production_capacity"].iter_rows())
    annual_rows = list(tables["hydrogen_production_annual_load"].iter_rows())
    hourly_rows = list(tables["hydrogen_production_load"].iter_rows())
    assert len(capacity_rows) == 348
    assert {row["year"] for row in capacity_rows} == set(requested_years)
    assert {
        (row["technology"], row["region"], row["year"], row["capacity"])
        for row in capacity_rows
        if row["technology"] == "battery_li" and row["region"] == "p1"
    } == {
        ("battery_li", "p1", 2029, 32.20000076293945),
        ("battery_li", "p1", 2032, 31.200000762939453),
    }
    assert annual_rows == [
        {"technology": "electrolyzer", "region": "p10", "year": 2029, "value": 997520.3125},
        {"technology": "electrolyzer", "region": "p10", "year": 2032, "value": 997520.3125},
    ]
    assert len(hourly_rows) == 160
    assert {row["year"] for row in hourly_rows} == set(requested_years)
    assert {
        (row["technology"], row["region"], row["year"], row["hour_period"], row["value"])
        for row in hourly_rows
    } >= {
        ("electrolyzer", "p10", 2029, "y2012d012h003", 113.87217712402344),
        ("electrolyzer", "p10", 2032, "y2012d012h003", 113.87217712402344),
    }


def test_missing_optional_hydrogen_hdf5_groups_remain_absent_after_assembly(tmp_path: Path) -> None:
    """Keep schema-bearing absent HDF5 groups distinct from present-empty tables."""
    config_path = ReEDSConfig.package_config_path()
    file_records = load_records(config_path / "file_mapping.json")
    input_names = {
        "hydrogen_production_capacity_input",
        "hydrogen_production_annual_load_input",
        "hydrogen_production_load_input",
        "requested_solve_year_rows",
    }
    data_files = [DataFile.model_validate(record) for record in file_records if record["name"] in input_names]
    output_names = [
        "hydrogen_production_capacity",
        "hydrogen_production_annual_load",
        "hydrogen_production_load",
    ]
    input_dir = tmp_path / "outputs"
    input_dir.mkdir()
    with h5py.File(str(input_dir / "outputs.h5"), "w"):
        pass
    placeholders = {"solve_year_rows": [{"solve_year": 2032}]}
    sources = DataReader().read_data_files(data_files, folder_path=tmp_path, placeholders=placeholders)

    tables = assemble_tables(
        sources,
        mapping_path=config_path / "table_mapping.json",
        backend=PolarsTabularBackend(),
        placeholders=placeholders,
        table_names=output_names,
    )

    for name in output_names:
        table = tables[name]
        assert table.availability is SourceAvailability.ABSENT
        assert table.is_empty()
        assert table.absent_inputs


def test_transmission_hdf_sources_normalize_native_value_case_and_assemble_names() -> None:
    """Decode uppercase HDF Value fields, then assemble transmission names in table mapping."""
    config_path = ReEDSConfig.package_config_path()
    records = load_records(config_path / "file_mapping.json")
    transmission_records = [
        DataFile.model_validate(record)
        for name in ("transmission_capacity", "transmission_losses", "requested_solve_year_rows")
        for record in records
        if record["name"] == name
    ]
    sources = DataReader().read_data_files(
        transmission_records,
        folder_path=Path(__file__).parent / "data" / "test_Upgrader",
        placeholders={"solve_year_rows": [{"solve_year": 2010}]},
    )

    capacity_source = sources["transmission_capacity"]
    losses_source = sources["transmission_losses"]
    assert isinstance(capacity_source, TabularSource)
    assert isinstance(losses_source, TabularSource)
    capacity = next(
        row
        for row in capacity_source.iter_rows()
        if row["from_region"] == "p1" and row["to_region"] == "p2" and row["year"] == 2010
    )
    losses = next(
        row for row in losses_source.iter_rows() if row["from_region"] == "p1" and row["to_region"] == "p2"
    )
    selected = assemble_tables(
        sources,
        mapping_path=config_path / "table_mapping.json",
        backend=PolarsTabularBackend(),
        table_names=["transmission_capacity_selected"],
    )["transmission_capacity_selected"]
    selected_row = next(iter(selected.iter_rows()))

    assert capacity["trtype"] == "ac"
    assert capacity["capacity"] == pytest.approx(8287.031)
    assert not {"region_a", "region_b", "interface_name", "line_name"} & set(capacity)
    assert losses["trtype"] == "ac"
    assert losses["losses"] == pytest.approx(0.013)
    assert selected_row["line_name"] == "p1_p2_ac_2010"
    assert selected_row["interface_name"] == "p1||p2"


@pytest.mark.parametrize("groups_present", [False, True], ids=["absent-groups", "present-empty-groups"])
def test_transmission_hdf_optional_sources_keep_absence_distinct_from_empty(
    tmp_path: Path, groups_present: bool
) -> None:
    """Typed fallback tables handle absent HDF groups without erasing present-empty inputs."""
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    with h5py.File(str(output_dir / "outputs.h5"), mode="w") as handle:
        if groups_present:
            definitions = {
                "tran_cap_energy": ["r", "rr", "trtype", "t", "Value"],
                "tranloss": ["r", "rr", "trtype", "Value"],
            }
            for group_name, columns in definitions.items():
                group = handle.create_group(group_name)
                group.create_dataset("columns", data=np.asarray(columns, dtype="S"))
                for column in columns:
                    if column == "t":
                        values = np.asarray([], dtype=np.int64)
                    elif column == "Value":
                        values = np.asarray([], dtype=np.float32)
                    else:
                        values = np.asarray([], dtype="S1")
                    group.create_dataset(column, data=values)

    config_path = ReEDSConfig.package_config_path()
    file_records = load_records(config_path / "file_mapping.json")
    file_names = {"requested_solve_year_rows", "transmission_capacity", "transmission_losses"}
    data_files = [DataFile.model_validate(record) for record in file_records if record["name"] in file_names]
    mapping_records = load_records(config_path / "table_mapping.json")
    table_names = {
        "requested_solve_year_keys",
        "transmission_capacity_empty",
        "transmission_capacity_selected",
        "transmission_losses_empty",
        "transmission_losses_selected",
    }
    records = [record for record in mapping_records if record["name"] in table_names]
    sources = DataReader().read_and_assemble_records(
        data_files,
        [TableMappingRecord.model_validate(record) for record in records],
        folder_path=tmp_path,
        backend=PolarsTabularBackend(),
        placeholders={"solve_year_rows": [{"solve_year": 2032}]},
    )

    assert ("transmission_capacity" in sources) is groups_present
    assert ("transmission_losses" in sources) is groups_present
    if groups_present:
        capacity_source = sources["transmission_capacity"]
        losses_source = sources["transmission_losses"]
        assert isinstance(capacity_source, TabularSource)
        assert isinstance(losses_source, TabularSource)
        assert capacity_source.availability is SourceAvailability.PRESENT
        assert losses_source.availability is SourceAvailability.PRESENT
        assert capacity_source.is_empty()
        assert losses_source.is_empty()
    else:
        assert "transmission_capacity_empty" in sources
        assert "transmission_losses_empty" in sources
    for name in ("transmission_capacity_selected", "transmission_losses_selected"):
        table = sources[name]
        assert isinstance(table, TabularSource)
        assert table.availability is SourceAvailability.PRESENT
        assert table.is_empty()


@pytest.mark.parametrize(
    ("name", "group_name", "columns"),
    [
        ("transmission_capacity", "tran_cap_energy", ["r", "rr", "trtype", "t"]),
        ("transmission_losses", "tranloss", ["r", "rr", "trtype"]),
    ],
    ids=["capacity-missing-value", "losses-missing-value"],
)
def test_transmission_hdf_malformed_present_group_is_not_a_fallback(
    tmp_path: Path, name: str, group_name: str, columns: list[str]
) -> None:
    """An existing HDF group without its required value field raises during decoding."""
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    with h5py.File(str(output_dir / "outputs.h5"), mode="w") as handle:
        group = handle.create_group(group_name)
        group.create_dataset("columns", data=np.asarray(columns, dtype="S"))
        for column in columns:
            values = np.asarray([2032], dtype=np.int64) if column == "t" else np.asarray([b"p1"], dtype="S3")
            group.create_dataset(column, data=values)

    config_path = ReEDSConfig.package_config_path()
    file_record = next(
        record for record in load_records(config_path / "file_mapping.json") if record["name"] == name
    )

    with pytest.raises(ReaderError):
        DataReader().read_data_files(
            [DataFile.model_validate(file_record)],
            folder_path=tmp_path,
        )


def test_transmission_capacity_year_selection_and_naming_run_in_table_mapping(tmp_path: Path) -> None:
    """Keep all native rows, then select years and derive line names in table mapping."""
    config_path = ReEDSConfig.package_config_path()
    file_records = load_records(config_path / "file_mapping.json")
    capacity_record = next(record for record in file_records if record["name"] == "transmission_capacity")
    capacity_record["relative_fpath"] = "inputs_case/transmission-capacity.csv"
    capacity_record["reader"] = {"format": "csv"}
    losses_record = next(record for record in file_records if record["name"] == "transmission_losses")
    losses_record["relative_fpath"] = "inputs_case/transmission-losses.csv"
    losses_record["reader"] = {"format": "csv"}
    solve_year_record = next(
        record for record in file_records if record["name"] == "requested_solve_year_rows"
    )
    input_dir = tmp_path / "inputs_case"
    input_dir.mkdir()
    (input_dir / "transmission-capacity.csv").write_text(
        "r,rr,trtype,t,value\np1,p2,AC,2032,100\np2,p1,AC,2040,80\np1,p2,DC,2044,40\n",
        encoding="utf-8",
    )
    (input_dir / "transmission-losses.csv").write_text(
        "r,rr,trtype,value\np1,p2,AC,0.013\n",
        encoding="utf-8",
    )
    placeholders = {
        "solve_year": [2032, 2040],
        "solve_year_rows": [{"solve_year": 2032}, {"solve_year": 2040}],
    }
    sources = DataReader().read_data_files(
        [
            DataFile.model_validate(capacity_record),
            DataFile.model_validate(losses_record),
            DataFile.model_validate(solve_year_record),
        ],
        folder_path=tmp_path,
        placeholders=placeholders,
    )

    capacity_source = sources["transmission_capacity"]
    losses_source = sources["transmission_losses"]
    assert isinstance(capacity_source, TabularSource)
    assert isinstance(losses_source, TabularSource)
    capacity_rows = list(capacity_source.iter_rows())
    assert {row["year"] for row in capacity_rows} == {2032, 2040, 2044}
    assert {row["trtype"] for row in capacity_rows} == {"ac", "dc"}
    assert not {"region_a", "region_b", "interface_name", "line_name"} & set(capacity_rows[0])
    losses_row = next(iter(losses_source.iter_rows()))
    assert losses_row["trtype"] == "ac"
    assert losses_row["losses"] == pytest.approx(0.013)
    selected = assemble_tables(
        sources,
        mapping_path=config_path / "table_mapping.json",
        backend=PolarsTabularBackend(),
        table_names=["transmission_capacity_selected"],
    )["transmission_capacity_selected"]

    assert {(row["line_name"], row["interface_name"], row["capacity"]) for row in selected.iter_rows()} == {
        ("p1_p2_ac_2032", "p1||p2", 100.0),
        ("p1_p2_ac_2040", "p1||p2", 80.0),
    }


def test_hydro_capacity_factors_assemble_all_requested_years_from_real_csv(tmp_path: Path) -> None:
    """Normalize native monthly rows in the file boundary and select years in table mapping."""
    config_path = ReEDSConfig.package_config_path()
    file_records = load_records(config_path / "file_mapping.json")
    hydro_record = next(record for record in file_records if record["name"] == "hydro_cf_input")
    solve_year_record = next(
        record for record in file_records if record["name"] == "requested_solve_year_rows"
    )
    input_dir = tmp_path / "inputs_case"
    input_dir.mkdir()
    (input_dir / "hydcf.csv").write_text(
        "*i,month,r,t,value\nhydED,JAN,p1,2032,0.1\nhydED,FEB,p1,2040,0.2\nhydED,MAR,p1,2044,0.3\n",
        encoding="utf-8",
    )
    sources = DataReader().read_data_files(
        [
            DataFile.model_validate({**hydro_record, "relative_fpath": "inputs_case/hydcf.csv"}),
            DataFile.model_validate(solve_year_record),
        ],
        folder_path=tmp_path,
        placeholders={"solve_year_rows": [{"solve_year": 2032}, {"solve_year": 2040}]},
    )

    table = assemble_tables(
        sources,
        mapping_path=config_path / "table_mapping.json",
        backend=PolarsTabularBackend(),
        table_names=["hydro_cf"],
    )["hydro_cf"]

    assert list(table.iter_rows()) == [
        {"hydro_cf": 0.1, "month": "jan", "region": "p1", "solve_year": 2032, "technology": "hyded"},
        {"hydro_cf": 0.2, "month": "feb", "region": "p1", "solve_year": 2040, "technology": "hyded"},
    ]


@pytest.mark.parametrize(
    ("contents", "availability", "selected_fields", "selected_rows"),
    [
        pytest.param(
            None,
            SourceAvailability.ABSENT,
            ["technology", "region", "month", "capacity_adjustment"],
            [],
            id="absent-uses-typed-fallback",
        ),
        pytest.param(
            "*i,month,r,value\n",
            SourceAvailability.PRESENT,
            ["technology", "region", "month", "capacity_adjustment"],
            [],
            id="present-empty-uses-typed-fallback",
        ),
        pytest.param(
            "*i,month,r,value\nhydED,JAN,p1,0.95\n",
            SourceAvailability.PRESENT,
            ["technology", "month", "region", "capacity_adjustment"],
            [{"technology": "hyded", "month": "jan", "region": "p1", "capacity_adjustment": 0.95}],
            id="present-nonempty-input-wins",
        ),
    ],
)
def test_hydro_adjustment_native_input_preserves_optional_availability(
    tmp_path: Path,
    contents: str | None,
    availability: SourceAvailability,
    selected_fields: list[str],
    selected_rows: list[dict[str, object]],
) -> None:
    """Normalize native hydro adjustment columns without conflating missing and empty input."""
    config_path = ReEDSConfig.package_config_path()
    file_records = load_records(config_path / "file_mapping.json")
    native_record = next(
        record for record in file_records if record["name"] == "hydro_capacity_adjustment_input"
    )
    if contents is not None:
        input_dir = tmp_path / "inputs_case"
        input_dir.mkdir()
        (input_dir / "hydcapadj.csv").write_text(contents, encoding="utf-8")

    table_records = load_records(config_path / "table_mapping.json")
    table_by_name = {record["name"]: record for record in table_records}
    selection = copy.deepcopy(table_by_name["hydro_capacity_adjustment_selected"])
    fallback_name = selection["operations"][0]["fallback"]
    table_mapping_path = tmp_path / "table_mapping.json"
    write_records(table_mapping_path, [copy.deepcopy(table_by_name[fallback_name]), selection])

    sources = DataReader().read_and_assemble_sources(
        [DataFile.model_validate(native_record)],
        folder_path=tmp_path,
        mapping_path=table_mapping_path,
        backend=PolarsTabularBackend(),
    )

    native = sources["hydro_capacity_adjustment_input"]
    assert isinstance(native, TabularSource)
    assert native.availability is availability
    assert native.fields() == ["technology", "month", "region", "capacity_adjustment"]
    if availability is SourceAvailability.ABSENT:
        assert native.absent_inputs == frozenset({"hydro_capacity_adjustment_input"})
    selected_source = sources["hydro_capacity_adjustment_selected"]
    assert isinstance(selected_source, TabularSource)
    assert selected_source.availability is SourceAvailability.PRESENT
    assert selected_source.absent_inputs == frozenset()
    assert selected_source.fields() == selected_fields
    assert list(selected_source.iter_rows()) == selected_rows


def test_hydro_adjustment_month_validation_rejects_invalid_selected_rows(tmp_path: Path) -> None:
    """Retain the hydro adjustment month-abbreviation assertion after native normalization."""
    config_path = ReEDSConfig.package_config_path()
    records = load_records(config_path / "file_mapping.json")
    selected = [
        DataFile.model_validate(record)
        for record in records
        if record["name"] in {"hydro_capacity_adjustment_input", "hydro_capacity_adjustment_month_validation"}
    ]
    table_records = load_records(config_path / "table_mapping.json")
    table_by_name = {record["name"]: record for record in table_records}
    hydro_selection = copy.deepcopy(table_by_name["hydro_capacity_adjustment_selected"])
    fallback_name = hydro_selection["operations"][0]["fallback"]
    table_mapping_path = tmp_path / "table_mapping.json"
    write_records(
        table_mapping_path,
        [copy.deepcopy(table_by_name[fallback_name]), hydro_selection],
    )
    input_dir = tmp_path / "inputs_case"
    input_dir.mkdir()
    (input_dir / "hydcapadj.csv").write_text("*i,month,r,value\nhydED,january,p1,0.95\n", encoding="utf-8")

    with pytest.raises(ReaderError, match="Hydro inputs must use month abbreviations JAN through DEC"):
        DataReader().read_and_assemble_sources(
            selected,
            folder_path=tmp_path,
            mapping_path=table_mapping_path,
            backend=PolarsTabularBackend(),
        )


def test_hydro_month_validation_rejects_invalid_selected_rows(tmp_path: Path) -> None:
    """Retain the hydro month-abbreviation assertion after table assembly."""
    config_path = ReEDSConfig.package_config_path()
    file_records = load_records(config_path / "file_mapping.json")
    records = {
        record["name"]: record
        for record in file_records
        if record["name"] in {"hydro_cf_input", "hydro_cf_month_validation", "requested_solve_year_rows"}
    }
    table_records = load_records(config_path / "table_mapping.json")
    table_mapping_path = tmp_path / "table_mapping.json"
    write_records(
        table_mapping_path, [next(record for record in table_records if record["name"] == "hydro_cf")]
    )
    input_dir = tmp_path / "inputs_case"
    input_dir.mkdir()
    (input_dir / "hydcf.csv").write_text(
        "*i,month,r,t,value\nhydED,january,p1,2032,0.1\n",
        encoding="utf-8",
    )

    with pytest.raises(ReaderError, match="Hydro inputs must use month abbreviations JAN through DEC"):
        DataReader().read_and_assemble_sources(
            [DataFile.model_validate(record) for record in records.values()],
            folder_path=tmp_path,
            mapping_path=table_mapping_path,
            backend=PolarsTabularBackend(),
            placeholders={"solve_year_rows": [{"solve_year": 2032}]},
        )


def test_hydro_month_validation_ignores_unrequested_solve_years(tmp_path: Path) -> None:
    """Preserve filtering before validation for malformed rows outside requested years."""
    config_path = ReEDSConfig.package_config_path()
    file_records = load_records(config_path / "file_mapping.json")
    records = {
        record["name"]: record
        for record in file_records
        if record["name"] in {"hydro_cf_input", "hydro_cf_month_validation", "requested_solve_year_rows"}
    }
    table_records = load_records(config_path / "table_mapping.json")
    table_mapping_path = tmp_path / "table_mapping.json"
    write_records(
        table_mapping_path, [next(record for record in table_records if record["name"] == "hydro_cf")]
    )
    input_dir = tmp_path / "inputs_case"
    input_dir.mkdir()
    (input_dir / "hydcf.csv").write_text(
        "*i,month,r,t,value\nhydED,JAN,p1,2032,0.1\nhydED,january,p1,2040,0.2\n",
        encoding="utf-8",
    )

    sources = DataReader().read_and_assemble_sources(
        [DataFile.model_validate(record) for record in records.values()],
        folder_path=tmp_path,
        mapping_path=table_mapping_path,
        backend=PolarsTabularBackend(),
        placeholders={"solve_year_rows": [{"solve_year": 2032}]},
    )

    assert list(sources["hydro_cf"].iter_rows()) == [
        {"technology": "hyded", "region": "p1", "solve_year": 2032, "month": "jan", "hydro_cf": 0.1}
    ]


def test_cost_hurdle_rate_selection_joins_every_requested_solve_year() -> None:
    """Keep the transmission hurdle-rate table limited to all configured years."""
    config_path = ReEDSConfig.package_config_path()
    file_records = load_records(config_path / "file_mapping.json")
    solve_year_record = next(
        record for record in file_records if record["name"] == "requested_solve_year_rows"
    )
    sources = dict(
        DataReader().read_data_files(
            [DataFile.model_validate(solve_year_record)],
            folder_path=Path.cwd(),
            placeholders={"solve_year_rows": [{"solve_year": 2032}, {"solve_year": 2040}]},
        )
    )
    sources["cost_hurdle_rate"] = TabularSource(
        pl.DataFrame(
            {
                "from_region": ["p1", "p2", "p1"],
                "to_region": ["p2", "p1", "p2"],
                "year": [2032, 2040, 2044],
                "cost_hurdle_rate": [3.0, 4.0, 9.0],
            },
            schema={
                "from_region": pl.String,
                "to_region": pl.String,
                "year": pl.Int64,
                "cost_hurdle_rate": pl.Float64,
            },
        ).lazy(),
        PolarsTabularBackend(),
    )

    table = assemble_tables(
        sources,
        mapping_path=config_path / "table_mapping.json",
        backend=PolarsTabularBackend(),
        table_names=["cost_hurdle_rate_selected"],
    )["cost_hurdle_rate_selected"]

    assert [(row["year"], row["cost_hurdle_rate"]) for row in table.iter_rows()] == [
        (2032, 3.0),
        (2040, 4.0),
    ]


def test_generator_capacity_selection_joins_every_requested_solve_year() -> None:
    """Filter native capacity rows with the full configured solve-year set."""
    config_path = ReEDSConfig.package_config_path()
    file_records = load_records(config_path / "file_mapping.json")
    solve_year_record = next(
        record for record in file_records if record["name"] == "requested_solve_year_rows"
    )
    sources = dict(
        DataReader().read_data_files(
            [DataFile.model_validate(solve_year_record)],
            folder_path=Path.cwd(),
            placeholders={"solve_year_rows": [{"solve_year": 2032}, {"solve_year": 2040}]},
        )
    )
    sources["generator_capacity_selected"] = TabularSource(
        pl.DataFrame(
            {
                "technology": ["gas-cc", "gas-cc", "gas-cc"],
                "region": ["p1", "p1", "p1"],
                "vintage": ["init-1", "init-1", "init-1"],
                "year": [2032, 2040, 2044],
                "capacity": [10.0, 20.0, 40.0],
            },
            schema={
                "technology": pl.String,
                "region": pl.String,
                "vintage": pl.String,
                "year": pl.Int64,
                "capacity": pl.Float64,
            },
        ).lazy(),
        PolarsTabularBackend(),
    )

    tables = assemble_tables(
        sources,
        mapping_path=config_path / "table_mapping.json",
        backend=PolarsTabularBackend(),
        table_names=["generator_capacity_for_solve_year"],
    )

    assert [
        (row["year"], row["capacity"]) for row in tables["generator_capacity_for_solve_year"].iter_rows()
    ] == [
        (2032, 10.0),
        (2040, 20.0),
    ]


def test_emission_rate_rows_normalize_and_select_requested_solve_years() -> None:
    """Normalize native emission values and keep all requested years in the table graph."""
    config_path = ReEDSConfig.package_config_path()
    file_records = load_records(config_path / "file_mapping.json")
    solve_year_record = next(
        record for record in file_records if record["name"] == "requested_solve_year_rows"
    )
    sources = dict(
        DataReader().read_data_files(
            [DataFile.model_validate(solve_year_record)],
            folder_path=Path.cwd(),
            placeholders={"solve_year_rows": [{"solve_year": 2032}, {"solve_year": 2040}]},
        )
    )
    sources["emission_rates"] = TabularSource(
        pl.DataFrame(
            {
                "eall": ["co2e", "unknown", None, "nox"],
                "etype": ["process", "oddsource", None, "upstream"],
                "i": ["gas-cc", "gas-cc", "gas-cc", "other"],
                "r": ["p1", "p1", "p1", "p1"],
                "t": [2032, 2032, 2040, 2044],
                "v": [None, "init-1", "new", "new"],
                "value": [0.1, 0.2, 0.3, 0.4],
            },
            schema={
                "eall": pl.String,
                "etype": pl.String,
                "i": pl.String,
                "r": pl.String,
                "t": pl.Int64,
                "v": pl.String,
                "value": pl.Float64,
            },
        ).lazy(),
        PolarsTabularBackend(),
    )

    tables = assemble_tables(
        sources,
        mapping_path=config_path / "table_mapping.json",
        backend=PolarsTabularBackend(),
        table_names=["emission_rate_rows"],
    )

    expected = [
        {
            "emission_source": "PRECOMBUSTION",
            "emission_type": "CO2E",
            "rate": 0.1,
            "region": "p1",
            "solve_year": 2032,
            "technology": "gas-cc",
            "vintage_key": "__missing_vintage__",
        },
        {
            "emission_source": "oddsource",
            "emission_type": "unknown",
            "rate": 0.2,
            "region": "p1",
            "solve_year": 2032,
            "technology": "gas-cc",
            "vintage_key": "init-1",
        },
        {
            "emission_source": "COMBUSTION",
            "emission_type": None,
            "rate": 0.3,
            "region": "p1",
            "solve_year": 2040,
            "technology": "gas-cc",
            "vintage_key": "new",
        },
    ]
    assert list(tables["emission_rate_rows"].iter_rows()) == expected

    schema = {
        "eall": pl.String,
        "etype": pl.String,
        "i": pl.String,
        "r": pl.String,
        "t": pl.Int64,
        "v": pl.String,
        "value": pl.Float64,
    }
    empty = TabularSource(pl.DataFrame(schema=schema).lazy(), PolarsTabularBackend())
    absent = TabularSource(
        pl.DataFrame(schema=schema).lazy(),
        PolarsTabularBackend(),
        availability=SourceAvailability.ABSENT,
        absent_inputs=frozenset({"emission_rates"}),
    )
    for input_source in (empty, absent):
        input_sources = {**sources, "emission_rates": input_source}
        result = assemble_tables(
            input_sources,
            mapping_path=config_path / "table_mapping.json",
            backend=PolarsTabularBackend(),
            table_names=["emission_rate_rows"],
        )["emission_rate_rows"]
        assert list(result.iter_rows()) == []
        assert result.fields() == [
            "emission_source",
            "emission_type",
            "rate",
            "region",
            "solve_year",
            "technology",
            "vintage_key",
        ]
        assert result.availability is SourceAvailability.PRESENT
        assert result.absent_inputs == frozenset()


def test_hydro_calendar_tables_assemble_from_generated_weather_axis() -> None:
    """Keep generic weather-calendar preparation at the input boundary."""
    config_path = ReEDSConfig.package_config_path()
    file_records = load_records(config_path / "file_mapping.json")
    weather_axis = next(record for record in file_records if record["name"] == "weather_hour_axis")
    sources = DataReader().read_data_files(
        [DataFile.model_validate(weather_axis)],
        folder_path=Path.cwd(),
        placeholders={"primary_weather_year": 2012},
    )

    tables = assemble_tables(
        sources,
        mapping_path=config_path / "table_mapping.json",
        backend=PolarsTabularBackend(),
        table_names=["hydro_hour_month_axis", "hydro_weather_calendar"],
    )

    month_hours = [744, 696, 744, 720, 744, 720, 744, 744, 720, 744, 720, 720]
    month_names = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    axis = tables["hydro_hour_month_axis"]
    assert axis.fields() == ["month_number"]
    assert axis.values("month_number") == [
        month_number for month_number, count in enumerate(month_hours, start=1) for _ in range(count)
    ]
    calendar = tables["hydro_weather_calendar"]
    assert list(calendar.iter_rows()) == [
        {"hours": hours, "month": month, "month_number": month_number}
        for month_number, (month, hours) in enumerate(zip(month_names, month_hours, strict=True), start=1)
    ]


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
    mapping.append(duration)
    write_records(mapping_path, mapping)
    table_mapping_path = config_path / "table_mapping.json"
    table_records = load_records(table_mapping_path)
    storage_mapping = next(
        record for record in table_records if record["name"] == "generator_storage_duration"
    )
    storage_mapping["operations"][0]["sources"][0] = "storage_duration_selected"
    write_records(table_mapping_path, table_records)

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


def test_generator_lookup_tables_normalize_raw_sources_and_preserve_multi_year_means() -> None:
    """Assemble generator lookup tables from native-shaped source columns."""
    backend = PolarsTabularBackend()
    sources = {
        "heat_rate": TabularSource(
            pl.DataFrame(
                {
                    "i": ["Gas-CC", "Gas-CC"],
                    "v": ["init-1", "init-1"],
                    "r": ["p1", "p1"],
                    "t": [2032, 2040],
                    "value": [10.0, 20.0],
                }
            ).lazy(),
            backend,
        ),
        "requested_solve_year_rows": TabularSource(
            pl.DataFrame({"solve_year": [2032, 2040]}, schema={"solve_year": pl.Int64}).lazy(),
            backend,
        ),
        "fuel_tech_map": TabularSource(
            pl.DataFrame(
                {
                    "i": ["Gas_CC", "Gas_CC_1", "Gas_CC_1", "Gas_CC_2", None],
                    "f": ["gas", "coal-first", "coal-last", "oil", "null-fuel"],
                },
                schema={"i": pl.String, "f": pl.String},
            ).lazy(),
            backend,
        ),
    }

    tables = assemble_tables(
        sources,
        mapping_path=ReEDSConfig.package_config_path() / "table_mapping.json",
        backend=backend,
        table_names=[
            "generator_heat_rate",
            "generator_heat_rate_mean",
            "generator_fuel_map_selected",
            "generator_fuel_full_lookup",
            "generator_fuel_base_lookup",
        ],
    )

    assert [row["year"] for row in tables["generator_heat_rate"].iter_rows()] == [2032, 2040]
    heat_rate_mean = next(iter(tables["generator_heat_rate_mean"].iter_rows()))
    assert heat_rate_mean["heat_rate_mean"] == 15.0
    full_fuel = [
        (row["technology"], row["fuel_type_full"]) for row in tables["generator_fuel_full_lookup"].iter_rows()
    ]
    assert full_fuel == [
        ("gas_cc", "gas"),
        ("gas_cc_1", "coal-first"),
        ("gas_cc_2", "oil"),
        (None, "null-fuel"),
    ]
    base_fuel = {
        row["technology_base"]: row["fuel_type_base"]
        for row in tables["generator_fuel_base_lookup"].iter_rows()
    }
    assert base_fuel == {"gas": "oil", None: "null-fuel"}


def test_generator_lookup_tables_keep_first_per_baseline_key() -> None:
    """Lookup deduplication matches each baseline join key and keeps its first value."""
    backend = PolarsTabularBackend()
    lookup_cases: list[tuple[str, str, dict[str, object], str, str, str, float]] = [
        (
            "generator_heat_rate",
            "heat_rate",
            {"i": "Gas-CC", "v": "init-1", "r": "p1", "t": 2032},
            "t",
            "value",
            "heat_rate",
            10.0,
        ),
        (
            "generator_fuel_price",
            "fuel_price",
            {"i": "Gas-CC", "r": "p1", "t": 2032},
            "t",
            "value",
            "fuel_price",
            10.0,
        ),
        (
            "generator_forced_outages",
            "forced_outages",
            {"i": "Gas-CC"},
            "i",
            "value",
            "forced_outage_rate",
            10.0,
        ),
        (
            "generator_planned_outages",
            "planned_outages",
            {"i": "Gas-CC"},
            "i",
            "value",
            "planned_outage_rate",
            10.0,
        ),
        (
            "generator_cost_vom",
            "cost_vom",
            {"i": "Gas-CC", "v": "init-1", "r": "p1", "t": 2032},
            "t",
            "value",
            "vom_cost",
            10.0,
        ),
        (
            "generator_ramprate",
            "ramprate",
            {"technology": "Gas-CC"},
            "technology",
            "ramp_rate",
            "ramp_rate",
            10.0,
        ),
        (
            "generator_minloadfrac",
            "minloadfrac",
            {"technology": "Gas-CC"},
            "technology",
            "min_load_frac",
            "min_load_frac",
            10.0,
        ),
        ("generator_startcost", "startcost", {"*i": "Gas-CC"}, "*i", "$2004/mw", "startup_cost", 10.0),
        (
            "generator_storage_duration",
            "storage_duration",
            {"i": "Gas-CC"},
            "i",
            "value",
            "storage_duration",
            10.0,
        ),
        (
            "generator_storage_efficiency",
            "storage_efficiency",
            {"i": "Gas-CC", "t": 2032},
            "t",
            "value",
            "round_trip_efficiency",
            10.0,
        ),
        (
            "generator_cost_capital",
            "cost_capital",
            {"i": "Gas-CC", "t": 2032},
            "t",
            "Value",
            "capital_cost",
            10.0,
        ),
        (
            "generator_cost_capital_energy",
            "cost_capital_energy",
            {"i": "Gas-CC", "t": 2032},
            "t",
            "Value",
            "capital_cost_energy",
            10.0,
        ),
        (
            "generator_cf_adjustment",
            "renewable_cf_adjustment",
            {"i": "Gas-CC", "v": "init-1", "t": 2032},
            "t",
            "value",
            "capacity_factor_adjustment",
            10.0,
        ),
        (
            "generator_ilr",
            "ilr",
            {"i": "Gas-CC"},
            "i",
            "value",
            "inverter_loading_ratio",
            10.0,
        ),
        (
            "generator_biofuel_lookup",
            "biofuel_price",
            {"r": "p1", "t": 2032},
            "t",
            "value",
            "biofuel_price",
            10.0,
        ),
        (
            "generator_storage_duration_out",
            "storage_duration_out",
            {"i": "Gas-CC", "v": "init-1", "r": "p1", "t": 2032},
            "t",
            "value",
            "duration_out_value",
            10.0,
        ),
    ]

    failures: list[tuple[str, list[Mapping[str, object]]]] = []
    for table_name, source_name, key, varied_key, value_column, output_column, first_value in lookup_cases:
        distinct_key = {**key, varied_key: 2040 if varied_key == "t" else "Gas-CT"}
        source_rows = [
            {**key, value_column: first_value},
            {**key, value_column: first_value},
            {**key, value_column: 20.0},
            {**distinct_key, value_column: 30.0},
        ]
        sources = {
            source_name: TabularSource(pl.DataFrame(source_rows).lazy(), backend),
            "requested_solve_year_rows": TabularSource(
                pl.DataFrame({"solve_year": [2032, 2040]}, schema={"solve_year": pl.Int64}).lazy(), backend
            ),
        }

        tables = assemble_tables(
            sources,
            mapping_path=ReEDSConfig.package_config_path() / "table_mapping.json",
            backend=backend,
            table_names=[table_name],
        )
        rows = list(tables[table_name].iter_rows())

        if len(rows) != 2 or {row[output_column] for row in rows} != {first_value, 30.0}:
            failures.append((table_name, rows))

    assert failures == []


def test_generator_lookup_preserves_first_null_value_and_null_key() -> None:
    """Deduplicate null keys without replacing a first null value with a later value."""
    backend = PolarsTabularBackend()
    source = TabularSource(
        pl.DataFrame(
            {"i": ["Gas-CC", "Gas-CC", None, None], "value": [None, 0.3, 0.4, 0.5]},
            schema={"i": pl.String, "value": pl.Float64},
        ).lazy(),
        backend,
    )

    tables = assemble_tables(
        {"forced_outages": source},
        mapping_path=ReEDSConfig.package_config_path() / "table_mapping.json",
        backend=backend,
        table_names=["generator_forced_outages"],
    )

    assert list(tables["generator_forced_outages"].iter_rows()) == [
        {"technology": "gas-cc", "forced_outage_rate": None},
        {"technology": None, "forced_outage_rate": 0.4},
    ]


def test_generator_exclusion_lookup_keeps_first_per_baseline_key() -> None:
    """The exclusion table keeps one row per technology and reserve type."""
    backend = PolarsTabularBackend()
    sources = {
        "generator_category_memberships": TabularSource(
            pl.DataFrame(
                {
                    "technology": ["gas-cc", "gas-cc"],
                    "category": ["wind", "wind"],
                }
            ).lazy(),
            backend,
        ),
        "reserve_provider_exclusion_categories": TabularSource(
            pl.DataFrame(
                {
                    "category": ["wind", "wind"],
                    "reserve_type": ["reg", "reg"],
                }
            ).lazy(),
            backend,
        ),
    }

    tables = assemble_tables(
        {},
        mapping_path=ReEDSConfig.package_config_path() / "table_mapping.json",
        backend=backend,
        initial_tables=sources,
        table_names=["generator_excluded_reserve_pairs"],
    )

    assert list(tables["generator_excluded_reserve_pairs"].iter_rows()) == [
        {"excluded": "yes", "reserve_type": "reg", "technology": "gas-cc"}
    ]


def test_migrated_assembly_graphs_are_declared_in_table_mapping() -> None:
    config_path = ReEDSConfig.package_config_path()
    file_names = {record["name"] for record in load_records(config_path / "file_mapping.json")}
    table_names = {record["name"] for record in load_records(config_path / "table_mapping.json")}
    legacy_names = {
        "generator_emission_base_rows",
        "generator_emission_storage_rows",
        "generator_emission_aggregate_rows",
        "generator_emission_owner_rows",
        "emission_matches",
        "emission_type_policy_rows",
        "emission_source_policy_rows",
        "emission_rate_rows",
        "emission_matches_thermal_rows",
        "emission_matches_variable_rows",
        "emission_matches_hydro_rows",
        "emission_matches_storage_rows",
        "emission_matches_import_rows",
        "renewable_profile_owner_rows",
        "renewable_profile_thermal_rows",
        "renewable_profile_variable_rows",
        "renewable_profile_hydro_rows",
        "renewable_profile_storage_rows",
        "renewable_profile_base_rows",
        "renewable_profiles",
        "hydro_monthly_values",
        "hydro_month_counts",
        "hydro_month_distinct_counts",
        "hydro_month_complete",
        "hydro_complete_months",
        "hydro_adjustment_monthly_values",
        "hydro_adjustment_counts",
        "hydro_adjustment_distinct_counts",
        "hydro_adjustment_complete",
        "hydro_adjustment_complete_months",
        "reserve_product_rows",
        "reserve_percentages_default",
        "reserve_cost_summary",
        "reserve_hierarchy_regions",
        "reserve_region_rows",
        "reserve_component_rows",
        "reserve_provider_exclusion_categories",
        "load_owner_names",
        "hydro_hour_month_axis",
        "hydro_weather_calendar",
        "cost_fom_selected",
        "requested_solve_year_keys",
        "generator_capacity_for_solve_year",
        "hydrogen_production_capacity",
        "hydrogen_production_annual_load",
        "hydrogen_production_load",
    }
    mapped_names = legacy_names - {"generator_emission_base_rows"}
    mapped_names.update(
        {
            "generator_emission_thermal_rows",
            "generator_emission_hydro_rows",
            "generator_emission_geothermal_rows",
            "generator_emission_import_rows",
        }
    )

    assert legacy_names.isdisjoint(file_names)
    assert mapped_names <= table_names
    assert "renewable_profiles_first_8760" not in file_names | table_names
    assert "emission_rate_rows" not in file_names
    assert not {"hydro_hour_month_axis", "hydro_weather_calendar"} & file_names


def test_load_profile_validation_preparation_is_table_owned() -> None:
    """Keep load-profile joins and reductions in tables, with file records only asserting."""
    config_path = ReEDSConfig.package_config_path()
    file_records = load_records(config_path / "file_mapping.json")
    table_records = load_records(config_path / "table_mapping.json")
    file_by_name = {record["name"]: record for record in file_records}
    table_by_name = {record["name"]: record for record in table_records}

    assert all("source_selection" not in record for record in file_records)
    assert "load_profile_solve_year_counts" not in file_by_name
    assert {
        "load_profile_solve_year_counts",
        "load_profile_requirement_check",
        "load_profile_peak_values",
    } <= table_by_name.keys()
    for validator, source in {
        "load_profiles_required": "load_profile_requirement_check",
        "load_profile_peak_validation": "load_profile_peak_values",
    }.items():
        record = file_by_name[validator]
        assert record["source"] == source
        assert [step["op"] for step in record["proc_spec"]["steps"]] == ["assert"]

    assert any(
        operation["operation"] == "group_by"
        for name in ("load_profile_solve_year_counts", "load_profile_peak_values")
        for operation in table_by_name[name]["operations"]
    )
    assert any(
        operation["operation"] == "unpivot"
        for operation in table_by_name["load_profile_peak_values"]["operations"]
    )


def test_optional_source_precedence_is_declared_in_table_mapping() -> None:
    """Keep all former source selectors in the ordered generic table graph."""
    config_path = ReEDSConfig.package_config_path()
    file_records = load_records(config_path / "file_mapping.json")
    table_records = load_records(config_path / "table_mapping.json")

    assert all("source_selection" not in record for record in file_records)
    first_present = {
        record["name"]: record["operations"][0]["sources"]
        for record in table_records
        if record.get("operations") and record["operations"][0]["operation"] == "first_present"
    }
    assert len(first_present) == 24
    assert first_present["transmission_capacity_selected"] == [
        "transmission_capacity",
        "transmission_capacity_empty",
    ]
    assert first_present["transmission_losses_selected"] == [
        "transmission_losses",
        "transmission_losses_empty",
    ]
    assert first_present["reserve_percentages_selected_rows"] == [
        "reserve_percentages",
        "reserve_percentages_default",
    ]
    assert first_present["reserve_cost_summary"] == [
        "reserve_costs_default",
        "reserve_costs_market",
        "empty_reserve_cost_rows",
    ]

    hydro_selection = next(
        record for record in table_records if record["name"] == "hydro_capacity_adjustment_selected"
    )
    assert hydro_selection["operations"][0] == {
        "operation": "first_nonempty",
        "sources": ["hydro_capacity_adjustment_input"],
        "fallback": "empty_hydro_capacity_adjustment_rows",
    }


def test_hierarchy_nonempty_validation_uses_table_aggregation() -> None:
    """Keep hierarchy counting in the table graph and the existing check as an assertion."""
    config_path = ReEDSConfig.package_config_path()
    file_records = load_records(config_path / "file_mapping.json")
    table_records = load_records(config_path / "table_mapping.json")
    validator = next(record for record in file_records if record["name"] == "hierarchy_required")
    table = next(record for record in table_records if record["name"] == "hierarchy_nonempty_count")

    assert validator["source"] == "hierarchy_nonempty_count"
    assert [step["op"] for step in validator["proc_spec"]["steps"]] == ["assert"]
    assert table["operations"] == [
        {
            "operation": "group_by",
            "columns": [],
            "aggregate": [{"operation": "count", "column": "region_id", "output": "region_count"}],
        }
    ]


def test_hierarchy_nonempty_validation_rejects_empty_native_input(tmp_path: Path) -> None:
    """A prepared global count still rejects a real empty hierarchy file."""
    config_path = ReEDSConfig.package_config_path()
    file_records = load_records(config_path / "file_mapping.json")
    table_records = load_records(config_path / "table_mapping.json")
    data_files = [
        DataFile.model_validate(record)
        for record in file_records
        if record["name"] in {"hierarchy", "hierarchy_required"}
    ]
    table_mapping_path = tmp_path / "table_mapping.json"
    write_records(
        table_mapping_path,
        [next(record for record in table_records if record["name"] == "hierarchy_nonempty_count")],
    )
    input_folder = tmp_path / "inputs_case"
    input_folder.mkdir()
    columns = [
        "*r",
        "ccreg",
        "cendiv",
        "country",
        "h2ptcreg",
        "hurdlereg",
        "interconnect",
        "nercr",
        "st",
        "transgrp",
        "transreg",
        "usda_region",
    ]
    (input_folder / "hierarchy.csv").write_text(",".join(columns) + "\n", encoding="utf-8")

    with pytest.raises(ReaderError):
        DataReader().read_and_assemble_sources(
            data_files,
            folder_path=tmp_path,
            mapping_path=table_mapping_path,
            backend=PolarsTabularBackend(),
        )


def test_generator_capacity_count_assert_uses_table_aggregation() -> None:
    """Keep the nonempty generator-capacity check as validation over a generic count table."""
    config_path = ReEDSConfig.package_config_path()
    file_records = load_records(config_path / "file_mapping.json")
    table_records = load_records(config_path / "table_mapping.json")
    validator = next(record for record in file_records if record["name"] == "generator_capacity_count")
    count_table = next(record for record in table_records if record["name"] == "generator_capacity_row_count")

    assert validator["source"] == "generator_capacity_row_count"
    assert [step["op"] for step in validator["proc_spec"]["steps"]] == ["assert"]
    assert count_table["operations"] == [
        {
            "operation": "group_by",
            "columns": [],
            "aggregate": [{"operation": "count", "column": "technology", "output": "technology_count"}],
        }
    ]


def test_fom_solve_year_coverage_uses_table_aggregation() -> None:
    """Keep FOM year reduction in tables while preserving its configured-year assertion."""
    config_path = ReEDSConfig.package_config_path()
    file_records = load_records(config_path / "file_mapping.json")
    table_records = load_records(config_path / "table_mapping.json")
    validator = next(record for record in file_records if record["name"] == "fom_solve_year_coverage")
    count_table = next(record for record in table_records if record["name"] == "fom_solve_year_count")

    assert validator["source"] == "fom_solve_year_count"
    assert [step["op"] for step in validator["proc_spec"]["steps"]] == ["assert"]
    assert count_table["operations"] == [
        {"operation": "unique", "columns": ["year"], "keep": "first"},
        {
            "operation": "group_by",
            "columns": [],
            "aggregate": [{"operation": "count", "column": "year", "output": "year_count"}],
        },
    ]


def test_fom_psh_scalar_validation_uses_table_aggregation() -> None:
    """Keep scalar filtering/counting in the table graph and retain its assertions."""
    config_path = ReEDSConfig.package_config_path()
    file_records = load_records(config_path / "file_mapping.json")
    table_records = load_records(config_path / "table_mapping.json")
    validator = next(record for record in file_records if record["name"] == "fom_psh_scalar_validation")
    scalar_table = next(record for record in table_records if record["name"] == "fom_psh_scalar_cardinality")

    assert validator["source"] == "fom_psh_scalar_cardinality"
    assert [step["op"] for step in validator["proc_spec"]["steps"]] == ["assert", "assert"]
    assert scalar_table["operations"] == [
        {"operation": "filter", "column": "parameter", "comparison": "equals", "value": "cost_fom_psh"},
        {"operation": "cast", "column": "value", "dtype": "float64"},
        {
            "operation": "group_by",
            "columns": [],
            "aggregate": [
                {"operation": "first", "column": "value", "output": "psh_fom_cost"},
                {"operation": "count", "column": "parameter", "output": "scalar_count"},
            ],
        },
    ]


@pytest.mark.parametrize(
    ("rows", "expected_error"),
    [
        pytest.param("cost_fom_psh,13030,2004$/MW-year\n", False, id="one-scalar"),
        pytest.param(
            "cost_fom_psh,13030,2004$/MW-year\ncost_fom_psh,14000,2004$/MW-year\n",
            True,
            id="duplicate-scalar",
        ),
        pytest.param("cost_vom_psh,0.375,2004$/MWh\n", True, id="missing-scalar"),
        pytest.param("cost_fom_psh,,2004$/MW-year\n", True, id="null-scalar"),
    ],
)
def test_fom_psh_scalar_cardinality_validates_real_input_rows(
    tmp_path: Path, rows: str, expected_error: bool
) -> None:
    """Validate the scalar count and value using a real source and table assembly."""
    config_path = ReEDSConfig.package_config_path()
    file_records = load_records(config_path / "file_mapping.json")
    table_records = load_records(config_path / "table_mapping.json")
    data_files = [
        DataFile.model_validate(record)
        for record in file_records
        if record["name"] in {"fom_scalars", "fom_psh_scalar_validation"}
    ]
    input_folder = tmp_path / "inputs_case"
    input_folder.mkdir()
    (input_folder / "scalars.csv").write_text(rows, encoding="utf-8")
    table_mapping_path = tmp_path / "table_mapping.json"
    write_records(
        table_mapping_path,
        [next(record for record in table_records if record["name"] == "fom_psh_scalar_cardinality")],
    )

    if expected_error:
        with pytest.raises(ReaderError):
            DataReader().read_and_assemble_sources(
                data_files,
                folder_path=tmp_path,
                mapping_path=table_mapping_path,
                backend=PolarsTabularBackend(),
            )
        return

    sources = DataReader().read_and_assemble_sources(
        data_files,
        folder_path=tmp_path,
        mapping_path=table_mapping_path,
        backend=PolarsTabularBackend(),
    )

    assert list(sources["fom_psh_scalar_cardinality"].iter_rows()) == [
        {"psh_fom_cost": 13030.0, "scalar_count": 1}
    ]


def test_fom_switch_cardinality_uses_table_aggregation() -> None:
    """Keep duplicate-switch counting in the table graph and retain its assertion."""
    config_path = ReEDSConfig.package_config_path()
    file_records = load_records(config_path / "file_mapping.json")
    table_records = load_records(config_path / "table_mapping.json")
    validator = next(record for record in file_records if record["name"] == "fom_switch_cardinality")
    grouped_switches = next(record for record in table_records if record["name"] == "fom_switches_by_name")

    assert validator["source"] == "fom_switches_by_name"
    assert [step["op"] for step in validator["proc_spec"]["steps"]] == ["assert"]
    assert grouped_switches["operations"] == [
        {
            "operation": "group_by",
            "columns": ["parameter"],
            "aggregate": [
                {"operation": "last", "column": "value", "output": "value"},
                {"operation": "count", "column": "parameter", "output": "switch_count"},
            ],
        }
    ]


@pytest.mark.parametrize(
    ("rows", "expected_error"),
    [
        pytest.param("GSw_Upgrades,1\n", False, id="one-switch-value"),
        pytest.param("GSw_Upgrades,1\nGSw_Upgrades,0\n", True, id="duplicate-switch-value"),
    ],
)
def test_fom_switch_cardinality_validates_real_input_rows(
    tmp_path: Path, rows: str, expected_error: bool
) -> None:
    """Validate switch cardinality after table aggregation from a real switches CSV."""
    config_path = ReEDSConfig.package_config_path()
    file_records = load_records(config_path / "file_mapping.json")
    table_records = load_records(config_path / "table_mapping.json")
    data_files = [
        DataFile.model_validate(record)
        for record in file_records
        if record["name"] in {"fom_switches", "fom_switch_cardinality"}
    ]
    input_folder = tmp_path / "inputs_case"
    input_folder.mkdir()
    (input_folder / "switches.csv").write_text(rows, encoding="utf-8")
    table_mapping_path = tmp_path / "table_mapping.json"
    write_records(
        table_mapping_path,
        [next(record for record in table_records if record["name"] == "fom_switches_by_name")],
    )

    if expected_error:
        with pytest.raises(ReaderError, match="Duplicate FOM switch values are not allowed"):
            DataReader().read_and_assemble_sources(
                data_files,
                folder_path=tmp_path,
                mapping_path=table_mapping_path,
                backend=PolarsTabularBackend(),
            )
        return

    sources = DataReader().read_and_assemble_sources(
        data_files,
        folder_path=tmp_path,
        mapping_path=table_mapping_path,
        backend=PolarsTabularBackend(),
    )

    assert list(sources["fom_switches_by_name"].iter_rows()) == [
        {"parameter": "gsw_upgrades", "value": "1", "switch_count": 1}
    ]


@pytest.mark.parametrize(
    "missing_parameter",
    [
        "GSw_Upgrades",
        "GSw_UpgradeFOM_Nems",
        "GSw_UpgradeYear",
        "GSw_UpgradeChar_Year",
    ],
)
def test_missing_fom_policy_switch_does_not_erase_policy_rows(tmp_path: Path, missing_parameter: str) -> None:
    """Scalar switch reductions retain one policy row when a selected input is missing."""
    config_path = ReEDSConfig.package_config_path()
    file_records = load_records(config_path / "file_mapping.json")
    switch_record = next(record for record in file_records if record["name"] == "fom_switches")
    switches = [
        ("GSw_Upgrades", "1"),
        ("GSw_UpgradeFOM_Nems", "0"),
        ("GSw_UpgradeYear", "2028"),
        ("GSw_UpgradeChar_Year", "2028"),
    ]
    inputs = tmp_path / "inputs_case"
    inputs.mkdir()
    (inputs / "switches.csv").write_text(
        "".join(f"{parameter},{value}\n" for parameter, value in switches if parameter != missing_parameter),
        encoding="utf-8",
    )
    decoded = DataReader().read_data_files([DataFile.model_validate(switch_record)], folder_path=tmp_path)

    tables = assemble_tables(
        decoded,
        mapping_path=config_path / "table_mapping.json",
        backend=PolarsTabularBackend(),
        table_names=["fom_switch_policy", "fom_characteristic_year"],
    )

    assert len(list(tables["fom_switch_policy"].iter_rows())) == 1
    if missing_parameter == "GSw_UpgradeChar_Year":
        validator = next(
            record for record in file_records if record["name"] == "fom_characteristic_year_validation"
        )
        with pytest.raises(ReaderError, match="GSw_UpgradeChar_Year must be a valid integer"):
            DataReader().read_data_files(
                [DataFile.model_validate(validator)],
                folder_path=tmp_path,
                initial_sources={"fom_characteristic_year": tables["fom_characteristic_year"]},
            )


@pytest.mark.parametrize(
    ("vintage", "expected_fom"),
    [
        pytest.param("init-1", 100.0, id="hyphenated-initial"),
        pytest.param("init1", 100.0, id="unseparated-initial"),
        pytest.param("new1", 200.0, id="noninitial"),
    ],
)
def test_fom_initial_vintage_uses_init_prefix_in_public_table_assembly(
    vintage: str, expected_fom: float
) -> None:
    """Initial FOM selection follows the original literal ``init`` prefix rule."""
    backend = PolarsTabularBackend()
    policy_row: dict[str, object] = {
        "technology": "target",
        "vintage": vintage,
        "region": "p1",
        "year": 2032,
        "target_technology": "target",
        "target_hydro_fom": 0.0,
        "initial_target_fom": 100.0,
        "target_fom": 200.0,
        "distpv": "no",
        "hintage_fom_cost": 0.0,
        "base_fom": 0.0,
        "hydro_fom_cost": 0.0,
        "retrofit_eligible": False,
        "source_current_retrofit": 0.0,
        "unit_spec_upgrade": False,
        "target_is_ccs": False,
        "retrofit_enabled": False,
        "psh": "no",
        "psh_fom_cost": 0.0,
    }
    prior_retrofit = pl.DataFrame(
        schema={
            "technology": pl.String,
            "vintage": pl.String,
            "region": pl.String,
            "year": pl.Int64,
            "prior_retrofit_fom": pl.Float64,
        }
    )
    tables = assemble_tables(
        {},
        mapping_path=ReEDSConfig.package_config_path() / "table_mapping.json",
        backend=backend,
        initial_tables={
            "generator_fom_policy_rows": TabularSource(pl.DataFrame([policy_row]).lazy(), backend),
            "generator_fom_prior_retrofit": TabularSource(prior_retrofit.lazy(), backend),
        },
        table_names=["generator_fom_costed"],
    )

    result = next(iter(tables["generator_fom_costed"].iter_rows()))

    assert result["fom_cost"] == expected_fom


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
