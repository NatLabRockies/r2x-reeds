import json
import tempfile
from pathlib import Path

from r2x_core.store import DataStore
from r2x_reeds import ReEDSConfig, ReEDSGenerator, ReEDSParser

# Configure
config = ReEDSConfig(
    solve_year=2032,
    weather_year=2012,
    case_name="test_Pacific"
)

# Test folder
folder = Path("/Users/mvelasqu/Documents/marck/GDO/r2x-reeds/tests/data/test_Pacific")

# Simple file location fixes before creating DataStore
print("Checking file locations...")

# Check if hour_map file is in the new location and needs to be copied/linked
hmap_new = folder / "inputs_case" / "rep" / "hmap_allyrs.csv"  # Where it actually is
hmap_old = folder / "inputs_case" / "hmap_allyrs.csv"         # Where mapping expects it

if hmap_new.exists() and not hmap_old.exists():
    print("Copying hour map from rep/ folder to expected location...")
    import shutil
    shutil.copy2(str(hmap_new), str(hmap_old))
    print("✓ Hour map file copied")

# Check hierarchy file locations
hierarchy_outputs = folder / "outputs" / "hierarchy.csv"
hierarchy_inputs = folder / "inputs_case" / "hierarchy.csv"

if hierarchy_outputs.exists() and not hierarchy_inputs.exists():
    print("Copying hierarchy from outputs/ to inputs_case/...")
    shutil.copy2(str(hierarchy_outputs), str(hierarchy_inputs))
    print("✓ Hierarchy file copied")

# Handle removed files by filtering them out of the file mapping
print("Processing file mapping to handle removed files...")
file_mapping = ReEDSConfig.get_file_mapping_path()

# Read the original mapping
with open(file_mapping) as f:
    mapping_data = json.load(f)

# Filter out files marked as removed and make problematic files optional
filtered_mapping = []
for file_entry in mapping_data:
    if file_entry.get('removed', False):
        print(f"Skipping removed file: {file_entry.get('name', 'unknown')}")
        continue

    # Make load_data optional due to HDF5 reader configuration issues
    if file_entry.get('name') == 'load_data':
        file_entry['optional'] = True
        print("Made load_data optional (HDF5 reader configuration issue)")

    filtered_mapping.append(file_entry)

# Create temporary mapping file without removed files
with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp_file:
    json.dump(filtered_mapping, tmp_file, indent=2)
    temp_mapping_path = tmp_file.name

try:
    # Create DataStore with filtered mapping
    print("Creating DataStore...")
    data_store = DataStore.from_json(
        temp_mapping_path,
        folder=folder
    )
    print("✓ DataStore created successfully")

    # Debug HDF5 file structure (optional - can be removed)
    print("\n=== HDF5 File Debug ===")
    load_h5_path = folder / "inputs_case" / "load.h5"
    if load_h5_path.exists():
        try:
            import h5py
            with h5py.File(load_h5_path, 'r') as f:
                print(f"HDF5 keys: {list(f.keys())}")
        except Exception as e:
            print(f"HDF5 inspection failed: {e}")
    print("=== End HDF5 Debug ===\n")

    # Create parser and build system
    print("Creating parser...")
    parser = ReEDSParser(config, data_store)

    print("Building system...")
    system = parser.build_system()

    # Access components
    from r2x_reeds import ReEDSDemand, ReEDSEmission
    from r2x_reeds.models.components import (
        ReEDSInterface,
        ReEDSRegion,
        ReEDSReserve,
        ReEDSResourceClass,
        ReEDSTransmissionLine,
    )

    generators = list(system.get_components(ReEDSGenerator))
    loads = list(system.get_components(ReEDSDemand))
    emissions = list(system.get_components(ReEDSEmission))
    regions = list(system.get_components(ReEDSRegion))
    reserves = list(system.get_components(ReEDSReserve))
    interfaces = list(system.get_components(ReEDSInterface))
    tlines = list(system.get_components(ReEDSTransmissionLine))
    resource_classes = list(system.get_components(ReEDSResourceClass))

    print("✓ System built successfully!")
    print(f"  - {len(generators)} generators")
    print(f"  - {len(loads)} loads")
    print(f"  - {len(emissions)} emissions")
    print(f"  - {len(regions)} regions")
    print(f"  - {len(reserves)} reserves")
    print(f"  - {len(interfaces)} interfaces")
    print(f"  - {len(tlines)} transmission lines")
    print(f"  - {len(resource_classes)} resource classes")

