"""Configuration for ReEDS parser."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from r2x_core import PluginConfig


class ReEDSConfig(PluginConfig):
    """Configuration for ReEDS model parser.

    This configuration class defines all parameters needed to parse
    ReEDS model data, including year information and model-specific settings.
    Model-specific defaults and constants are loaded from configuration files
    in the `config/` directory relative to this module.

    Parameters
    ----------
    solve_year : int | list[int]
        Model solve year(s) (e.g., 2030, [2030, 2040, 2050])
    weather_year : int | list[int]
        Weather data year(s) used for time series profiles (e.g., 2012, [2007, 2012])
    case_name : str, optional
        Name of the ReEDS case
    scenario : str, optional
        Scenario identifier

    Examples
    --------
    Single year:

    >>> config = ReEDSConfig(
    ...     solve_year=2030,
    ...     weather_year=2012,
    ...     case_name="High_Renewable",
    ... )

    Multiple years:

    >>> config = ReEDSConfig(
    ...     solve_year=[2030, 2040, 2050],
    ...     weather_year=[2007, 2012],
    ...     case_name="Multi_Year_Analysis",
    ... )

    Load model defaults separately for use in parser:

    >>> # Load defaults using the class method
    >>> defaults = ReEDSConfig.load_config()
    >>> excluded_techs = defaults.get("defaults", {}).get("excluded_techs", [])
    >>>
    >>> # Create config
    >>> config = ReEDSConfig(
    ...     solve_year=2030,
    ...     weather_year=2012,
    ... )

    See Also
    --------
    r2x_core.PluginConfig : Base configuration class
    r2x_reeds.parser.ReEDSParser : Parser that uses this configuration
    """

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
