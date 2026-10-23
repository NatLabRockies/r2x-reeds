"""Public profile regressions independent of the parser's calendar implementation."""

import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pytest

from r2x_core import DataStore, PluginContext
from r2x_reeds import ReEDSConfig, ReEDSParser
from r2x_reeds.models import ReEDSHydroGenerator
from tests.test_parser_current_core import configure_csv_sources, copy_package_config

pytestmark = [pytest.mark.integration, pytest.mark.polars]


@pytest.mark.parametrize("weather_year", [2012, [2012, 2011]], ids=["single-weather", "primary-weather"])
@pytest.mark.parametrize("complete_dispatchable_months", [True, False], ids=["complete", "incomplete"])
def test_monthly_hydro_profiles_keep_budget_power_and_leap_year_expansion_distinct(
    reeds_run_path: Path,
    reeds_config: ReEDSConfig,
    tmp_path: Path,
    complete_dispatchable_months: bool,
    weather_year: int | list[int],
) -> None:
    """Capacity scales power but not budget, and February retains its weather-year hours."""
    with TemporaryDirectory(prefix="profiles-", dir=tmp_path) as directory:
        run_path = Path(directory) / "run"
        shutil.copytree(reeds_run_path, run_path)
        inputs = run_path / "inputs_case"
        outputs = run_path / "outputs"
        (outputs / "cap_ivrt.csv").write_text(
            "i,v,r,t,Value\nhydED,init-1,p1,2032,100\nhydND,init-1,p1,2032,200\n"
        )
        months = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
        dispatchable_factors = [0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6]
        nondispatchable_factors = [0.025, 0.05, 0.075, 0.1, 0.125, 0.15, 0.175, 0.2, 0.225, 0.25, 0.275, 0.3]
        capacity_adjustments = [0.95, 0.9, 0.85, 0.8, 0.75, 0.7, 0.65, 0.6, 0.55, 0.5, 0.45, 0.4]
        hydro_rows = ["*i,month,r,t,value\n"]
        adjustment_rows = ["*i,month,r,value\n"]
        for month, budget, power_factor, adjustment in zip(
            months, dispatchable_factors, nondispatchable_factors, capacity_adjustments, strict=True
        ):
            if complete_dispatchable_months or month != "DEC":
                hydro_rows.append(f"hydED,{month},p1,2032,{budget}\n")
            hydro_rows.append(f"hydND,{month},p1,2032,{power_factor}\n")
            adjustment_rows.append(f"hydED,{month},p1,{adjustment}\n")
        (inputs / "hydcf.csv").write_text("".join(hydro_rows))
        (inputs / "hydcapadj.csv").write_text("".join(adjustment_rows))
        config_path = copy_package_config(tmp_path)
        defaults_path = config_path / "defaults.json"
        defaults = json.loads(defaults_path.read_text(encoding="utf-8"))
        defaults["reserve_products"] = []
        defaults_path.write_text(json.dumps(defaults), encoding="utf-8")
        configure_csv_sources(config_path, include_all=True)
        config = ReEDSConfig(
            solve_year=2032,
            weather_year=weather_year,
            case_name="hydro-profile-policy-test",
            config_path_override=config_path,
        )
        store = DataStore(path=run_path)
        context = PluginContext(config=config, store=store)

        result = ReEDSParser.from_context(context).run()

        assert result.system is not None
        system = result.system
        hydro = {generator.technology: generator for generator in system.get_components(ReEDSHydroGenerator)}
        assert set(hydro) == {"hyded", "hydnd"}
        assert hydro["hyded"].is_dispatchable is True
        assert hydro["hydnd"].is_dispatchable is False
        if not complete_dispatchable_months:
            assert not system.has_time_series(hydro["hyded"])
            nondispatchable_power = system.get_time_series(hydro["hydnd"], name="max_active_power")
            assert nondispatchable_power.length == 8760
            assert nondispatchable_power.initial_timestamp == datetime(2012, 1, 1)
            return
        budget = system.get_time_series(hydro["hyded"], name="hydro_budget")
        dispatchable_power = system.get_time_series(hydro["hyded"], name="max_active_power")
        nondispatchable_power = system.get_time_series(hydro["hydnd"], name="max_active_power")
        weather_year_month_hours = [744, 696, 744, 720, 744, 720, 744, 744, 720, 744, 720, 744]
        expected_budget = np.repeat(dispatchable_factors, weather_year_month_hours)[:8760]
        expected_dispatchable_power = np.repeat(
            [95.0, 90.0, 85.0, 80.0, 75.0, 70.0, 65.0, 60.0, 55.0, 50.0, 45.0, 40.0],
            weather_year_month_hours,
        )[:8760]
        expected_nondispatchable_power = np.repeat(
            [5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 45.0, 50.0, 55.0, 60.0],
            weather_year_month_hours,
        )[:8760]
        np.testing.assert_allclose(budget.data, expected_budget)
        np.testing.assert_allclose(dispatchable_power.data, expected_dispatchable_power)
        np.testing.assert_allclose(nondispatchable_power.data, expected_nondispatchable_power)
        assert budget.length == dispatchable_power.length == nondispatchable_power.length == 8760
        for profile in (budget, dispatchable_power, nondispatchable_power):
            assert profile.initial_timestamp == datetime(2012, 1, 1)
            assert profile.resolution == timedelta(hours=1)
        for technology, variable in (
            ("hyded", "hydro_budget"),
            ("hyded", "max_active_power"),
            ("hydnd", "max_active_power"),
        ):
            metadata = system.list_time_series_metadata(hydro[technology], name=variable, solve_year=2032)
            assert len(metadata) == 1
