"""Custom readers for ReEDS data files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl

from r2x_core import DataStore, ReaderConfig, TabularProcessing

_GAMS_HEADER_DATASETS = (
    "existing_capacity",
    "existing_transmission_capacity",
    "renewable_supply_curves",
)


def read_gams_header_csv(fpath: Path, /, **kwargs: Any) -> pl.LazyFrame:
    """Read a ReEDS CSV with or without GAMS' leading header marker."""
    frame = pl.scan_csv(fpath, **kwargs)
    columns = frame.collect_schema().names()
    if not columns or not columns[0].startswith("*"):
        return frame

    return frame.rename({columns[0]: columns[0].removeprefix("*")})


def register_gams_header_readers(store: DataStore, /) -> None:
    """Normalize single-row CSV headers, preserving explicit reader overrides."""
    for name in _GAMS_HEADER_DATASETS:
        if name not in store:
            continue

        reader = store[name].reader
        if reader is not None and (reader.function is not None or reader.header_rows > 1):
            continue

        reader = reader if reader is not None else ReaderConfig(kwargs={})
        data_file = store[name].model_copy(
            update={"reader": reader.model_copy(update={"function": read_gams_header_csv})}
        )
        store.add_data([data_file], overwrite=True)


def _read_modeled_years_file(fpath: Path) -> pl.LazyFrame:
    """Read ReEDS' headerless, wide list of modeled years into one typed column."""
    return (
        pl.scan_csv(fpath, has_header=False)
        .unpivot(value_name="modeled_years")
        .select(pl.col("modeled_years").cast(pl.Int32))
    )


def register_modeled_years_reader(store: DataStore, /) -> None:
    """Configure a ReEDS DataStore to read the headerless modeled-years file."""
    if "modeled_years" not in store:
        return

    data_file = store["modeled_years"].model_copy(
        update={
            "reader": ReaderConfig(kwargs={}, function=_read_modeled_years_file),
            "proc_spec": None,
        }
    )
    store.add_data([data_file], overwrite=True)


def configure_fom_processing(store: DataStore) -> None:
    """Configure core's hydro unpivot from the run's region-column schema."""
    if "fom_hydro" not in store:
        return
    data_file = store["fom_hydro"]
    processing = data_file.proc_spec
    if not isinstance(processing, TabularProcessing):
        msg = "fom_hydro requires TabularProcessing configuration"
        raise ValueError(msg)
    if processing.unpivot_on:
        return
    raw_frame = store.reader.read_data_file(
        data_file.model_copy(update={"proc_spec": None}), folder_path=store.folder
    )
    if not isinstance(raw_frame, pl.LazyFrame):
        msg = "fom_hydro must be a tabular dataset"
        raise ValueError(msg)
    regions = [column.lower() for column in raw_frame.collect_schema().names() if column != "technology"]
    if not regions:
        msg = "fom_hydro has no region columns to unpivot"
        raise ValueError(msg)
    configured = data_file.model_copy(
        update={"proc_spec": processing.model_copy(update={"unpivot_on": regions})}
    )
    store.add_data([configured], overwrite=True)
