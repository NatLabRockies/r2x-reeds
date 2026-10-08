"""Custom readers for ReEDS data files."""

from __future__ import annotations

from pathlib import Path

import polars as pl

from r2x_core import DataStore, ReaderConfig

_GAMS_HEADER_DATASETS = (
    "existing_capacity",
    "existing_transmission_capacity",
    "renewable_supply_curves",
)


def _read_gams_header_csv(fpath: Path) -> pl.LazyFrame:
    """Read a ReEDS CSV with or without GAMS' leading header marker."""
    frame = pl.scan_csv(fpath)
    columns = frame.collect_schema().names()
    if not columns or not columns[0].startswith("*"):
        return frame

    return frame.rename({columns[0]: columns[0].removeprefix("*")})


def register_gams_header_readers(store: DataStore, /) -> None:
    """Normalize optional GAMS header markers for compatible ReEDS inputs."""
    for name in _GAMS_HEADER_DATASETS:
        if name not in store:
            continue

        data_file = store[name].model_copy(
            update={"reader": ReaderConfig(kwargs={}, function=_read_gams_header_csv)}
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
