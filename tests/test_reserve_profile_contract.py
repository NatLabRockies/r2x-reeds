"""Whole-parser profile and reserve behavior with controlled real input files."""

import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import h5py
import numpy as np
import polars as pl
import pytest

from r2x_core import PluginContext
from r2x_core.exceptions import PluginError, ReaderError
from r2x_reeds import ReEDSConfig, ReEDSParser
from r2x_reeds.models import ReEDSDemand, ReEDSGenerator, ReEDSReserve
from tests.fixtures.data_fixtures import current_data_store, csv_file_mapping

pytestmark = [pytest.mark.integration, pytest.mark.polars]


def write_hourly_profile_file(
    path: Path,
    /,
    *,
    columns: list[str],
    values: np.ndarray,
    solve_year: int | None = None,
) -> None:
    """Write the existing named-index HDF5 format used by the real source readers."""
    timestamps = (
        (np.datetime64("2012-01-01") + np.arange(values.shape[0]) * np.timedelta64(1, "h"))
        .astype("datetime64[s]")
        .astype("S19")
    )
    with h5py.File(path, "w") as handle:
        handle.create_dataset("columns", data=np.asarray(columns, dtype="S32"))
        handle.create_dataset("data", data=values)
        if solve_year is None:
            handle.create_dataset("index_0", data=timestamps)
            handle.create_dataset("index_names", data=np.asarray(["datetime"], dtype="S8"))
        else:
            handle.create_dataset("index_0", data=np.full(values.shape[0], solve_year, dtype=np.int64))
            handle.create_dataset("index_1", data=timestamps)
            handle.create_dataset("index_names", data=np.asarray(["year", "datetime"], dtype="S8"))


