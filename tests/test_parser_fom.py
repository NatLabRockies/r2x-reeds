"""Public fixed O&M source mappings and characteristic-year coverage."""

from pathlib import Path

import pytest
from pydantic import TypeAdapter

from r2x_core import DataFile, DataReader, assemble_tables
from r2x_core.exceptions import ReaderError
from r2x_core.polars_adapter import PolarsTabularBackend
from tests.fixtures.data_fixtures import package_file_mapping

pytestmark = [pytest.mark.integration, pytest.mark.polars]


@pytest.mark.parametrize(
    ("source_name", "relative_fpath", "empty_content"),
    [
        pytest.param(
            "fom_upgrade_links", "inputs_case/upgrade_link.csv", "*TO,FROM,DELTA\n", id="upgrade-links"
        ),
        pytest.param("fom_unitspec_upgrades", "inputs_case/inputs.h5", None, id="unitspec-upgrades"),
    ],
)
@pytest.mark.parametrize("missing", [False, True], ids=["present", "missing"])
def test_required_fom_sources_allow_empty_data_but_require_the_file(
    tmp_path: Path,
    source_name: str,
    relative_fpath: str,
    empty_content: str | None,
    missing: bool,
) -> None:
    """Current DataReader contracts distinguish an empty source from a missing one."""
    run_path = tmp_path / "run"
    input_path = run_path / relative_fpath
    input_path.parent.mkdir(parents=True)
    if source_name == "fom_unitspec_upgrades":
        if not missing:
            import h5py
            import numpy as np

            with h5py.File(input_path, mode="w") as h5_file:
                group = h5_file.create_group("unitspec_upgrades")
                string_dtype = h5py.string_dtype(encoding="utf-8")
                group.create_dataset("columns", data=np.asarray(["i"], dtype=string_dtype))
                group.create_dataset("i", data=np.asarray([], dtype=string_dtype))
    elif not missing:
        input_path.write_text(empty_content or "", encoding="utf-8")

    configured = {item["name"]: item for item in package_file_mapping()}
    data_file = TypeAdapter(DataFile).validate_python(configured[source_name])
    if missing:
        with pytest.raises((FileNotFoundError, ReaderError)):
            DataReader().read_data_files([data_file], folder_path=run_path)
        return

    sources = DataReader().read_data_files([data_file], folder_path=run_path)

    assert list(sources[source_name].iter_rows()) == []


@pytest.mark.parametrize("source_name", ["cost_fom", "fom_upgrade_characteristics"])
def test_fom_sources_read_fractional_values_after_inference_window(tmp_path: Path, source_name: str) -> None:
    """Both views of plant characteristics preserve late fractional costs."""
    input_path = tmp_path / "inputs_case" / "plantcharout.csv"
    input_path.parent.mkdir(parents=True)
    input_path.write_text(
        "*i,t,variable,value\n"
        + "".join(f"tech_{index},2032,fom,{index}\n" for index in range(100))
        + "fractional-tech,2032,fom,1.2861\n",
        encoding="utf-8",
    )
    configured = {item["name"]: item for item in package_file_mapping()}
    data_file = TypeAdapter(DataFile).validate_python(configured[source_name])

    source = DataReader().read_data_files([data_file], folder_path=tmp_path)[source_name]
    rows = list(source.iter_rows())

    assert float(rows[-1]["fom_cost"]) == pytest.approx(1.2861)


def test_fom_characteristic_source_preserves_all_years(tmp_path: Path) -> None:
    """The upgrade policy source retains prior and solve-year FOM rows."""
    run_path = tmp_path / "run"
    input_path = run_path / "inputs_case" / "plantcharout.csv"
    input_path.parent.mkdir(parents=True)
    input_path.write_text(
        "*i,t,variable,value\n"
        "Gas-CC,2032,fom,20081\n"
        "Gas-CC,2029,fom,99999\n"
        "Gas-CC,2032,capcost,not-a-number\n"
        "wind-ons_1,2032,fom,31000\n",
        encoding="utf-8",
    )
    configured = {item["name"]: item for item in package_file_mapping()}
    data_file = TypeAdapter(DataFile).validate_python(configured["fom_upgrade_characteristics"])

    raw = DataReader().read_data_files([data_file], folder_path=run_path)["fom_upgrade_characteristics"]
    sources = assemble_tables(
        {"fom_upgrade_characteristics": raw},
        mapping_path=Path(__file__).parents[1] / "src/r2x_reeds/config/table_mapping.json",
        backend=PolarsTabularBackend(),
        table_names=["fom_characteristic_source"],
    )

    assert list(sources["fom_characteristic_source"].iter_rows()) == [
        {"technology": "gas-cc", "year": 2032, "fom_cost": 20081.0},
        {"technology": "gas-cc", "year": 2029, "fom_cost": 99999.0},
        {"technology": "wind-ons_1", "year": 2032, "fom_cost": 31000.0},
    ]
