from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import pytest
from infrasys.time_series_models import SingleTimeSeries

from r2x_core import DataStore, PluginContext, System, TabularSource
from r2x_core.polars_adapter import PolarsTabularBackend
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


def _policy_source(frame: pl.DataFrame) -> TabularSource:
    return TabularSource(frame.lazy(), PolarsTabularBackend())


def _build_input_policy_parser(tmp_path: Path, *, use_psh: bool = False) -> ReEDSParser:
    config = ReEDSConfig(
        solve_year=2032,
        weather_year=2012,
        use_psh_energy_capacity_duration=use_psh,
    )
    parser = ReEDSParser.from_context(
        PluginContext(config=config, store=DataStore(path=tmp_path))
    )
    assert parser.on_validate().is_ok()
    return parser


def _generator_input_sources(*, storage_duration: float | None = None) -> dict[str, TabularSource]:
    generators = pl.DataFrame(
        {
            "name": ["gas-cc_h2-cc_p1_2032", "hyded_p1_2032", "pumped-hydro_1_p1_2032"],
            "category": ["gas-cc_h2-cc", "hydro", "pumped_storage"],
            "technology": ["gas-cc_h2-cc", "hyded", "pumped-hydro_1"],
            "component_family": ["thermal", "hydro", "storage"],
            "capacity": [100.0, 100.0, 100.0],
            "vintage": ["new", "new", "new"],
            "region": ["p1", "p1", "p1"],
            "year": [2032, 2032, 2032],
            "is_dispatchable": [None, True, None],
            "storage_duration": [None, None, storage_duration],
        }
    )
    empty_links = pl.DataFrame(
        schema={"technology": pl.String, "target_technology": pl.String}
    )
    return {
        "generator_rows": _policy_source(generators),
        "generator_thermal_rows": _policy_source(
            generators.filter(pl.col("component_family") == "thermal").select(
                "technology", "storage_duration"
            ).with_columns(pl.lit(None, dtype=pl.Float64).alias("ramp_rate"))
        ),
        "generator_hydro_rows": _policy_source(
            generators.filter(pl.col("component_family") == "hydro").select(
                "technology", "storage_duration"
            ).with_columns(pl.lit(None, dtype=pl.Float64).alias("ramp_rate"))
        ),
        "generator_storage_rows": _policy_source(
            pl.DataFrame(
                schema={
                    "name": pl.String,
                    "category": pl.String,
                    "technology": pl.String,
                    "capacity": pl.Float64,
                    "vintage": pl.String,
                    "solve_year": pl.Int64,
                    "region": pl.String,
                    "storage_duration": pl.Float64,
                }
            )
        ),
        "fom_upgrade_links": _policy_source(empty_links),
        "fom_switches": _policy_source(
            pl.DataFrame({"parameter": ["gsw_watermain"], "value": ["0"]})
        ),
        "ramprate": _policy_source(
            pl.DataFrame(
                {"technology": ["h2-cc", "hydro"], "ramp_rate": [0.08, 1.0]}
            )
        ),
    }


def test_generator_ramp_policy_resolves_upgrade_and_dispatchable_hydro(
    tmp_path: Path,
) -> None:
    parser = _build_input_policy_parser(tmp_path)
    sources = _generator_input_sources()
    sources["fom_upgrade_links"] = _policy_source(
        pl.DataFrame(
            {
                "technology": ["gas-cc_h2-cc"],
                "target_technology": ["h2-cc"],
            }
        )
    )

    updated = parser._prepare_generator_input_policies(sources)

    thermal = updated["generator_thermal_rows"].data.collect()
    hydro = updated["generator_hydro_rows"].data.collect()
    assert thermal["ramp_rate"].to_list() == [0.08]
    assert hydro["ramp_rate"].to_list() == [1.0]


def test_water_switch_enables_cooling_ramp_resolution(tmp_path: Path) -> None:
    parser = _build_input_policy_parser(tmp_path)
    sources = _generator_input_sources()
    generator_rows = sources["generator_rows"].data.collect().with_columns(
        pl.when(pl.col("component_family") == "thermal")
        .then(pl.lit("gas-cc_r_fsa_h2-cc"))
        .otherwise(pl.col("technology"))
        .alias("technology")
    )
    thermal_rows = sources["generator_thermal_rows"].data.collect().with_columns(
        pl.lit("gas-cc_r_fsa_h2-cc").alias("technology")
    )
    sources["generator_rows"] = _policy_source(generator_rows)
    sources["generator_thermal_rows"] = _policy_source(thermal_rows)
    sources["fom_switches"] = _policy_source(
        pl.DataFrame({"parameter": ["gsw_watermain"], "value": ["1"]})
    )
    sources["fom_water_upgrade_links"] = _policy_source(
        pl.DataFrame(
            {
                "technology": ["gas-cc_r_fsa_h2-cc"],
                "target_technology": ["gas-cc_r_fsa"],
            }
        )
    )
    cooling_schema = {
        "technology": pl.String,
        "base_technology": pl.String,
        "cooling_type": pl.String,
        "water_source": pl.String,
    }
    sources["cooling_technology_links"] = _policy_source(
        pl.DataFrame(
            {
                "technology": ["gas-cc_r_fsa"],
                "base_technology": ["gas-cc"],
                "cooling_type": ["r"],
                "water_source": ["fsa"],
            }
        )
    )
    sources["cooling_upgrade_technology_links"] = _policy_source(
        pl.DataFrame(schema=cooling_schema)
    )
    sources["ramprate"] = _policy_source(
        pl.DataFrame(
            {
                "technology": ["gas-cc", "gas-cc_r_fsa", "gas-cc_r_fsa_h2-cc"],
                "ramp_rate": [0.05, 0.8, 0.9],
            }
        )
    )

    updated = parser._prepare_generator_input_policies(sources)

    thermal = updated["generator_thermal_rows"].data.collect()
    assert thermal["ramp_rate"].to_list() == [0.05]


def test_psh_report_duration_restores_storage_row_missing_baseline_duration(
    tmp_path: Path,
) -> None:
    parser = _build_input_policy_parser(tmp_path, use_psh=True)
    sources = _generator_input_sources()
    keys = {
        "technology": ["pumped-hydro_1"],
        "vintage": ["new"],
        "region": ["p1"],
        "year": [2032],
    }
    sources["psh_energy_capacity"] = _policy_source(
        pl.DataFrame({**keys, "psh_energy_capacity": [1970.0]})
    )
    sources["psh_reference_capacity"] = _policy_source(
        pl.DataFrame({**keys, "reference_capacity": [100.0]})
    )

    updated = parser._prepare_generator_input_policies(sources)

    storage = updated["generator_storage_rows"].data.collect()
    assert storage["technology"].to_list() == ["pumped-hydro_1"]
    assert storage["solve_year"].to_list() == [2032]
    assert storage["storage_duration"].to_list() == [pytest.approx(19.7)]


def test_disabled_psh_policy_does_not_require_optional_report_sources(
    tmp_path: Path,
) -> None:
    parser = _build_input_policy_parser(tmp_path, use_psh=False)

    updated = parser._prepare_generator_input_policies(_generator_input_sources(storage_duration=12.0))

    assert "psh_energy_capacity" not in updated
    assert "psh_reference_capacity" not in updated


def test_profile_adjustments_scale_values_and_keep_capacity(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
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
