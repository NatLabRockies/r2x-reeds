from pathlib import Path

from r2x_core import DataStore, PluginContext
from r2x_reeds import ReEDSConfig, ReEDSParser
from r2x_reeds.models.components import ReEDSGenerator

RUN_PATH = Path("/Users/mvelasqu/Documents/kestrel-data/v20250725_gdoK0_OBBBAcon_DemMd__core")
WEATHER_YEAR = 2012
SOLVE_YEAR = 2035

config = ReEDSConfig(
    solve_year=SOLVE_YEAR,
    weather_year=WEATHER_YEAR,
    excluded_techs=[],
    drop_gen_capacity_threshold=1e-3,
    models=("r2x_reeds.models",),
)
store = DataStore.from_plugin_config(config, path=RUN_PATH)
context = PluginContext(config=config, store=store)
result_context = ReEDSParser.from_context(context).run()
system = result_context.system
if system is None:
    raise RuntimeError("ReEDS parser returned no system")

generators = sorted(
    system.get_components(ReEDSGenerator),
    key=lambda generator: (float(generator.capacity), generator.name.casefold()),
)
lowest_capacity_generators = generators[:20]
print(
    f"\n20 lowest-capacity ReEDS generators "
    f"(showing {len(lowest_capacity_generators)} of {len(generators)} total)"
)
print(f"{'Generator':<40} {'Technology':<24} {'Region':<12} {'Capacity MW':>14}")
for generator in lowest_capacity_generators:
    print(
        f"{generator.name:<40} {generator.technology:<24} {generator.region.name:<12} "
        f"{float(generator.capacity):>18,.7f}"
    )
