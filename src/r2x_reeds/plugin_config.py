"""Configuration for ReEDS parser."""

from __future__ import annotations

from typing import Annotated, ClassVar

from pydantic import Field

from r2x_core.plugin_config import PluginConfig


class ReEDSConfig(PluginConfig):
    """Configuration for ReEDS model parser.

    This configuration class defines all parameters needed to parse
    ReEDS model data, including year information and model-specific settings.
    Model-specific defaults and constants should be loaded using the
    `load_defaults()` class method and used in parser logic.

    Parameters
    ----------
    solve_years : int | list[int]
        Model solve year(s) (e.g., 2030, [2030, 2040, 2050])
    weather_years : int | list[int]
        Weather data year(s) used for time series profiles (e.g., 2012, [2007, 2012])
    case_name : str, optional
        Name of the ReEDS case
    scenario : str, optional
        Scenario identifier

    Examples
    --------
    Single year:

    >>> config = ReEDSConfig(
    ...     solve_years=2030,
    ...     weather_years=2012,
    ...     case_name="High_Renewable",
    ... )

    Multiple years:

    >>> config = ReEDSConfig(
    ...     solve_years=[2030, 2040, 2050],
    ...     weather_years=[2007, 2012],
    ...     case_name="Multi_Year_Analysis",
    ... )

    Load model defaults separately for use in parser:

    >>> # Load defaults using the class method
    >>> defaults = ReEDSConfig.load_defaults()
    >>> excluded_techs = defaults.get("excluded_techs", [])
    >>>
    >>> # Create config (no defaults field)
    >>> config = ReEDSConfig(
    ...     solve_years=2030,
    ...     weather_years=2012,
    ... )

    See Also
    --------
    r2x_core.plugin_config.PluginConfig : Base configuration class
    r2x_reeds.parser.ReEDSParser : Parser that uses this configuration
    load_defaults : Class method to load default constants from JSON
    """

    # Class variables to customize file locations (can override defaults from PluginConfig)
    FILE_MAPPING_NAME: ClassVar[str] = "file_mapping.json"
    DEFAULTS_FILE_NAME: ClassVar[str] = "defaults.json"

    solve_year: Annotated[
        int | list[int],
        Field(description="Model solve year(s) - automatically converted to list"),
    ]
    weather_year: Annotated[
        int | list[int],
        Field(description="Weather data year(s) - automatically converted to list"),
    ]
    case_name: Annotated[str | None, Field(default=None, description="Case name")] = None
    scenario: Annotated[str, Field(default="base", description="Scenario identifier")] = "base"

    @property
    def primary_solve_year(self) -> int:
        """Get the primary (first) solve year.

        Returns
        -------
        int
            The first solve year in the list
        """
        if isinstance(self.solve_year, list):
            return self.solve_year[0]
        return self.solve_year

    @property
    def primary_weather_year(self) -> int:
        """Get the primary (first) weather year.

        Returns
        -------
        int
            The first weather year in the list
        """
        if isinstance(self.weather_year, list):
            return self.weather_year[0]
        return self.weather_year
