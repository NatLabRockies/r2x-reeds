"""Build ReEDS systems from current core typed sources."""

from __future__ import annotations

from typing import Self, cast

import polars as pl
from loguru import logger
from pydantic import TypeAdapter
from rust_ok import Err, Ok, Result, is_ok

from r2x_core import DataReader, Plugin, PluginContext, System, build_system_from_sources
from r2x_core.exceptions import ReaderError
from r2x_core.models import ParserInstruction
from r2x_core.processors import substitute_placeholders

from .plugin_config import ReEDSConfig, ReEDSDefaults
from .processing import reeds_step_handlers
from .upgrader.data_upgrader import run_reeds_upgrades


class ReEDSParser(Plugin[ReEDSConfig]):
    """Read configured ReEDS sources and build their domain objects."""

    def __init__(self) -> None:
        """Initialize parser-owned configuration state."""
        self._generator_defaults: ReEDSDefaults | None = None
        self._instructions: list[ParserInstruction] | None = None

    @classmethod
    def from_context(cls, ctx: PluginContext[ReEDSConfig]) -> Self:
        """Create a parser bound to one ReEDS plugin context."""
        return cast(Self, super().from_context(ctx))

    def on_validate(self) -> Result[None, Exception]:
        """Load packaged configuration before any input data is read."""
        try:
            assets = self.config.load_config(config_path=self.config.config_path)
        except (OSError, ValueError) as error:
            return Err(error)
        defaults = assets.get("defaults")
        if not isinstance(defaults, dict):
            msg = "ReEDS defaults configuration must be a JSON object"
            return Err(ValueError(msg))
        try:
            substituted_rules = substitute_placeholders(
                assets.get("parser_rules"),
                placeholders=self.config.model_dump(mode="json"),
            )
            if not is_ok(substituted_rules):
                return Err(substituted_rules.err())
            instructions = TypeAdapter(list[ParserInstruction]).validate_python(substituted_rules.value)
            self._generator_defaults = ReEDSDefaults.model_validate(defaults)
        except ValueError as error:
            return Err(error)
        self._instructions = instructions
        return Ok(None)

    def on_prepare(self) -> Result[None, Exception]:
        """Load the configured core DataFile mapping into the run's DataStore."""
        if self.store.data_files:
            return Ok(None)
        try:
            self.store.load_file_mapping(self.config.fmap_path)
        except (OSError, TypeError, ValueError) as error:
            return Err(error)
        return Ok(None)

    def on_upgrade(self) -> Result[System | None, Exception]:
        """Apply the configured ReEDS input upgrades."""
        result = run_reeds_upgrades(store=self.store, ctx=self.ctx)
        if result.is_err():
            return Err(result.err())
        return Ok(None)

    def on_build(self) -> Result[System, Exception]:
        """Read declared sources and build their typed outputs."""
        logger.info("Building ReEDS hierarchy")
        configured_files = tuple(self.store.data_files.values())
        defaults = self._generator_defaults
        instructions = self._instructions
        classification_overrides = self.config.generator_classification_overrides
        if defaults is None or instructions is None:
            msg = "Parser configuration was not validated before building"
            return Err(RuntimeError(msg))

        solve_years = tuple(
            dict.fromkeys(
                (self.config.solve_year,)
                if isinstance(self.config.solve_year, int)
                else self.config.solve_year
            )
        )
        weather_years = tuple(
            dict.fromkeys(
                (self.config.weather_year,)
                if isinstance(self.config.weather_year, int)
                else self.config.weather_year
            )
        )
        capacity_sources = {
            "standard": "online_capacity",
            "degraded": "online_capacity_degraded",
        }
        placeholders = self.config.model_dump(mode="json")
        placeholders.update(
            {
                "default_heat_rate": defaults.default_heat_rate,
                "generator_classification_override_rows": [
                    override.model_dump(mode="json") for override in classification_overrides
                ],
                "excluded_techs": (
                    self.config.excluded_techs
                    if self.config.excluded_techs is not None
                    else defaults.excluded_techs
                ),
                "solve_year_count": len(solve_years),
                "solve_year_rows": [{"solve_year": year} for year in solve_years],
                "requested_solve_weather_year_rows": [
                    {"solve_year": solve_year, "weather_year": weather_year}
                    for solve_year in solve_years
                    for weather_year in weather_years
                ],
                "generator_capacity_source_name": capacity_sources[self.config.generator_capacity_source],
                "resource_supply_curve_datasets": defaults.resource_supply_curve_datasets,
                "reserve_product_rows": [row.model_dump(mode="json") for row in defaults.reserve_products],
                "reserve_provider_exclusion_rows": [
                    row.model_dump(mode="json") for row in defaults.reserve_provider_exclusions
                ],
            }
        )
        try:
            sources = DataReader(step_handlers=reeds_step_handlers()).read_data_files(
                configured_files,
                folder_path=self.store.folder,
                placeholders=placeholders,
            )
        except (OSError, ReaderError, ValueError, pl.exceptions.PolarsError) as error:
            return Err(error)

        try:
            system = build_system_from_sources(
                sources,
                config=self.config,
                instructions=instructions,
                name=self.config.case_name or "ReEDS",
            )
        except (OSError, ValueError, pl.exceptions.PolarsError) as error:
            return Err(error)
        if self.ctx.current_version is not None:
            system.data_format_version = self.ctx.current_version
        system.description = (
            f"ReEDS model system for case '{self.config.case_name}', "
            f"scenario '{self.config.scenario}', "
            f"solve years: {self.config.solve_year}, "
            f"weather years: {self.config.weather_year}"
        )
        return Ok(system)
