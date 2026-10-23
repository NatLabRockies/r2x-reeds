"""Public contracts for source-backed FOM controls and conditional inputs."""

import shutil
from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from r2x_core import DataStore, PluginContext
from r2x_core.exceptions import PluginError
from r2x_reeds import ReEDSConfig, ReEDSParser
from r2x_reeds.models import ReEDSGenerator
from tests.fixtures.data_fixtures import current_data_store

pytestmark = [pytest.mark.integration, pytest.mark.polars]


@pytest.fixture
def control_run_path(reeds_run_path: Path, tmp_path: Path) -> Iterator[Path]:
    """Isolate each real-file case and release its copied run afterwards."""
    with TemporaryDirectory(prefix="fom-controls-", dir=tmp_path) as directory:
        run_path = Path(directory) / "run"
        shutil.copytree(reeds_run_path, run_path)
        yield run_path


@pytest.mark.parametrize("enabled", [False, True], ids=["disabled", "enabled"])
@pytest.mark.parametrize("present", [False, True], ids=["absent", "existing-empty"])
def test_water_input_requiredness_distinguishes_absent_from_existing_empty(
    control_run_path: Path, reeds_config: ReEDSConfig, enabled: bool, present: bool
) -> None:
    """Only physical absence under an enabled water switch is an error."""
    inputs = control_run_path / "inputs_case"
    switches_path = inputs / "switches.csv"
    switches = switches_path.read_text()
    assert "GSw_WaterMain,0" in switches
    switches_path.write_text(switches.replace("GSw_WaterMain,0", f"GSw_WaterMain,{int(enabled)}"))
    water_path = inputs / "upgradelink_water.csv"
    if present:
        water_path.write_text("*TO,FROM,DELTA\n")
    else:
        water_path.unlink(missing_ok=True)
    store = current_data_store(control_run_path)
    context = PluginContext(config=reeds_config, store=store)
    parser = ReEDSParser.from_context(context)

    if enabled and not present:
        with pytest.raises(PluginError) as captured:
            parser.run()
        assert isinstance(captured.value.__cause__, FileNotFoundError)
        assert "upgradelink_water.csv" in str(captured.value.__cause__)
        return

    result = parser.run()

    assert result.system is not None
    assert list(result.system.get_components(ReEDSGenerator))


@pytest.mark.parametrize(
    ("filename", "duplicate_row"),
    [("switches.csv", "GSw_Upgrades,1\n"), ("scalars.csv", "cost_fom_psh,13030,2004$/MW-year\n")],
    ids=["duplicate-switch", "duplicate-scalar"],
)
def test_fom_control_sources_reject_duplicate_singleton_values(
    control_run_path: Path, reeds_config: ReEDSConfig, filename: str, duplicate_row: str
) -> None:
    """Source order must not silently decide which control value is used."""
    source = control_run_path / "inputs_case" / filename
    with source.open("a") as handle:
        handle.write(duplicate_row)
    store = current_data_store(control_run_path)
    context = PluginContext(config=reeds_config, store=store)
    parser = ReEDSParser.from_context(context)

    with pytest.raises(PluginError, match=r"(?i)duplicate|unique|singleton|cardinality"):
        parser.run()
