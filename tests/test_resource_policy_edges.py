"""Public resource precedence regressions with source-specific CSV schemas."""

import json
import shutil
from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory

import polars as pl
import pytest
from infrasys.location import GeographicInfo

from r2x_core import DataFile, DataReader, DataStore, PluginContext, TabularSource, assemble_tables
from r2x_core.exceptions import ReaderError
from r2x_core.polars_adapter import PolarsTabularBackend
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


@pytest.mark.parametrize(
    ("source_has_rows", "source_capacity", "expected_capacity"),
    [
        pytest.param(True, "341", 341.0, id="source-values-win"),
        pytest.param(True, "", 254.0, id="candidate-fills-null-source-field"),
        pytest.param(False, "", 254.0, id="candidate-fallback-when-source-empty"),
    ],
)
def test_resource_precedence_uses_real_file_aliases_and_preserves_selected_values(
    resource_run_path: Path,
    reeds_config: ReEDSConfig,
    source_has_rows: bool,
    source_capacity: str,
    expected_capacity: float,
) -> None:
    """Source rows own present values, candidates fill nulls or absent sources."""
    inputs = resource_run_path / "inputs_case"
    outputs = resource_run_path / "outputs"
    source_header = "sc_point_gid,class,capacity,cf,region,supply_curve_cost_per_mw\n"
    source_rows = f"416,1,{source_capacity},0.2,p1,10\n" if source_has_rows else ""
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


@pytest.mark.parametrize(
    ("raw_flag", "raw_value", "raw_type", "expected"),
    [
        pytest.param("0", 0, int, False, id="numeric-false"),
        pytest.param("1", 1, int, True, id="numeric-true"),
        pytest.param("false", False, bool, False, id="text-false"),
        pytest.param("true", True, bool, True, id="text-true"),
        pytest.param(None, None, None, None, id="missing-column"),
    ],
)
def test_resource_investment_bool_normalizes_supported_csv_encodings_in_tables(
    tmp_path: Path,
    raw_flag: str | None,
    raw_value: int | bool | None,
    raw_type: type | None,
    expected: bool | None,
) -> None:
    """Table projection normalizes native numeric and textual flags without rewriting inputs."""
    config_path = ReEDSConfig.package_config_path()
    file_records = json.loads((config_path / "file_mapping.json").read_text(encoding="utf-8"))
    file_record = next(item for item in file_records if item["name"] == "df_sc_out_upv_reduced")
    data_file = DataFile.model_validate(file_record)
    output_path = tmp_path / "outputs" / "df_sc_out_upv_reduced.csv"
    output_path.parent.mkdir()
    header = "sc_point_gid,class,supply_curve_cost_per_mw"
    row = "416,1,12"
    if raw_flag is not None:
        header += ",investment_bool"
        row += f",{raw_flag}"
    output_path.write_text(f"{header}\n{row}\n", encoding="utf-8")

    sources = DataReader().read_data_files([data_file], folder_path=tmp_path)
    source = sources[data_file.name]
    assert isinstance(source, TabularSource)
    raw_row = next(iter(source.iter_rows()))
    if raw_flag is None:
        assert "investment_bool" not in source.fields()
    else:
        assert raw_row["investment_bool"] == raw_value
        assert type(raw_row["investment_bool"]) is raw_type

    table_records = json.loads((config_path / "table_mapping.json").read_text(encoding="utf-8"))
    table_record = next(item for item in table_records if item["name"] == "resource_output_rows_upv")
    table_mapping_path = tmp_path / "table_mapping.json"
    table_mapping_path.write_text(json.dumps([table_record]), encoding="utf-8")
    tables = assemble_tables(
        sources,
        mapping_path=table_mapping_path,
        backend=PolarsTabularBackend(),
    )
    result = tables[table_record["name"]]

    assert next(iter(result.iter_rows()))["investment_bool"] is expected
    assert result.data.collect_schema()["investment_bool"] == pl.Boolean


def test_resource_input_still_rejects_a_missing_renamed_source_column(tmp_path: Path) -> None:
    """A real candidate file missing a configured rename input remains malformed."""
    config_path = ReEDSConfig.package_config_path()
    file_records = json.loads((config_path / "file_mapping.json").read_text(encoding="utf-8"))
    data_file = DataFile.model_validate(next(item for item in file_records if item["name"] == "df_sc_in_upv"))
    relative_fpath = data_file.relative_fpath
    assert isinstance(relative_fpath, str)
    source_path = tmp_path / relative_fpath
    source_path.parent.mkdir(parents=True)
    source_path.write_text("sc_point_gid,class,cap_avail\n416,1,254\n", encoding="utf-8")

    with pytest.raises(ReaderError, match="supply_curve_cost_per_mw"):
        DataReader().read_data_files([data_file], folder_path=tmp_path)