except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()

finally:
    # Clean up temporary file
    import os
    if 'temp_mapping_path' in locals() and os.path.exists(temp_mapping_path):
        os.unlink(temp_mapping_path)
        print("Cleaned up temporary files")

print("\n=== Test Complete ===")



# from r2x_core.store import DataStore
# from r2x_reeds import ReEDSConfig, ReEDSGenerator, ReEDSParser

# # Configure
# config = ReEDSConfig(
#     solve_year=2032,
#     weather_year=2012,
#     case_name="test_Pacific"
# )

# # Load data using the default file mapping
# file_mapping = ReEDSConfig.get_file_mapping_path()
# data_store = DataStore.from_json(
#     file_mapping,
#     # folder="/Users/mvelasqu/Documents/marck/GDO/r2x-reeds/tests/data/test_Pacific/"
#     folder="/Users/mvelasqu/Downloads/test_Pacific"
# )

# # Parse
# parser = ReEDSParser(config, data_store)
# system = parser.build_system()

# # Access components
# generators = list(system.get_components(ReEDSGenerator))
# print(f"Built system with {len(generators)} generators")

# # config = ReEDSConfig(
# #     solve_year=2032,
# #     weather_year=2012,
# #     case_name="test_Pacific"
# # )

# # file_mapping = ReEDSConfig.get_file_mapping_path()
# # data_store = DataStore.from_json(
# #     file_mapping,
# #     folder="/Users/mvelasqu/Documents/marck/GDO/r2x-reeds/tests/data/test_Pacific"
# #     # folder="/Users/mvelasqu/Downloads/test_Pacific"
# #     # folder="/Users/mvelasqu/Downloads/test_newest_Pacific"
# # )

# # # Parse
# # parser = ReEDSParser(config, data_store)

# # system = parser.build_system()

# # # Access components
# # generators = list(system.get_components(ReEDSGenerator))
# # loads = list(system.get_components(ReEDSDemand))
# # emissions = list(system.get_components(ReEDSEmission))
# # regions = list(system.get_components(ReEDSRegion))
# # reserves = list(system.get_components(ReEDSReserve))
# # interfaces = list(system.get_components(ReEDSInterface))
# # tline = list(system.get_components(ReEDSTransmissionLine))
# # resource_class = list(system.get_components(ReEDSResourceClass))
# # print(f"Built system with {len(generators)} generators")
# # print(f"Built system with {len(loads)} loads")
# # print(f"Built system with {len(emissions)} emissions")
# # print(f"Built system with {len(regions)} regions")
# # print(f"Built system with {len(reserves)} reserves")
# # print(f"Built system with {len(interfaces)} interfaces")
# # print(f"Built system with {len(tline)} transmission lines")
# # print(f"Built system with {len(resource_class)} resource classes")

# # # data_my = data_store.get_data_file_by_name("modeled_years")
# # # data = data_store.read_data_file(name="modeled_years")

# # # def detect_from_csv(folder: Path) -> str | None:
# # #     # breakpoint()
# # #     csv_path = folder / "meta.csv"
# # #     if csv_path.exists():
# # #         df = pl.read_csv(csv_path)
# # #         version_row = pl.col("commit")
# # #         version_row = df.select(version_row)
# # #         if len(version_row) > 0:
# # #             # return str(version_row["commit"][0])
# # #             return {"git_version": str(version_row["commit"][0])}
# # #     return None

# # # PluginManager.register_version_detector("reeds", detect_from_csv)

# # # detected_ver = PluginManager.registered_version_detectors
# # # version = PluginManager.detect_version("reeds", Path("/Users/mvelasqu/Downloads/test_Pacific"))

