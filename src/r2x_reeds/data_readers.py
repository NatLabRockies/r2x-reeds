"""Custom readers for ReEDS data files."""

from __future__ import annotations

from pathlib import Path

import polars as pl
from r2x_core import DataStore, ReaderConfig


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
