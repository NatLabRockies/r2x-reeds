"""Build ReEDS systems from current core typed sources."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self, cast

import polars as pl
from infrasys.time_series_models import SingleTimeSeries
from loguru import logger
from pydantic import TypeAdapter
from rust_ok import Err, Ok, Result, is_ok

from r2x_core import (
    DataReader,
    DecodedSource,
    Plugin,
    PluginContext,
    SourceAvailability,
    System,
    TabularSource,
    build_system_from_sources,
)
from r2x_core.exceptions import ReaderError
from r2x_core.models import ParserInstruction
from r2x_core.polars_adapter import PolarsTabularBackend
from r2x_core.processors import substitute_placeholders

from .models.components import ReEDSGenerator, ReEDSVariableGenerator
from .parser_utils import (
    resolve_generator_ramp_rates,
    resolve_psh_storage_durations,
    tech_matches_category,
)
from .plugin_config import ReEDSConfig, ReEDSDefaults
from .upgrader.data_upgrader import run_reeds_upgrades

CONFIGURATION_GUIDANCE = (
    "To update a configuration override, copy the current package configuration "
    "to a new directory and reapply customizations. See the ReEDS configuration reference."
)

POST_ASSEMBLY_VALIDATION_RECORDS = frozenset(
    {
        "hierarchy_required",
        "load_profiles_required",
        "load_profile_peak_validation",
        "generator_capacity_validation",
        "generator_category_hydro_validation",
        "generator_capacity_classification_validation",
        "generator_capacity_count",
        "fom_characteristic_year_validation",
        "fom_switch_cardinality",
        "fom_solve_year_coverage",
        "fom_switch_policy_validation",
        "fom_psh_scalar_validation",
        "generator_fom_validation",
        "hydro_cf_month_validation",
        "hydro_capacity_adjustment_month_validation",
    }
)


class ReEDSParser(Plugin[ReEDSConfig]):
    """Build a ReEDS ``System`` from a configured run directory.

    The parser loads configuration assets, loads the file mapping when the
    ``DataStore`` is empty, applies configured input upgrades, reads and
    assembles sources, and builds domain components from parser instructions.
    Configuration assets can be customized with ``config_path_override``.
    Upgrades may modify run files, so parse a copy when the original inputs must
    remain unchanged.

    Create the parser with a ``PluginContext`` containing ``ReEDSConfig`` and a
    ``DataStore`` rooted at a prepared ReEDS run directory. Replace
    ``Path.cwd()`` below with that run directory before calling ``run()``:

    >>> from pathlib import Path
    >>> from r2x_core import DataStore, PluginContext
    >>> from r2x_reeds import ReEDSConfig, ReEDSParser
    >>> config = ReEDSConfig(solve_year=2032, weather_year=2012)
    >>> store = DataStore(path=Path.cwd())
    >>> context = PluginContext(config=config, store=store)
    >>> parser = ReEDSParser.from_context(context)
    >>> parser.config.solve_year
    2032

    ``parser.run()`` returns a ``PluginContext`` containing the parsed system.
    It raises ``PluginError`` when configuration or input data cannot be
    processed. See the parsing tutorial for a complete end-to-end example.
    """

    def __init__(self) -> None:
        """Initialize parser-owned configuration state."""
        self._generator_defaults: ReEDSDefaults | None = None
        self._instructions: list[ParserInstruction] | None = None
        self._technology_categories: dict[str, Any] = {}

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
        technology_categories = defaults.get("tech_categories")
        if not isinstance(technology_categories, dict):
            msg = "ReEDS defaults must define technology categories"
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
        self._technology_categories = technology_categories
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
        initial_sources: dict[str, DecodedSource] = {}
        if not self.config.use_psh_energy_capacity_duration:
            configured_files = tuple(
                data_file
                for data_file in configured_files
                if not data_file.name.startswith(("psh_energy_capacity", "psh_reference_capacity"))
            )
            psh_source_schemas = {
                "psh_energy_capacity": {
                    "technology": pl.String,
                    "vintage": pl.String,
                    "region": pl.String,
                    "year": pl.Int64,
                    "psh_energy_capacity": pl.Float64,
                },
                "psh_reference_capacity": {
                    "technology": pl.String,
                    "vintage": pl.String,
                    "region": pl.String,
                    "year": pl.Int64,
                    "reference_capacity": pl.Float64,
                },
            }
            for name, schema in psh_source_schemas.items():
                for source_format in ("h5", "csv"):
                    initial_sources[f"{name}_{source_format}"] = TabularSource(
                        pl.DataFrame(schema=schema).lazy(),
                        PolarsTabularBackend(),
                        availability=SourceAvailability.ABSENT,
                    )
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
                "excluded_technology_rows": [
                    {"technology_key": technology.casefold(), "excluded": True}
                    for technology in (
                        self.config.excluded_techs
                        if self.config.excluded_techs is not None
                        else defaults.excluded_techs
                    )
                ],
                "solve_year_count": len(solve_years),
                "solve_year_rows": [{"solve_year": year} for year in solve_years],
                "requested_solve_weather_year_rows": [
                    {"solve_year": solve_year, "weather_year": weather_year}
                    for solve_year in solve_years
                    for weather_year in weather_years
                ],
                "generator_capacity_source_name": capacity_sources[self.config.generator_capacity_source],
                "resource_supply_curve_datasets": defaults.resource_supply_curve_datasets,
                "resource_supply_curve_dataset_rows": [
                    {"technology": technology} for technology in defaults.resource_supply_curve_datasets
                ],
                "reserve_product_rows": [row.model_dump(mode="json") for row in defaults.reserve_products],
                "reserve_provider_exclusion_rows": [
                    row.model_dump(mode="json") for row in defaults.reserve_provider_exclusions
                ],
            }
        )
        validation_names = {
            data_file.name
            for data_file in configured_files
            if data_file.name in POST_ASSEMBLY_VALIDATION_RECORDS
        }
        if validation_names != POST_ASSEMBLY_VALIDATION_RECORDS:
            missing = sorted(POST_ASSEMBLY_VALIDATION_RECORDS - validation_names)
            msg = f"Missing post-assembly validation record(s): {missing}. {CONFIGURATION_GUIDANCE}"
            return Err(ValueError(msg))
        table_mapping_path = self.config.config_path / "table_mapping.json"
        try:
            reader = DataReader()
            sources = reader.read_and_assemble_sources(
                configured_files,
                folder_path=self.store.folder,
                mapping_path=table_mapping_path,
                backend=PolarsTabularBackend(),
                placeholders=placeholders,
                initial_sources=initial_sources,
            )
        except FileNotFoundError as error:
            if error.filename != str(table_mapping_path):
                return Err(error)
            msg = f"Table mapping is missing. {CONFIGURATION_GUIDANCE}"
            guided_error = FileNotFoundError(error.errno, msg, error.filename)
            guided_error.__cause__ = error
            return Err(guided_error)
        except (OSError, ReaderError, KeyError, TypeError, ValueError, pl.exceptions.PolarsError) as error:
            return Err(error)

        try:
            sources = self._prepare_generator_input_policies(sources)
        except (TypeError, ValueError, pl.exceptions.PolarsError) as error:
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
        try:
            self._apply_generator_policies(system)
        except ValueError as error:
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

    def _prepare_generator_input_policies(
        self, sources: Mapping[str, DecodedSource]
    ) -> dict[str, DecodedSource]:
        """Resolve generator rates and optional PSH duration before component assembly."""
        updated_sources = dict(sources)
        backend = PolarsTabularBackend()

        def table(name: str, *, required: bool = False) -> pl.DataFrame | None:
            source = updated_sources.get(name)
            if source is None:
                if required:
                    raise ValueError(f"Required assembled source {name!r} is unavailable")
                return None
            if not isinstance(source, TabularSource):
                raise TypeError(f"Generator source {name!r} is not tabular")
            if source.availability is SourceAvailability.ABSENT:
                if required:
                    raise ValueError(f"Required assembled source {name!r} is absent")
                return None
            if isinstance(source.data, pl.LazyFrame):
                return source.data.collect()
            if isinstance(source.data, pl.DataFrame):
                return source.data
            raise TypeError(f"Generator source {name!r} has unsupported data {type(source.data).__name__}")

        def replace_table(name: str, frame: pl.DataFrame) -> None:
            source = updated_sources.get(name)
            if not isinstance(source, TabularSource):
                raise ValueError(f"Required assembled source {name!r} is not tabular")
            updated_sources[name] = backend.source_with_frame(source, frame.lazy())

        generator_rows = table("generator_rows", required=True)
        assert generator_rows is not None
        required_columns = {"technology", "component_family", "capacity", "year"}
        missing_columns = required_columns.difference(generator_rows.columns)
        if missing_columns:
            raise ValueError(f"Generator rows are missing policy columns: {sorted(missing_columns)}")

        ramp_data = table("ramprate")
        upgrade_links = table("fom_upgrade_links", required=True)
        switches = table("fom_switches", required=True)
        assert upgrade_links is not None and switches is not None
        switch_column = "parameter" if "parameter" in switches.columns else "switch"
        if switch_column not in switches.columns or "value" not in switches.columns:
            raise ValueError("FOM switches must contain a switch name and value")
        water_switch = switches.filter(
            pl.col(switch_column).cast(pl.String).str.to_lowercase() == "gsw_watermain"
        )
        water_enabled = not water_switch.is_empty() and str(water_switch["value"][0]).strip() == "1"

        cooling_links: pl.DataFrame | None = None
        if water_enabled:
            water_links = table("fom_water_upgrade_links", required=True)
            cooling_frames = [
                table("cooling_technology_links"),
                table("cooling_upgrade_technology_links"),
            ]
            assert water_links is not None
            # Standard upgrade identities take precedence over water-specific rows.
            standard_technologies = upgrade_links["technology"].to_list()
            water_links = water_links.filter(~pl.col("technology").is_in(standard_technologies))
            upgrade_links = pl.concat([upgrade_links, water_links], how="diagonal")
            available_cooling_frames = [frame for frame in cooling_frames if frame is not None]
            if available_cooling_frames:
                cooling_links = pl.concat(available_cooling_frames, how="diagonal")

        technologies = generator_rows["technology"].drop_nulls().unique().to_list()
        thermal_technologies = (
            generator_rows.filter(pl.col("component_family") == "thermal")["technology"]
            .drop_nulls()
            .unique()
            .to_list()
        )
        hydro_rows = generator_rows.filter(pl.col("component_family") == "hydro")
        hydro_technologies = hydro_rows["technology"].drop_nulls().unique().to_list()
        dispatchable_hydro = (
            hydro_rows.filter(pl.col("is_dispatchable") == True)["technology"]  # noqa: E712
            .drop_nulls()
            .unique()
            .to_list()
            if "is_dispatchable" in hydro_rows.columns
            else []
        )
        categories = {
            "thermal": {"exact": thermal_technologies},
            "hydro": {"exact": hydro_technologies},
            "hydro_dispatchable": {"exact": dispatchable_hydro},
        }
        ramp_result = resolve_generator_ramp_rates(
            technologies,
            ramp_data,
            upgrade_links,
            categories,
            cooling_links=cooling_links,
        )
        if ramp_result.is_err():
            raise ValueError(str(ramp_result.unwrap_err()))
        resolved_rates = ramp_result.unwrap()
        for source_name in ("generator_thermal_rows", "generator_hydro_rows"):
            rows = table(source_name, required=True)
            assert rows is not None
            if rows.is_empty():
                continue
            rows = rows.join(
                resolved_rates.rename({"ramp_rate": "__resolved_ramp_rate"}),
                on="technology",
                how="left",
                validate="m:1",
            ).with_columns(pl.col("__resolved_ramp_rate").alias("ramp_rate")).drop("__resolved_ramp_rate")
            replace_table(source_name, rows)

        if not self.config.use_psh_energy_capacity_duration:
            return updated_sources
        category_column = (
            pl.col("category").cast(pl.String).str.to_lowercase() == "pumped_storage"
            if "category" in generator_rows.columns
            else pl.lit(False)
        )
        category_column = category_column | pl.col("technology").map_elements(
            lambda technology: tech_matches_category(
                technology, "pumped_storage", self._technology_categories
            ),
            return_dtype=pl.Boolean,
        )
        psh_capacity = generator_rows.filter(
            category_column
            & (pl.col("capacity") > 0)
            & (pl.col("capacity") >= self.config.drop_gen_capacity_threshold)
        ).select("technology", "vintage", "region", "year", "capacity")
        if psh_capacity.is_empty():
            return updated_sources

        energy = table("psh_energy_capacity")
        reference = table("psh_reference_capacity")
        duration_result = resolve_psh_storage_durations(
            psh_capacity,
            energy.lazy() if energy is not None else None,
            reference.lazy() if reference is not None else None,
        )
        if duration_result.is_err():
            raise ValueError(str(duration_result.unwrap_err()))
        durations = duration_result.unwrap().collect().rename({"psh_storage_duration": "__psh_duration"})

        storage_rows = table("generator_rows", required=True)
        assert storage_rows is not None
        storage_rows = storage_rows.join(
            durations,
            on=["technology", "vintage", "region", "year"],
            how="left",
            validate="m:1",
        ).with_columns(
            pl.coalesce(["__psh_duration", "storage_duration"]).alias("storage_duration")
        )
        storage_rows = storage_rows.filter(
            (pl.col("component_family") == "storage") & pl.col("storage_duration").is_not_null()
        )
        output = table("generator_storage_rows", required=True)
        assert output is not None
        output_columns = output.columns
        if "solve_year" in output_columns and "year" not in output_columns:
            storage_rows = storage_rows.rename({"year": "solve_year"})
        storage_rows = storage_rows.select(output_columns)
        replace_table("generator_storage_rows", storage_rows)
        return updated_sources

    def _apply_generator_policies(self, system: System) -> None:
        """Apply configured capacity filtering and renewable profile adjustments."""
        capacity_threshold = self.config.drop_gen_capacity_threshold
        if capacity_threshold > 0:
            generators = list(system.get_components(ReEDSGenerator))
            dropped = 0
            for generator in generators:
                if generator.capacity < capacity_threshold:
                    system.remove_component(generator)
                    dropped += 1
            logger.info(
                "Dropped {} generators below the {} MW capacity threshold", dropped, capacity_threshold
            )

        if not (self.config.apply_cf_adjustment or self.config.apply_ilr_adjustment):
            return

        for generator in system.get_components(ReEDSVariableGenerator):
            keys = system.list_time_series_keys(generator, name="max_active_power")
            if not keys:
                continue

            cf_adjustment = generator.capacity_factor_adjustment
            ilr_adjustment = generator.inverter_loading_ratio
            technology = generator.technology.casefold()

            for key in keys:
                time_series = system.get_time_series_by_key(generator, key)
                data = time_series.data.copy()
                if self.config.apply_cf_adjustment:
                    if cf_adjustment is None:
                        raise ValueError(f"Missing CF adjustment for {generator.name}")
                    data *= cf_adjustment
                if self.config.apply_ilr_adjustment and "pv" in technology:
                    if ilr_adjustment is None:
                        raise ValueError(f"Missing ILR adjustment for {generator.name}")
                    data *= ilr_adjustment
                    if data.size and float(data.max()) > generator.capacity:
                        logger.warning(
                            "PV profile for tech {} in region {} exceeds generator capacity after ILR adjustment",
                            generator.technology,
                            generator.region.name,
                        )

                adjusted = SingleTimeSeries.from_array(
                    data=data,
                    name=time_series.name,
                    initial_timestamp=time_series.initial_timestamp,
                    resolution=time_series.resolution,
                )
                system.remove_time_series(generator, name=time_series.name, **key.features)
                system.add_time_series(adjusted, generator, **key.features)
