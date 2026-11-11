from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pytest
from infrasys import System
from infrasys.time_series_models import SingleTimeSeries

from r2x_reeds.models.components import ReEDSGenerator, ReEDSRegion
from r2x_reeds.sysmod.distpv_capacity import DistPVCapacityConfig, scale_distpv_capacity

pytestmark = [pytest.mark.unit]


def _build_system() -> tuple[System, ReEDSGenerator, ReEDSGenerator]:
    system = System(name="test_distpv_capacity")
    region = ReEDSRegion(name="west")
    system.add_component(region)
    distpv = ReEDSGenerator(name="distpv_west", technology="distpv", region=region, capacity=100.0)
    other = ReEDSGenerator(name="upv_west", technology="upv_1", region=region, capacity=200.0)
    system.add_component(distpv)
    system.add_component(other)
    return system, distpv, other


@pytest.mark.parametrize("loss", [0.0, 0.05, 0.1])
def test_manual_loss_scales_only_capacity(loss: float) -> None:
    system, distpv, other = _build_system()
    profile = SingleTimeSeries.from_array(
        data=np.array([0.0, 105.0, 50.0]),
        name="max_active_power",
        initial_timestamp=datetime(2035, 1, 1),
        resolution=timedelta(hours=1),
    )
    system.add_time_series(profile, distpv)
    metadata_before = system.list_time_series_metadata(distpv)

    result = scale_distpv_capacity(system, DistPVCapacityConfig(distloss=loss))

    assert result.is_ok()
    assert result.unwrap() is system
    assert distpv.capacity == pytest.approx(100.0 / (1 - loss))
    assert other.capacity == 200.0
    assert system.list_time_series_metadata(distpv) == metadata_before
    np.testing.assert_array_equal(system.get_time_series(distpv, name="max_active_power").data, profile.data)


def test_reads_reeds_scalars(tmp_path: Path) -> None:
    system, distpv, _ = _build_system()
    path = tmp_path / "scalars.csv"
    path.write_text('other,1,"description, with comma"\ndistloss,0.05,distribution loss\n')
    result = scale_distpv_capacity(system, DistPVCapacityConfig(scalars_fpath=path))
    assert result.is_ok()
    assert distpv.capacity == pytest.approx(100.0 / 0.95)


def test_manual_loss_overrides_file(tmp_path: Path) -> None:
    system, distpv, _ = _build_system()
    result = scale_distpv_capacity(
        system, DistPVCapacityConfig(distloss=0.0, scalars_fpath=tmp_path / "absent.csv")
    )
    assert result.is_ok()
    assert distpv.capacity == 100.0


@pytest.mark.parametrize("loss", [-0.1, 1.0, 1.1, float("nan"), float("inf")])
def test_rejects_invalid_manual_loss(loss: float) -> None:
    with pytest.raises(ValueError):
        DistPVCapacityConfig(distloss=loss)


@pytest.mark.parametrize(
    "contents",
    ["other,1\n", "distloss,0.05\ndistloss,0.1\n", "distloss\n", "distloss,nan\n", "distloss,1\n"],
)
def test_bad_scalars_do_not_mutate_capacity(tmp_path: Path, contents: str) -> None:
    system, distpv, other = _build_system()
    path = tmp_path / "scalars.csv"
    path.write_text(contents)
    result = scale_distpv_capacity(system, DistPVCapacityConfig(scalars_fpath=path))
    assert result.is_err()
    assert distpv.capacity == 100.0
    assert other.capacity == 200.0


def test_missing_source_fails() -> None:
    system, distpv, _ = _build_system()
    assert scale_distpv_capacity(system, DistPVCapacityConfig()).is_err()
    assert distpv.capacity == 100.0
