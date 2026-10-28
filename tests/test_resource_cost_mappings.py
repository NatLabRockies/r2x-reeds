"""Real ReEDS resource inputs map their supported cost and capacity fields."""

from pathlib import Path

import pytest
from pydantic import TypeAdapter

from r2x_core import DataFile, DataReader
from tests.fixtures.data_fixtures import package_file_mapping

pytestmark = [pytest.mark.integration, pytest.mark.polars]

_OUTPUT_RESOURCE_FILES = (
    ("df_sc_in_geohydro", "outputs/df_sc_in_geohydro_allkm.csv"),
    ("df_sc_out_geohydro_reduced", "outputs/df_sc_out_geohydro_allkm_reduced.csv"),
    ("df_sc_in_upv", "outputs/df_sc_in_upv.csv"),
    ("df_sc_out_upv_reduced", "outputs/df_sc_out_upv_reduced.csv"),
    ("df_sc_in_wind-ons", "outputs/df_sc_in_wind-ons.csv"),
    ("df_sc_out_wind-ons_reduced", "outputs/df_sc_out_wind-ons_reduced.csv"),
)


@pytest.mark.parametrize(("source_name", "relative_fpath"), _OUTPUT_RESOURCE_FILES)
def test_resource_cost_projection_reads_real_candidate_and_selected_schemas(
    test_data_path: Path, source_name: str, relative_fpath: str
) -> None:
    """Candidate and selected ReEDS outputs expose cost without fabricated columns."""
    configured_files = {item["name"]: item for item in package_file_mapping()}
    declaration = {**configured_files[source_name], "relative_fpath": relative_fpath}
    data_file = TypeAdapter(DataFile).validate_python(declaration)
    run_path = test_data_path / "test_Upgrader"

    source = DataReader().read_data_files([data_file], folder_path=run_path)[source_name]
    row = next(iter(source.iter_rows()))

    assert isinstance(row["supply_curve_cost"], float)
    assert "cost_per_mw" not in row
    assert "cf" not in row
    assert "cap_avail" not in row


@pytest.mark.parametrize(
    ("source_name", "has_capacity_factor"),
    [
        pytest.param("csp_supply_curve", False, id="csp-no-cf"),
        pytest.param("egs_supply_curve", True, id="egs-has-cf"),
        pytest.param("wind-ofs_supply_curve", True, id="offshore-wind-has-cf"),
    ],
)
def test_resource_supply_curve_projection_matches_technology_schema(
    test_data_path: Path, source_name: str, has_capacity_factor: bool
) -> None:
    """Resource input mappings preserve only technology-supported source fields."""
    configured_files = {item["name"]: item for item in package_file_mapping()}
    data_file = TypeAdapter(DataFile).validate_python(configured_files[source_name])
    run_path = test_data_path / "test_Upgrader"

    source = DataReader().read_data_files([data_file], folder_path=run_path)[source_name]
    row = next(iter(source.iter_rows()))

    assert isinstance(row["supply_curve_cost"], float)
    assert ("capacity_factor" in row) is has_capacity_factor
