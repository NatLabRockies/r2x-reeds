from pathlib import Path

from r2x_core import DataStore, PluginContext
from r2x_reeds import ReEDSConfig, ReEDSParser
from r2x_reeds.models.components import ReEDSDemand
from r2x_reeds.sysmod.exports import ExportsConfig, add_exports

# RUN_PATH = Path("/Users/mvelasqu/Documents/kestrel-data/v20250725_gdoK0_OBBBAcon_DemMd__core")
RUN_PATH = Path("/Users/mvelasqu/Documents/marck/GDO/test-r2x-translations/reeds-runs/v20260617_DefaultDCLoad_20GWsited_Flexible98_HighH2_LimTrans" \
"")
WEATHER_YEAR = 2012
SOLVE_YEAR = 2035


config = ReEDSConfig(
    solve_year=SOLVE_YEAR,
    weather_year=WEATHER_YEAR,
    excluded_techs=["can-imports", "electrolyzer", "smr", "smr_ccs"],
)
store = DataStore.from_plugin_config(config, path=RUN_PATH)
context = PluginContext(config=config, store=store)
result_context = ReEDSParser.from_context(context).run()
system = result_context.system
if system is None:
    raise RuntimeError("ReEDS parser returned no system")


annual_exports = DataStore.load_file(RUN_PATH / "inputs_case/can_exports.csv", name="canada_exports")
if annual_exports is not None:
    annual_exports = annual_exports.collect()

parsed_demands = list(system.get_components(ReEDSDemand))
demands_by_region = {demand.region.name: demand for demand in parsed_demands}
print(f"Parsed {len(parsed_demands)} regional demand components")
base_stats_by_region = {}
if annual_exports is not None:
    print(f"\nBEFORE: existing regional demand (weather year {WEATHER_YEAR})")
    print(f"{'Region':<8} {'Demand':<14} {'Hours':>7} {'Energy (MWh)':>16} {'Peak (MW)':>12}")
    for row in annual_exports.iter_rows(named=True):
        region_name = row["r"]
        demand = demands_by_region.get(region_name)
        if demand is None:
            print(f"{region_name:<8} No ReEDSDemand found")
        elif not system.has_time_series(demand):
            print(f"{region_name:<8} No base load profile found")
        else:
            profile = system.get_time_series(demand, name="max_active_power")
            energy_mwh = float(profile.data.sum())
            peak_mw = float(profile.data.max())
            base_stats_by_region[region_name] = (energy_mwh, peak_mw, len(profile.data))
            print(
                f"{region_name:<8} {demand.name:<14} {len(profile.data):>7,} "
                f"{energy_mwh:>16,.1f} {peak_mw:>12,.1f}"
            )

export_result = add_exports(
    system,
    ExportsConfig(
        weather_year=WEATHER_YEAR,
        solve_year=SOLVE_YEAR,
        canada_exports_fpath=RUN_PATH / "inputs_case/can_exports.csv",
        canada_exports_h_frac_fpath=RUN_PATH / "inputs_case/rep/can_exports_h_frac.csv",
        hour_map_fpath=RUN_PATH / "inputs_case/rep/hmap_myr.csv",
    ),
)
if export_result.is_err():
    raise RuntimeError(export_result.unwrap_err())
system = export_result.unwrap()

profiled_demands = 0
if annual_exports is not None:
    print("\nAFTER: demand profile with Canadian exports added")
    print(
        f"{'Region':<8} {'Demand':<14} {'Hours':>7} {'Base (MWh)':>14} "
        f"{'Export input (MWh)':>20} {'Export added (MWh)':>20} "
        f"{'After (MWh)':>14} {'Base peak (MW)':>16} {'After peak (MW)':>17}"
    )
    for row in annual_exports.iter_rows(named=True):
        region_name = row["r"]
        demand = demands_by_region.get(region_name)
        if demand is not None and system.has_time_series(demand):
            profile = system.get_time_series(demand, name="max_active_power")
            profiled_demands += 1
            base_energy_mwh, base_peak_mw, _ = base_stats_by_region[region_name]
            added_energy_mwh = float(profile.data.sum()) - base_energy_mwh
            export_input_mwh = float(row[str(SOLVE_YEAR)])
            print(
                f"{region_name:<8} {demand.name:<14} {len(profile.data):>7,} "
                f"{base_energy_mwh:>14,.1f} {export_input_mwh:>20,.1f} "
                f"{added_energy_mwh:>20,.1f} {profile.data.sum():>14,.1f} "
                f"{base_peak_mw:>16,.1f} {profile.data.max():>17,.1f}"
            )
        else:
            print(f"{region_name:<8} No export demand profile attached")

annual_region_count = len(annual_exports) if annual_exports is not None else 0
print(f"Added export demand to {profiled_demands} of {annual_region_count} annual export regions")
