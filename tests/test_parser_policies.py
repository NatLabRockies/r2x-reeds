from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pytest
from infrasys.time_series_models import SingleTimeSeries

from r2x_core import DataStore, PluginContext, System
from r2x_reeds import ReEDSConfig, ReEDSParser
from r2x_reeds.models.components import ReEDSGenerator, ReEDSRegion, ReEDSVariableGenerator
from tests.type_helpers import get_time_series

pytestmark = pytest.mark.unit


def _build_parser(
    tmp_path: Path,
    *,
    drop_gen_capacity_threshold: float = 0.0,
    apply_cf_adjustment: bool = False,
    apply_ilr_adjustment: bool = False,
) -> ReEDSParser:
    config = ReEDSConfig(
        solve_year=2032,
        weather_year=2012,
        drop_gen_capacity_threshold=drop_gen_capacity_threshold,
        apply_cf_adjustment=apply_cf_adjustment,
        apply_ilr_adjustment=apply_ilr_adjustment,
    )
    store = DataStore(path=tmp_path)
    return ReEDSParser.from_context(PluginContext(config=config, store=store))


def _add_profile(system: System, generator: ReEDSGenerator) -> None:
    series = SingleTimeSeries.from_array(
        data=np.array([0.0, 25.0, 100.0]),
        name="max_active_power",
        initial_timestamp=datetime(2012, 1, 1),
        resolution=timedelta(hours=1),
    )
    system.add_time_series(series, generator, solve_year=2032)


def test_profile_adjustments_scale_values_and_keep_capacity(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    parser = _build_parser(tmp_path, apply_cf_adjustment=True, apply_ilr_adjustment=True)
    system = System(name="profile-adjustments")
    region = ReEDSRegion(name="p1")
    generator = ReEDSVariableGenerator(
        name="upv_1_p1",
        category="solar",
        technology="upv_1",
        region=region,
        capacity=100.0,
        solve_year=2032,
        capacity_factor_adjustment=0.8,
        inverter_loading_ratio=1.3,
    )
    system.add_component(region)
    system.add_component(generator)
    _add_profile(system, generator)

    parser._apply_generator_policies(system)

    np.testing.assert_allclose(
        get_time_series(system, generator, name="max_active_power", solve_year=2032).data,
        [0.0, 26.0, 104.0],
    )
    assert generator.capacity == 100.0
    assert system.list_time_series_keys(generator)[0].features == {"solve_year": 2032}
    assert "exceeds generator capacity after ILR adjustment" in caplog.text


def test_profile_adjustment_requires_configured_value(tmp_path: Path) -> None:
    parser = _build_parser(tmp_path, apply_cf_adjustment=True)
    system = System(name="missing-profile-adjustment")
    region = ReEDSRegion(name="p1")
    generator = ReEDSVariableGenerator(
        name="wind-ons_1_p1",
        category="wind",
        technology="wind-ons_1",
        region=region,
        capacity=100.0,
        capacity_factor_adjustment=None,
    )
    system.add_component(region)
    system.add_component(generator)
    _add_profile(system, generator)

    with pytest.raises(ValueError, match="Missing CF adjustment for wind-ons_1_p1"):
        parser._apply_generator_policies(system)

    np.testing.assert_allclose(
        get_time_series(system, generator, name="max_active_power", solve_year=2032).data,
        [0.0, 25.0, 100.0],
    )


def test_capacity_threshold_removes_small_generators_and_profiles(tmp_path: Path) -> None:
    parser = _build_parser(tmp_path, drop_gen_capacity_threshold=50.0)
    system = System(name="capacity-threshold")
    region = ReEDSRegion(name="p1")
    small = ReEDSGenerator(
        name="small",
        category="thermal",
        technology="gas-cc",
        region=region,
        capacity=10.0,
    )
    large = ReEDSGenerator(
        name="large",
        category="thermal",
        technology="gas-cc",
        region=region,
        capacity=100.0,
    )
    system.add_component(region)
    system.add_component(small)
    system.add_component(large)
    _add_profile(system, small)

    parser._apply_generator_policies(system)

    assert list(system.get_components(ReEDSGenerator)) == [large]
    assert not system.has_time_series(small)