# # # steps = PluginManager.get_upgrade_steps("reeds")
# # # print(steps)

# # # from pathlib import Path

# # # from loguru import logger

# # # from r2x_core.plugins import PluginManager
# # # from r2x_reeds.upgrader.data_upgrader import ReedsDataUpgrader

# # # logger.enable("r2x_core")

# # # # Test the version detection functionality
# # # def test_version_detection():
# # #     """Test ReEDS version detection workflow."""

# # #     # Test folder paths - use the one that has meta.csv
# # #     test_folders = [
# # #         "/Users/mvelasqu/Downloads/test_Pacific",
# # #         "/Users/mvelasqu/Downloads/test_newest_Pacific",
# # #         "/Users/mvelasqu/Documents/marck/GDO/r2x-reeds/tests/data/test_Pacific"
# # #     ]

# # #     for folder_path in test_folders:
# # #         folder = Path(folder_path)
# # #         print(f"\n--- Testing folder: {folder} ---")
# # #         print(f"Folder exists: {folder.exists()}")

# # #         if not folder.exists():
# # #             continue

# # #         # Check if meta.csv exists
# # #         meta_csv = folder / "meta.csv"
# # #         print(f"meta.csv exists: {meta_csv.exists()}")

# # #         if meta_csv.exists():
# # #             # Test direct method call
# # #             print("\n1. Testing direct ReedsDataUpgrader.detect_from_csv():")
# # #             version = ReedsDataUpgrader.detect_from_csv(folder)
# # #             print(f"Detected version: {version}")

# # #             # Test through PluginManager (after registering plugin)
# # #             print("\n2. Testing through PluginManager:")
# # #             try:
# # #                 # Register the plugin first
# # #                 from r2x_reeds.plugins import register_plugin
# # #                 register_plugin()

# # #                 # Now test version detection through PluginManager
# # #                 detected_version = PluginManager.detect_version("reeds", folder)
# # #                 print(f"PluginManager detected version: {detected_version}")

# # #                 # Test upgrade steps
# # #                 print("\n3. Testing upgrade steps:")
# # #                 steps = PluginManager.get_upgrade_steps("reeds")
# # #                 print(f"Available upgrade steps: {len(steps)}")
# # #                 for step in steps:
# # #                     print(f"  - {step}")

# # #             except Exception as e:
# # #                 print(f"Error with PluginManager: {e}")
# # #         else:
# # #             print("No meta.csv found, cannot test version detection")
# # #             # Show what files are available
# # #             if folder.exists():
# # #                 csv_files = list(folder.glob("*.csv"))
# # #                 print(f"Available CSV files: {[f.name for f in csv_files[:5]]}...")

# # # if __name__ == "__main__":
# # #     test_version_detection()


# # # from pathlib import Path

# # # # from r2x_core.plugins import PluginManager
# # # from r2x_core.store import DataStore

# # # # from data_upgrader
# # # from r2x_reeds import ReEDSConfig, ReEDSDemand, ReEDSEmission, ReEDSGenerator, ReEDSParser
# # # from r2x_reeds.models.components import (
# # #     ReEDSInterface,
# # #     ReEDSRegion,
# # #     ReEDSReserve,
# # #     ReEDSResourceClass,
# # #     ReEDSTransmissionLine,
# # # )

# # # # Test different folder paths to demonstrate upgrader functionality
# # # test_folders = [
# # #     "/Users/mvelasqu/Documents/marck/GDO/r2x-reeds/tests/data/test_Pacific",
# # #     # "/Users/mvelasqu/Downloads/test_Pacific",
# # #     # "/Users/mvelasqu/Downloads/test_newest_Pacific"
# # # ]

# # # for folder_path in test_folders:
# # #     folder = Path(folder_path)
# # #     if not folder.exists():
# # #         print(f"Skipping {folder_path} - folder doesn't exist")
# # #         continue

# # #     print(f"\n=== Testing with folder: {folder_path} ===")

