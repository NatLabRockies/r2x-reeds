"""Data upgrader for ReEDS."""

from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from rust_ok import Err, Ok, Result

from r2x_core import (
    DataStore,
    PluginContext,
    SemanticVersioningStrategy,
    UpgradeStep,
    UpgradeType,
    VersionReader,
    VersionStrategy,
    run_upgrade_step,
)
from r2x_core.utils import shall_we_upgrade
from r2x_reeds.upgrader.helpers import LEGACY_VERSION
from r2x_reeds.upgrader.upgrade_steps import UPGRADE_STEPS

if TYPE_CHECKING:
    from r2x_reeds.plugin_config import ReEDSConfig


class ReEDSVersionDetector(VersionReader):
    """Version detector class for ReEDS."""

    def read_version(self, folder_path: Path) -> str | None:
        """Read ReEDS model version from tag column.

        Parameters
        ----------
        folder_path : Path
            Path to directory containing meta.csv file.

        Returns
        -------
        str | None
            Version string from meta.csv "tag" column, or LEGACY_VERSION if
            the column is missing or empty.

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
            header_row = next(reader)
            data_row = next(reader)

            # Find "tag" column by header name
            try:
                tag_index = header_row.index("tag")
            except ValueError:
                # No "tag" column found - legacy format
                return LEGACY_VERSION

            # ReEDS writes the literal "None" when no tag is available.
            if tag_index < len(data_row):
                tag = data_row[tag_index].strip()
                if tag and tag.lower() != "none":
                    return tag

            return LEGACY_VERSION


class ReEDSUpgrader:
    """Upgrader class for ReEDS files."""

    steps: ClassVar[list[UpgradeStep]] = list(UPGRADE_STEPS)
    version_reader: ClassVar[VersionReader] = ReEDSVersionDetector()
    version_strategy: ClassVar[VersionStrategy] = SemanticVersioningStrategy()

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
    ) -> Result[Path, Exception]:
        """Run ReEDS upgrade steps, retaining expected failures as exceptions."""
        try:
            resolved_version = current_version or self.version_reader.read_version(self.path)
        except OSError as error:
            return Err(error)

        if resolved_version is None:
            msg = "ReEDS version could not be determined from meta.csv."
            return Err(ValueError(msg))

        active_strategy = strategy or self.version_strategy
        data = self.path
        for step in sorted(self.steps, key=lambda item: (item.priority, item.name)):
            if step.upgrade_type is not upgrade_type:
                continue

            if target_version is not None and active_strategy is not None:
                try:
                    target_is_after_step = (
                        active_strategy.compare_versions(step.target_version, target=target_version) > 0
                    )
                except ValueError as error:
                    return Err(error)
                if target_is_after_step:
                    continue

            try:
                decision = shall_we_upgrade(step, current_version=resolved_version, strategy=active_strategy)
            except ValueError as error:
                return Err(error)
            if decision.is_err():
                return Err(decision.err())
            if not decision.value:
                continue

            result = run_upgrade_step(data, step=step, upgrader_context=upgrader_context)
            if result.is_err():
                return Err(result.err())

            upgraded = result.value
            if not isinstance(upgraded, Path):
                msg = f"Upgrade step {step.name} did not return a Path"
                return Err(TypeError(msg))
            data = upgraded

        return Ok(data)


def run_reeds_upgrades(
    *,
    store: DataStore,
    ctx: PluginContext["ReEDSConfig"],
) -> Result[None, Exception]:
    """Run ReEDS file upgrades while preserving original exception values."""
    upgrader = ReEDSUpgrader(store.folder)
    current_version = ctx.current_version
    if current_version is None:
        try:
            current_version = upgrader.version_reader.read_version(store.folder)
        except OSError as error:
            return Err(error)
        if current_version is None:
            msg = "ReEDS version could not be determined from meta.csv."
            return Err(ValueError(msg))
        ctx.current_version = current_version

    result = upgrader.upgrade(
        current_version=current_version,
        target_version=ctx.target_version,
        strategy=ctx.version_strategy,
    )
    if result.is_err():
        return Err(result.err())
    return Ok(None)
