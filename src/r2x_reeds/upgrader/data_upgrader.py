"""Data Uprader for ReEDS."""

from pathlib import Path
from typing import Any

from r2x_core import UpgradeStep
from r2x_core.upgrader import PluginUpgrader
from r2x_core.versioning import VersionReader


class ReEDSVersionDetector(VersionReader):
    """Version detector class for ReEDS."""

    def read_version(self, path: Path) -> str | None:
        """Read ReEDS model version.

        Parameters
        ----------
        path : Path
            Path to directory containing meta.csv file.

        Returns
        -------
        str | None
            Version string from meta.csv fourth column, or None if not found.
        """
        import csv

        path = Path(path)

        csv_path = path / "meta.csv"
        if not csv_path.exists():
            msg = f"ReEDS version file {csv_path} not found."
            return FileNotFoundError(msg)

        with open(csv_path) as f:
            reader = csv.reader(f)
            next(reader)  # Skip header row
            second_row = next(reader)
            assert len(second_row) == 5, "meta file format changed."
            return second_row[3]


class ReEDSUpgrader(PluginUpgrader):
    """Upgrader class for ReEDS files."""

    def __init__(
        self,
        path: Path | str,
        steps: list[UpgradeStep] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize ReEDS upgrader.

        Parameters
        ----------
        path : Path | str
            Path to ReEDS data directory containing meta.csv and other data files.
        steps : list[UpgradeStep] | None
            Optional list of upgrade steps. If None, uses class-level steps.
        **kwargs
            Additional keyword arguments (unused, for compatibility).
        """
        self.path = Path(path)
        self.steps = steps or self.__class__.steps