# # #     try:
# # #         # Register the ReEDS plugin first
# # #         # from r2x_reeds.plugins import register_plugin
# # #         # register_plugin()

# # #         # # Detect ReEDS version using the upgrader system
# # #         # print("1. Detecting ReEDS version...")
# # #         # version = PluginManager.detect_from_csv("reeds", folder)
# # #         # print(f"   Detected version: {version}")

# # #         # Create config
# # #         config = ReEDSConfig(
# # #             solve_year=2032,
# # #             weather_year=2012,
# # #             case_name=folder.name
# # #         )

# # #         # Get file mapping path
# # #         file_mapping = ReEDSConfig.get_file_mapping_path()

# # #         # Create DataStore with upgrader support
# # #         print("2. Creating DataStore with upgrader...")
# # #         data_store = DataStore.from_json(
# # #             file_mapping,
# # #             folder=folder,
# # #             # Enable the upgrader system to handle file location changes
# # #             # plugin_name="reeds",
# # #             # auto_upgrade=True
# # #         )

# # #         print(f"   DataStore created with {len(data_store.list_data_files())} files")

# # #         # Show some files that were found/upgraded
# # #         files_found = data_store.list_data_files()
# # #         print(f"   Key files found: {[f for f in files_found if f in ['hierarchy', 'hour_map', 'modeledyears']]}")

# # #         # Parse with enhanced error handling
# # #         print("3. Creating parser and building system...")
# # #         parser = ReEDSParser(config, data_store)

# # #         # Build the system
# # #         system = parser.build_system()

# # #         # Access components
# # #         generators = list(system.get_components(ReEDSGenerator))
# # #         loads = list(system.get_components(ReEDSDemand))
# # #         emissions = list(system.get_components(ReEDSEmission))
# # #         regions = list(system.get_components(ReEDSRegion))
# # #         reserves = list(system.get_components(ReEDSReserve))
# # #         interfaces = list(system.get_components(ReEDSInterface))
# # #         tline = list(system.get_components(ReEDSTransmissionLine))
# # #         resource_class = list(system.get_components(ReEDSResourceClass))

# # #         print("✓ Built system successfully!")
# # #         print(f"  - {len(generators)} generators")
# # #         print(f"  - {len(loads)} loads")
# # #         print(f"  - {len(emissions)} emissions")
# # #         print(f"  - {len(regions)} regions")
# # #         print(f"  - {len(reserves)} reserves")
# # #         print(f"  - {len(interfaces)} interfaces")
# # #         print(f"  - {len(tline)} transmission lines")
# # #         print(f"  - {len(resource_class)} resource classes")

# # #         # Test glob pattern functionality (example for future XML files)
# # #         # print("4. Testing glob pattern support...")
# # #         # try:
# # #         #     # Example of how glob patterns would work for dynamic file discovery
# # #         #     json_files = list(folder.glob("*.json"))
# # #         #     if json_files:
# # #         #         print(f"   Found JSON files that could use glob patterns: {[f.name for f in json_files]}")
# # #         #     else:
# # #         #         print("   No JSON files found (glob patterns ready for future use)")
# # #         # except Exception as e:
# # #         #     print(f"   Glob pattern test info: {e}")

# # #         # break  # Success with this folder, no need to try others

# # #     except Exception as e:
# # #         print(f"✗ Failed with {folder_path}: {e}")
# # #         import traceback
# # #         traceback.print_exc()
# # #         continue

# # # # Test upgrade steps functionality
# # # # print("\n=== Testing Upgrade Steps ===")
# # # # try:
# # # #     steps = PluginManager.get_upgrade_steps("reeds")
# # # #     print(f"Available ReEDS upgrade steps: {len(steps)}")
# # # #     for i, step in enumerate(steps, 1):
# # # #         print(f"  {i}. {step.__name__}: {step.__doc__.split('.')[0] if step.__doc__ else 'No description'}")
# # # # except Exception as e:
# # # #     print(f"Error getting upgrade steps: {e}")

# # # print("\n=== Test Complete ===")
