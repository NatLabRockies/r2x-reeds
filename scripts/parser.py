from pathlib import Path

from r2x_core import DataStore, PluginContext
from r2x_reeds import ReEDSConfig, ReEDSParser

# setup_logging(level="DEBUG")
run_path = Path("/Users/psanchez/Downloads/Pacific/")

config = ReEDSConfig(weather_year=2012, solve_year=2032)
store = DataStore(path=run_path)
store.load_file_mapping(config.fmap_path)

context = PluginContext(config=config, store=store)
result = ReEDSParser.from_context(context).run()
system = result.system