@pytest.mark.parametrize(
    ("exclude_solar", "profile_hours", "load_hours", "unprofiled_solar_capacity", "source_policy"),
    [
        (False, 8760, 8760, 0, "default"),
        (True, 8760, 8760, 0, "default"),
        (False, 8, 8760, 300, "default"),
        (False, 8, 8, 300, "default"),
        (False, 8760, 8760, 0, "market"),
        (False, 8760, 8760, 0, "empty-default"),
        (False, 8760, 8760, 0, "no-costs"),
        (False, 8760, 8760, 0, "no-percentages"),
        (False, 8760, 8760, 0, "malformed-default"),
    ],
    ids=[
        "both-providers",
        "solar-ineligible",
        "short-renewable-full-load-and-missing-contributor",
        "short-load-and-renewable-profiles-and-missing-contributor",
        "market-costs",
        "present-empty-default-does-not-select-market",
        "no-cost-source",
        "configured-percentage-metadata",
        "present-malformed-default-does-not-select-market",
    ],
)
def test_reserve_requirements_and_provider_membership_are_distinct_policies(
    reeds_run_path: Path,
    reeds_config: ReEDSConfig,
    tmp_path: Path,
    exclude_solar: bool,
    profile_hours: int,
    load_hours: int,
    unprofiled_solar_capacity: int,
    source_policy: str,
) -> None:
    """Activity-gated solar capacity affects requirements even when solar cannot provide reserve."""
    with TemporaryDirectory(prefix="reserve-profiles-", dir=tmp_path) as directory:
        run_path = Path(directory) / "run"
        shutil.copytree(reeds_run_path, run_path)
        inputs = run_path / "inputs_case"
        outputs = run_path / "outputs"
        hierarchy_path = inputs / "hierarchy.csv"
        hierarchy = pl.read_csv(hierarchy_path)
        hierarchy.with_columns(
            pl.when(pl.col("*r") == "p1")
            .then(pl.lit("controlled"))
            .otherwise(pl.lit("rest"))
            .alias("transreg")
        ).write_csv(hierarchy_path)
        (outputs / "cap_ivrt.csv").write_text(
            "i,v,r,t,Value\nwind-ons_1,new1,p1,2032,100\nupv_1,new1,p1,2032,200\n"
        )
        if unprofiled_solar_capacity:
            with (outputs / "cap_ivrt.csv").open("a") as output:
                output.write(f"upv_2,new1,p1,2032,{unprofiled_solar_capacity}\n")
        with h5py.File(inputs / "load.h5", "r") as handle:
            load_columns = [value.decode() for value in handle["columns"][:]]
        write_hourly_profile_file(
            inputs / "load.h5",
            columns=load_columns,
            values=np.full((load_hours, len(load_columns)), 10.0),
            solve_year=2032,
        )
        write_hourly_profile_file(
            inputs / "recf.h5",
            columns=["wind-ons_1|p1", "upv_1|p1"],
            values=np.tile([[0.2, 0.0], [0.0, 0.5]], (profile_hours // 2, 1)),
        )
        (inputs / "orperc.csv").write_text(",or_load,or_wind,or_pv\nSPINNING,0.9,0.8,0.7\n")
        default_costs = inputs / "cost_opres_default.csv"
        market_costs = inputs / "cost_opres_market.csv"
        default_costs.write_text(",reg,flex,spin\nfirst,1,3,5\nsecond,3,5,9\n")
        market_costs.write_text(",reg,flex,spin\nfirst,20,30,100\nsecond,40,50,200\n")
        if source_policy in {"market", "no-costs"}:
            default_costs.unlink()
        if source_policy == "empty-default":
            default_costs.write_text(",reg,flex,spin\n")
        if source_policy == "no-costs":
            market_costs.unlink()
        if source_policy == "no-percentages":
            (inputs / "orperc.csv").unlink()
        if source_policy == "malformed-default":
            default_costs.write_bytes(b"\xff\xfe")
        config_path = tmp_path / "reserve-config"
        shutil.copytree(reeds_config.config_path, config_path)
        defaults_path = config_path / "defaults.json"
        defaults = json.loads(defaults_path.read_text(encoding="utf-8"))
        product = next(item for item in defaults["reserve_products"] if item["reserve_type"] == "SPINNING")
        product.update(
            load_fraction=0.3,
            wind_fraction=0.1,
            solar_fraction=0.2,
            default_load_percentage=0.6,
            default_wind_percentage=0.5,
            default_solar_percentage=0.4,
        )
        defaults["reserve_products"] = [product]
        defaults["reserve_provider_exclusions"] = (
            [{"reserve_type": "SPINNING", "technology_category": "solar"}] if exclude_solar else []
        )
        defaults_path.write_text(json.dumps(defaults), encoding="utf-8")
        config = ReEDSConfig(
            solve_year=reeds_config.solve_year,
            weather_year=reeds_config.weather_year,
            case_name=reeds_config.case_name,
            scenario=reeds_config.scenario,
            config_path_override=config_path,
        )
        store = current_data_store(run_path, data_files=csv_file_mapping())
        context = PluginContext(config=config, store=store)

        if source_policy == "malformed-default":
            with pytest.raises(PluginError, match="reserve_costs_default") as raised:
                ReEDSParser.from_context(context).run()
            assert isinstance(raised.value.__cause__, ReaderError)
            assert isinstance(raised.value.__cause__.__cause__, ValueError)
            return
        result = ReEDSParser.from_context(context).run()

        assert result.system is not None
        system = result.system
        reserves = {reserve.name: reserve for reserve in system.get_components(ReEDSReserve)}
        assert set(reserves) == {"controlled_SPINNING", "rest_SPINNING"}
        controlled = reserves["controlled_SPINNING"]
        for reserve in reserves.values():
            expected_percentages = (0.6, 0.5, 0.4) if source_policy == "no-percentages" else (0.9, 0.8, 0.7)
            assert (reserve.or_load_percentage, reserve.or_wind_percentage, reserve.or_pv_percentage) == (
                expected_percentages
            )
            expected_cost: float | None = 7.0
            if source_policy in {"empty-default", "no-costs"}:
                expected_cost = None
            elif source_policy == "market":
                expected_cost = 150.0
            assert reserve.spin_cost == expected_cost
            assert reserve.reg_cost is None
            assert reserve.flex_cost is None
            assert reserve.duration == 3600
            assert reserve.time_frame == 300
            assert reserve.vors == 400000.0
        requirement = system.get_time_series(controlled, name="requirement")
        expected_requirement = np.zeros(8760)
        expected_requirement[:load_hours] = 3.0
        expected_requirement[:profile_hours] = np.tile(
            [5.0, 3.0 + (200.0 + unprofiled_solar_capacity) * 0.2], profile_hours // 2
        )
        np.testing.assert_allclose(requirement.data, expected_requirement)
        assert requirement.initial_timestamp == datetime(2012, 1, 1)
        assert requirement.resolution == timedelta(hours=1)
        assert requirement.length == 8760
        generators = {generator.technology: generator for generator in system.get_components(ReEDSGenerator)}
        expected_technologies = {"wind-ons_1", "upv_1"}
        if unprofiled_solar_capacity:
            expected_technologies.add("upv_2")
            assert not system.has_time_series(generators["upv_2"])
        assert set(generators) == expected_technologies
        wind = generators["wind-ons_1"]
        solar = generators["upv_1"]
        np.testing.assert_allclose(
            system.get_time_series(wind).data, np.tile([20.0, 0.0], profile_hours // 2)
        )
        np.testing.assert_allclose(
            system.get_time_series(solar).data, np.tile([0.0, 100.0], profile_hours // 2)
        )
        assert wind.ext["reserves"] == [controlled.name]
        assert solar.ext.get("reserves", []) == ([] if exclude_solar else [controlled.name])
        demands = list(system.get_components(ReEDSDemand))
        assert len(demands) == len(load_columns)
        assert all(demand.max_active_power == 10.0 for demand in demands)
        for demand in demands:
            load_series = system.get_time_series(demand)
            assert load_series.length == load_hours
            np.testing.assert_allclose(load_series.data, np.full(load_hours, 10.0))
