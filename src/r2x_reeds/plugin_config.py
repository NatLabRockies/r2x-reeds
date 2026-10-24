"""Configuration for ReEDS parser."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from r2x_core import PluginConfig


class GeneratorClassificationOverride(BaseModel):
    """Exact exception to metadata-derived generator classification."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    technology: str = Field(min_length=1)
    category: Literal[
        "thermal",
        "solar",
        "wind",
        "geothermal",
        "hydro",
        "storage",
        "pumped_storage",
        "imports",
    ]
    is_dispatchable: bool | None = None
    parser_supported: bool | None = None


class GeneratorDefaultValues(BaseModel):
    """Validated generator fallback values used by the declarative mapping."""

    model_config = ConfigDict(strict=True, extra="allow", frozen=True)

    default_heat_rate: Annotated[float, Field(gt=0, allow_inf_nan=False)] = 10.0


class ReserveProduct(BaseModel):
    """One configured reserve product and its profile policy."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    reserve_type: str = Field(min_length=1)
    duration_seconds: int = Field(gt=0)
    time_frame_seconds: int = Field(gt=0)
    vors: float = Field(allow_inf_nan=False)
    direction: Literal["Up", "Down"]
    load_fraction: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
    wind_fraction: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
    solar_fraction: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
    default_load_percentage: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
    default_wind_percentage: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
    default_solar_percentage: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]

    @field_validator("reserve_type")
    @classmethod
    def normalize_reserve_type(cls, value: str) -> str:
        return value.upper()


class ReserveProviderExclusion(BaseModel):
    """One technology category excluded from a reserve product's membership."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    reserve_type: str = Field(min_length=1)
    technology_category: str = Field(min_length=1)

    @field_validator("reserve_type")
    @classmethod
    def normalize_reserve_type(cls, value: str) -> str:
        return value.upper()

    @field_validator("technology_category")
    @classmethod
    def normalize_category(cls, value: str) -> str:
        return value.casefold()


class ReEDSDefaults(BaseModel):
    """Typed subset of packaged ReEDS defaults consumed by ingestion."""

    model_config = ConfigDict(strict=True, extra="ignore", frozen=True)

    excluded_techs: list[str]
    default_values: GeneratorDefaultValues
    resource_supply_curve_datasets: list[str]
    reserve_products: list[ReserveProduct]
    reserve_provider_exclusions: list[ReserveProviderExclusion]

    @field_validator("excluded_techs")
    @classmethod
    def normalize_excluded_technologies(cls, value: list[str]) -> list[str]:
        """Match the case-insensitive category and exclusion contract."""
        return [technology.casefold() for technology in value]

    @field_validator("resource_supply_curve_datasets")
    @classmethod
    def validate_unique_resource_datasets(cls, value: list[str]) -> list[str]:
        """Reject duplicate resource sources before declarative processing."""
        if len(set(value)) != len(value):
            msg = "resource_supply_curve_datasets cannot contain duplicates"
            raise ValueError(msg)
        return value

    @field_validator("reserve_products")
    @classmethod
    def validate_unique_reserve_products(cls, value: list[ReserveProduct]) -> list[ReserveProduct]:
        """Reject repeated product types before generating components."""
        reserve_types = [product.reserve_type.upper() for product in value]
        if len(set(reserve_types)) != len(reserve_types):
            msg = "reserve_products cannot contain duplicate reserve_type values"
            raise ValueError(msg)
        return value

    @property
    def default_heat_rate(self) -> float:
        """Return the validated thermal heat-rate fallback."""
        return self.default_values.default_heat_rate


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
    excluded_techs : list[str], optional
        Technologies to exclude from the parsed system. When omitted, the list
        from ``defaults.json`` is used.

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

    >>> # Load defaults from this configuration instance
    >>> config = ReEDSConfig(solve_year=2030, weather_year=2012)
    >>> defaults = config.load_config()
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

    model_config = ConfigDict(extra="forbid")

    models: Annotated[
        tuple[str, ...],
        Field(description="Module paths used to resolve configured ReEDS component types."),
    ] = ("r2x_reeds.models",)
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
    generator_capacity_source: Literal["standard", "degraded"] = Field(
        default="standard",
        description="Capacity source used to build generator components",
    )
    generator_classification_overrides: list[GeneratorClassificationOverride] = Field(
        default_factory=list,
        description="Exact technology-specific classification exceptions",
    )
    excluded_techs: Annotated[
        list[str] | None,
        Field(
            default=None,
            description=(
                "Technologies to exclude from the parsed system. "
                "When omitted, the defaults.json list is used."
            ),
        ),
    ] = None

    @field_validator("generator_classification_overrides")
    @classmethod
    def validate_unique_classification_overrides(
        cls, value: list[GeneratorClassificationOverride]
    ) -> list[GeneratorClassificationOverride]:
        technologies = [override.technology.casefold() for override in value]
        if len(set(technologies)) != len(technologies):
            msg = "Generator classification overrides must name each technology once"
            raise ValueError(msg)
        return value

    @field_validator("excluded_techs")
    @classmethod
    def normalize_excluded_technologies(cls, value: list[str] | None) -> list[str] | None:
        """Normalize explicit exclusions consistently with packaged defaults."""
        if value is None:
            return None
        return [technology.casefold() for technology in value]

    @computed_field
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
