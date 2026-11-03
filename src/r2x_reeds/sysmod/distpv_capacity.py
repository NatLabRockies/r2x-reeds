"""Adjust distributed PV capacity for avoided distribution losses."""

import csv
from math import isfinite
from pathlib import Path

from infrasys import System
from loguru import logger
from pydantic import Field
from rust_ok import Err, Ok, Result

from r2x_core import PluginConfig, expose_plugin
from r2x_reeds.models.components import ReEDSGenerator


class DistPVCapacityConfig(PluginConfig):
    """Provide a manual loss fraction or a ReEDS scalars CSV."""

    distloss: float | None = Field(
        default=None,
        ge=0,
        lt=1,
        allow_inf_nan=False,
        description="Distribution loss fraction; overrides the scalars file when provided.",
    )
    scalars_fpath: Path | str | None = Field(
        default=None,
        description="Path to the headerless ReEDS inputs_case/scalars.csv file.",
    )


def _read_distloss(path: Path | str) -> float:
    """Read exactly one distloss scalar from the ReEDS CSV."""
    with Path(path).open(newline="", encoding="utf-8-sig") as stream:
        rows = [row for row in csv.reader(stream) if row and row[0].strip() == "distloss"]
    if len(rows) != 1:
        raise ValueError(f"Expected exactly one distloss row in {path}; found {len(rows)}")
    if len(rows[0]) < 2:
        raise ValueError(f"distloss row in {path} is missing its value")
    loss = float(rows[0][1])
    if not isfinite(loss) or not 0 <= loss < 1:
        raise ValueError("distloss must be a finite fraction in [0, 1)")
    return loss


@expose_plugin
def scale_distpv_capacity(system: System, config: DistPVCapacityConfig) -> Result[System, str]:
    """Scale distpv capacity by 1/(1-distloss), leaving all time series unchanged.

    Only generators with technology exactly equal to ``distpv`` are selected.
    Include this transform once, after parsing and before export. Applying it
    repeatedly compounds the capacity adjustment.
    """
    try:
        if config.distloss is not None:
            loss = config.distloss
            source = "manual override"
        elif config.scalars_fpath is not None:
            loss = _read_distloss(config.scalars_fpath)
            source = str(config.scalars_fpath)
        else:
            raise ValueError("Provide distloss or scalars_fpath for the distpv capacity transform")

        if not isfinite(loss) or not 0 <= loss < 1:
            raise ValueError("distloss must be a finite fraction in [0, 1)")
        factor = 1 / (1 - loss)
        updates: list[tuple[ReEDSGenerator, float]] = []
        for generator in system.get_components(ReEDSGenerator):
            if generator.technology != "distpv":
                continue
            capacity = generator.capacity * factor
            if not isfinite(capacity) or capacity < 0:
                raise ValueError(f"Invalid adjusted capacity for generator {generator.name}")
            updates.append((generator, capacity))

        for generator, capacity in updates:
            generator.capacity = capacity
        logger.info(
            "Scaled capacity of {} distpv generators by {} using distloss={} from {}; "
            "time series unchanged",
            len(updates), factor, loss, source,
        )
    except Exception as error:
        logger.error("Error in distpv capacity transform: {}", error)
        return Err(str(error))
    return Ok(system)