@pytest.mark.parametrize(
    ("capacity_in_source", "expected_capacity"),
    [
        pytest.param(True, 777.0, id="optional-field-present"),
        pytest.param(False, None, id="optional-field-absent"),
    ],
)
def test_resource_table_projection_preserves_optional_candidate_capacity(
    tmp_path: Path, capacity_in_source: bool, expected_capacity: float | None
) -> None:
    """The table projection retains a native optional field or emits a typed null."""
    config_path = ReEDSConfig.package_config_path()
    file_records = json.loads((config_path / "file_mapping.json").read_text(encoding="utf-8"))
    data_file = DataFile.model_validate(next(item for item in file_records if item["name"] == "df_sc_in_upv"))
    header = "sc_point_gid,class,cap_avail,supply_curve_cost_per_mw"
    row = "416,1,254,20"
    if capacity_in_source:
        header += ",capacity"
        row += ",777"
    relative_fpath = data_file.relative_fpath
    assert isinstance(relative_fpath, str)
    source_path = tmp_path / relative_fpath
    source_path.parent.mkdir(parents=True)
    source_path.write_text(f"{header}\n{row}\n", encoding="utf-8")
    sources = DataReader().read_data_files([data_file], folder_path=tmp_path)
    source = sources[data_file.name]
    assert isinstance(source, TabularSource)
    assert ("capacity" in source.fields()) is capacity_in_source

    table_records = json.loads((config_path / "table_mapping.json").read_text(encoding="utf-8"))
    record = next(item for item in table_records if item["name"] == "resource_candidate_rows_upv")
    table_mapping_path = tmp_path / "table_mapping.json"
    table_mapping_path.write_text(json.dumps([record]), encoding="utf-8")
    result = assemble_tables(
        sources,
        mapping_path=table_mapping_path,
        backend=PolarsTabularBackend(),
    )[record["name"]]

    assert next(iter(result.iter_rows()))["capacity"] == expected_capacity


@pytest.mark.parametrize(
    ("capacity_factor_in_source", "expected_capacity_factor"),
    [
        pytest.param(True, 0.37, id="optional-output-field-present"),
        pytest.param(False, None, id="optional-output-field-absent"),
    ],
)
def test_resource_table_projection_preserves_optional_selected_capacity_factor(
    tmp_path: Path, capacity_factor_in_source: bool, expected_capacity_factor: float | None
) -> None:
    """Selected rows retain native optional attributes or produce typed nulls."""
    config_path = ReEDSConfig.package_config_path()
    file_records = json.loads((config_path / "file_mapping.json").read_text(encoding="utf-8"))
    data_file = DataFile.model_validate(
        next(item for item in file_records if item["name"] == "df_sc_out_upv_reduced")
    )
    header = "sc_point_gid,class,supply_curve_cost_per_mw,year,built_capacity"
    row = "416,1,12,2009,0.37"
    if capacity_factor_in_source:
        header += ",capacity_factor"
        row += ",0.37"
    relative_fpath = data_file.relative_fpath
    assert isinstance(relative_fpath, str)
    source_path = tmp_path / relative_fpath
    source_path.parent.mkdir(parents=True)
    source_path.write_text(f"{header}\n{row}\n", encoding="utf-8")
    sources = DataReader().read_data_files([data_file], folder_path=tmp_path)
    source = sources[data_file.name]
    assert isinstance(source, TabularSource)
    assert ("capacity_factor" in source.fields()) is capacity_factor_in_source

    table_records = json.loads((config_path / "table_mapping.json").read_text(encoding="utf-8"))
    record = next(item for item in table_records if item["name"] == "resource_output_rows_upv")
    mapping_path = tmp_path / "table_mapping.json"
    mapping_path.write_text(json.dumps([record]), encoding="utf-8")
    result = assemble_tables(
        sources,
        mapping_path=mapping_path,
        backend=PolarsTabularBackend(),
    )[record["name"]]

    output_row = next(iter(result.iter_rows()))
    assert output_row["capacity_factor"] == expected_capacity_factor
    assert result.data.collect_schema()["capacity_factor"] == pl.Float64


def test_supply_capacity_alias_does_not_shadow_candidate_capacity(
    resource_run_path: Path, reeds_config: ReEDSConfig
) -> None:
    """A raw supply capacity populates available capacity, not the separate capacity field."""
    inputs = resource_run_path / "inputs_case"
    outputs = resource_run_path / "outputs"
    (inputs / "supplycurve_upv.csv").write_text(
        "sc_point_gid,class,capacity,cf,region,supply_curve_cost_per_mw\n416,1,341,0.2,p1,10\n"
    )
    (outputs / "df_sc_in_upv.csv").write_text(
        "sc_gid,sc_point_gid,latitude,longitude,region,class,bin,cap_avail,existing_capacity,"
        "online_year,retire_year,supply_curve_cost_per_mw,capacity\n"
        "0,416,48,-122,p1,1,18,254,0,0,0,20,777\n"
    )
    (outputs / "df_sc_out_upv_reduced.csv").write_text(
        "year,sc_gid,sc_point_gid,latitude,longitude,region,class,bin,supply_curve_cost_per_mw,"
        "built_capacity,investment_bool\n"
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
        case_name="resource-capacity-alias-test",
        excluded_techs=[],
        config_path_override=config_path,
    )
    context = PluginContext(config=config, store=DataStore(path=resource_run_path))

    result = ReEDSParser.from_context(context).run()

    assert result.system is not None
    site = next(iter(result.system.get_components(ReEDSResourceSite)))
    assert site.capacity == 777.0
    assert site.available_capacity == 341.0


def test_resource_assembly_is_owned_by_table_mapping() -> None:
    config_path = ReEDSConfig.package_config_path()
    file_names = {record["name"] for record in json.loads((config_path / "file_mapping.json").read_text())}
    table_names = {record["name"] for record in json.loads((config_path / "table_mapping.json").read_text())}
    migrated_names = {
        "resource_supply_rows",
        "resource_candidate_rows",
        "resource_output_rows",
        "resource_region_names",
        "resource_reference_rows",
        "resource_build_reference",
        "resource_site_rows",
        "resource_site_geo",
        "resource_build_rows",
        "resource_build_geo",
    }
    migrated_names.update(
        f"resource_{kind}_rows_{technology}"
        for kind in ("supply", "candidate", "output")
        for technology in ("csp", "egs", "geohydro", "upv", "wind-ons", "wind-ofs")
    )

    assert migrated_names.isdisjoint(file_names)
    assert migrated_names <= table_names
