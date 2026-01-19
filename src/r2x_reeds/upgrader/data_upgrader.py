"""Data upgrader for ReEDS."""

from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from rust_ok import Err, Ok, Result

from r2x_core import (
    DataStore,
    GitVersioningStrategy,
    PluginContext,
    UpgradeStep,
    UpgradeType,
    VersionReader,
    VersionStrategy,
    run_upgrade_step,
)
from r2x_core.utils import shall_we_upgrade
from r2x_reeds.upgrader.helpers import COMMIT_HISTORY
from r2x_reeds.upgrader.upgrade_steps import UPGRADE_STEPS

if TYPE_CHECKING:
    from r2x_reeds.plugin_config import ReEDSConfig


class ReEDSVersionDetector(VersionReader):
    """Version detector class for ReEDS."""

    def read_version(self, folder_path: Path) -> str | None:
        """Read ReEDS model version.
        Parameters
        ----------
        folder_path : Path
            Path to directory containing meta.csv file.

        Returns
        -------
        str | None
            Version string from meta.csv fourth column, or None if not found.

        Raises
        ------
        FileNotFoundError
            If meta.csv file does not exist.
        """
        import csv

        folder_path = Path(folder_path)

        csv_path = folder_path / "meta.csv"
        if not csv_path.exists():
            msg = f"ReEDS version file {csv_path} not found."
            raise FileNotFoundError(msg)

        with open(csv_path) as f:
            reader = csv.reader(f)
            next(reader)  # Skip header row
            second_row = next(reader)
            assert len(second_row) == 5, "meta file format changed."
            return second_row[3]


class ReEDSUpgrader:
    """Upgrader class for ReEDS files."""

    steps: ClassVar[list[UpgradeStep]] = list(UPGRADE_STEPS)
    version_reader: ClassVar[VersionReader] = ReEDSVersionDetector()
    version_strategy: ClassVar[VersionStrategy] = GitVersioningStrategy(COMMIT_HISTORY)

    def __init__(self, path: Path | str) -> None:
        """Initialize ReEDS upgrader.

        Parameters
        ----------
        path : Path | str
            Path to ReEDS data directory containing meta.csv and other data files.
        """
        self.path = Path(path)

    def upgrade(
        self,
        *,
        current_version: str | None = None,
        target_version: str | None = None,
        strategy: VersionStrategy | None = None,
        upgrader_context: dict[str, object] | None = None,
        upgrade_type: UpgradeType = UpgradeType.FILE,
    ) -> Result[Path, str]:
        """Run ReEDS upgrade steps for the configured folder.

        Parameters
        ----------
        current_version : str | None, optional
            Override for the detected version. If None, use the version reader.
        target_version : str | None, optional
            Optional target version to stop upgrades at. If None, run all eligible steps.
        strategy : VersionStrategy | None, optional
            Optional version comparison strategy override.
        upgrader_context : dict[str, object] | None, optional
            Context passed to upgrade steps that accept `upgrader_context`.
        upgrade_type : UpgradeType, optional
            Upgrade type to apply (FILE or SYSTEM). Defaults to FILE.

        Returns
        -------
        Result[Path, str]
            Ok(path) when upgrades succeed, Err with message on failure.
        """
        try:
            resolved_version = current_version or self.version_reader.read_version(self.path)
        except FileNotFoundError as exc:
            return Err(str(exc))

        if resolved_version is None:
            return Err("ReEDS version could not be determined from meta.csv.")

        active_strategy = strategy or self.version_strategy

        data: Path = self.path
        for step in sorted(self.steps, key=lambda item: (item.priority, item.name)):
            if step.upgrade_type is not upgrade_type:
                continue

            if target_version is not None and active_strategy is not None:
                try:
                    if active_strategy.compare_versions(step.target_version, target=target_version) > 0:
                        continue
                except Exception as exc:
                    return Err(f"Invalid target_version '{target_version}': {exc}")

            try:
                decision = shall_we_upgrade(step, current_version=resolved_version, strategy=active_strategy)
            except Exception as exc:
                return Err(str(exc))
            if decision.is_err():
                return Err(str(decision.err()))
            if not decision.unwrap():
                continue

            result = run_upgrade_step(data, step=step, upgrader_context=upgrader_context)
            if result.is_err():
                return Err(result.err())

            upgraded = result.unwrap()
            if not isinstance(upgraded, Path):
                return Err(f"Upgrade step {step.name} did not return a Path")
            data = upgraded

        return Ok(data)


def run_reeds_upgrades(
    *,
    store: DataStore,
    ctx: PluginContext["ReEDSConfig"],
) -> Result[None, str]:
    """Run ReEDS file upgrades using the plugin context."""
    upgrader = ReEDSUpgrader(store.folder)
    current_version = ctx.current_version
    if current_version is None:
        try:
            current_version = upgrader.version_reader.read_version(store.folder)
        except FileNotFoundError as exc:
            return Err(str(exc))
        if current_version is None:
            return Err("ReEDS version could not be determined from meta.csv.")
        ctx.current_version = current_version

    result = upgrader.upgrade(
        current_version=current_version,
        target_version=ctx.target_version,
        strategy=ctx.version_strategy,
    )
    if result.is_err():
        return Err(str(result.err()))
    return Ok(None)
