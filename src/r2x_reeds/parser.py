"""
ReEDS parser for building infrasys.System from ReEDS model output.

The :class:`ReEDSParser` is used to build an infrasys.System from ReEDS model output
using the new Plugin[ReEDSConfig] pattern with lifecycle hooks.
"""

from __future__ import annotations

from itertools import chain
from typing import Any, Self, cast

import polars as pl
from loguru import logger
from rust_ok import Err, Ok, Result

from r2x_core import (
    DatasetSource,
    Plugin,
    PluginContext,
    RulePlan,
    SelectedMappingRoute,
    System,
    apply_mapping_records,
    apply_rules_to_context,
)

from .plugin_config import ReEDSConfig
from .rules_helper import create_parser_context
from .upgrader.data_upgrader import run_reeds_upgrades


class ReEDSParser(Plugin[ReEDSConfig]):
    """Parser for ReEDS model data using the Plugin[ReEDSConfig] pattern.

    This parser builds an :class:`infrasys.System` from ReEDS model output through three main phases:

    1. **Validation** (:meth:`on_validate`):
       - Presence of required datasets
       - Validity of configured solve and weather years
       - Loading and parsing of configuration assets

    2. **Preparation** (:meth:`on_prepare`):
       - Parser context with configuration and defaults
       - Configured generator datasets

    3. **Building** (:meth:`on_build`):
       - Regions from hierarchy data with regional attributes
       - Generators split into renewable (aggregated by tech-region) and non-renewable (with vintage)
       - Transmission interfaces and lines with bi-directional ratings
       - Loads with peak demand by region
       - Reserves by transmission region and type
       - Emissions as supplemental attributes on generators
       - Time series data (load profiles, capacity factors, reserve requirements, hydro profiles)
       - System metadata and description

    Key Implementation Details
    --------------------------
    - Renewable generators are aggregated by technology and region (no vintage)
    - Non-renewable generators retain vintage information
    - Reserve requirements are calculated dynamically based on wind capacity, solar capacity,
      and load data with configurable percentage contributions
    - Time series data is filtered to match configured weather years and solve years
    - Component caches are used during building for efficient cross-referencing

    Parameters
    ----------
    config : ReEDSConfig
        ReEDS-specific configuration with solve years, weather years, etc.
    store : DataStore
        Initialized DataStore with ReEDS file mappings loaded
    overrides : dict[str, Any] | None, optional
        Configuration overrides to apply, by default None

    Attributes
    ----------
    config : ReEDSConfig
        The ReEDS configuration instance
    store : DataStore
        The DataStore for accessing ReEDS data files

    Methods
    -------
    on_validate()
        Validate input data and configuration before building the system
    on_prepare()
        Prepare configuration and component datasets
    on_build()
        Build and return the complete infrasys.System

    See Also
    --------
    :class:`Plugin` : Parent class with lifecycle hooks
    :class:`ReEDSConfig` : Configuration class for ReEDS parser
    :class:`DataStore` : Data storage and access interface

    Examples
    --------
    Build a ReEDS system from test data:

    >>> from pathlib import Path
    >>> from r2x_core import PluginContext, DataStore
    >>> from r2x_reeds import ReEDSConfig, ReEDSParser
    >>>
    >>> config = ReEDSConfig(solve_year=2030, weather_year=2012, case_name="High_Renewable")
    >>> store = DataStore(path=Path("tests/data/test_Pacific"))
    >>> ctx = PluginContext(config=config, store=store)
    >>> parser = ReEDSParser.from_context(ctx)
    >>> result_ctx = parser.run()
    >>> system = result_ctx.system

    Notes
    -----
    The parser uses internal caches for regions and generators to optimize cross-referencing
    during component construction. These caches are populated during the build phase
    and are used for all subsequent operations.
    """

    def __init__(self) -> None:
        """Initialize the ReEDS parser with internal state.

        Note: Configuration and store are provided via from_context() class method.
        """
        self._config_assets: dict[str, Any] | None = None
        self._defaults: dict[str, Any] = {}
        self.rule_plan: RulePlan | None = None

        # Internal caches for component building
        self._variable_generator_df: pl.DataFrame | None = None
        self._non_variable_generator_df: pl.DataFrame | None = None
        self._ctx: Any = None

        # Technology categorization
        self._tech_categories: dict[str, Any] = {}
        self._excluded_techs: list[str] = []

    @classmethod
    def from_context(cls, ctx: PluginContext[ReEDSConfig]) -> Self:
        """Create the parser from its configured context."""
        return cast(Self, super().from_context(ctx))

    def on_validate_config(self) -> Result[None, str]:
        """Validate configuration assets before upgrades or data I/O."""
        logger.debug("Validating parser configuration")
        logger.trace(
            "Solve year(s): {}, weather year(s): {}, case: {}, scenario: {}",
            self.config.solve_year,
            self.config.weather_year,
            self.config.case_name,
            self.config.scenario,
        )

        res = self._ensure_config_assets()
        if res.is_err():
            return Err(str(res.err()))
        if self.rule_plan is not None:
            return Ok(None)

        config_assets = self._config_assets
        if config_assets is None:
            return Err("Parser configuration assets are unavailable")
        plan_result = RulePlan.from_mapping(
            config_assets.get("parser_rules"),
            context=self.ctx,
        )
        if plan_result.is_err():
            return Err(str(plan_result.err()))
        plan = plan_result.unwrap()
        load_profile_source = self._get_load_profile_source(plan)
        if load_profile_source.is_err():
            return Err(str(load_profile_source.err()))
        self.rule_plan = plan
        return Ok(None)

    def on_upgrade(self) -> Result[System | None, str]:
        """Run ReEDS file upgrades before input validation."""
        logger.debug("Determining if upgrade is needed.")
        result = run_reeds_upgrades(store=self.store, ctx=self.ctx)
        if result.is_err():
            return Err(str(result.err()))
        return Ok(None)

    def _get_load_profile_source(self, plan: RulePlan) -> Result[str, str]:
        """Resolve the required physical source shared by load peaks and profiles."""
        match plan.get_rule("load"):
            case Err(error):
                return Err(str(error))
            case Ok(resolved_rule):
                source = resolved_rule.rule.source

        if not isinstance(source, DatasetSource):
            return Err("Load Rule must use a DatasetSource")

        try:
            table = self.store.get_table(source.dataset)
        except KeyError:
            return Err(f"Load Rule dataset {source.dataset!r} must reference a prepared table")

        required_load_columns = {"region", "max_active_power"}
        missing_non_null_columns = sorted(required_load_columns - set(table.non_null_columns))
        if missing_non_null_columns:
            return Err(
                f"Load Rule prepared table {source.dataset!r} must declare non-null columns: "
                f"{missing_non_null_columns}"
            )

        def physical_root(dataset: str) -> str:
            """Follow named-table roots to the configured physical input."""
            while dataset in self.store.prepared_tables:
                dataset = self.store.get_table(dataset).source
            return dataset

        peaks_source = physical_root(source.dataset)
        match plan.get_rule("load_profile"):
            case Err(error):
                return Err(str(error))
            case Ok(profile_rule):
                profile_dataset = profile_rule.rule.source
        if not isinstance(profile_dataset, DatasetSource):
            return Err("Load profile Rule must use a DatasetSource")
        if profile_dataset.dataset not in self.store.prepared_tables:
            return Err(f"Load profile Rule dataset {profile_dataset.dataset!r} must be a prepared table")
        profiles_source = physical_root(profile_dataset.dataset)
        if profiles_source != peaks_source:
            return Err(
                "Load peak and profile prepared tables must resolve to the same physical source, "
                f"got {peaks_source!r} and {profiles_source!r}"
            )
        if peaks_source not in self.store.list_files():
            return Err(f"Load profile tables must resolve to a physical source, got {peaks_source!r}")
        if self.store.is_optional(peaks_source):
            return Err(f"Load profile source {peaks_source!r} must be a required physical dataset")
        return Ok(peaks_source)

    def on_validate(self) -> Result[None, str]:
        """Validate input data after upgrades, before building the system.

        Performs comprehensive validation including:
        - Presence of required datasets
        - Validity of configured solve and weather years
        - Rule validation from parser configuration (already loaded)

        Returns
        -------
        Result[None, str]
            Ok() if all validation checks pass, Err() with detailed error message otherwise
        """
        logger.debug("Validating input files")

        config_result = self.on_validate_config()
        if config_result.is_err():
            return Err(str(config_result.err()))

        try:
            self.store.validate_input_data(placeholders=self.config.model_dump())
        except (KeyError, OSError, TypeError, ValueError, pl.exceptions.PolarsError) as error:
            return Err(str(error))
        return Ok(None)

    def on_prepare(self) -> Result[None, str]:
        """Prepare configuration and generator component datasets.

        Initializes the parser context and configured generator tables.

        Returns
        -------
        Result[None, str]
            Ok() on successful preparation, Err() with error message if any step fails
        """
        logger.trace("Preparing parser data caches and context")
        self._initialize_caches()
        logger.trace("Parser caches initialized")

        res = self._initialize_parser_globals()
        if res.is_err():
            return Err(str(res.err()))

        # Create a temporary system for context creation
        temp_system = System(name=self.config.case_name or "ReEDS")
        self._ctx = create_parser_context(temp_system, self.config, self._defaults, store=self._ctx.store)
        logger.trace("Parser context created")

        generator_data_result = self._prepare_generator_datasets()
        if generator_data_result.is_err():
            return Err(str(generator_data_result.err()))
        logger.trace("Generator datasets prepared")

        return Ok(None)

    def on_build(self) -> Result[System, str]:
        """Build and return the complete infrasys.System.

        Constructs all system components in dependency order:
        1. Regions (required by all other components)
        2. Generators (requires regions)
        3. Transmission interfaces and lines
        4. Loads (requires regions)
        5. Reserves and reserve regions (requires transmission regions)
        6. Emissions (requires generators)
        7. Time series data (load profiles, capacity factors, reserve requirements, hydro budgets)
        8. Post-processing (metadata and description)

        Returns
        -------
        Result[System, str]
            Ok(system) with the constructed power system, or Err() with error message
        """
        logger.info("Building ReEDS system")
        system = System(name=self.config.case_name or "ReEDS")
        if self._ctx is None:
            return Err("Parser context is missing")
        self._ctx.system = system
        self._ctx.target_system = system
        if self.rule_plan is None:
            return Err("RulePlan was not validated before building")

        region_result = apply_rules_to_context(
            self._ctx,
            on_error="stop",
            plan=self.rule_plan,
            stage="regions",
        )
        if not region_result.success:
            failure = next(
                (
                    item.error
                    for item in region_result.rule_results
                    if not item.success and item.error is not None
                ),
                "Region Rule execution failed",
            )
            return Err(failure)

        reserve_result = apply_rules_to_context(
            self._ctx,
            on_error="stop",
            plan=self.rule_plan,
            stage="reserves",
        )
        if not reserve_result.success:
            failure = next(
                (
                    item.error
                    for item in reserve_result.rule_results
                    if not item.success and item.error is not None
                ),
                "Reserve Rule execution failed",
            )
            return Err(failure)

        if self._variable_generator_df is None or self._non_variable_generator_df is None:
            return Err("Generator datasets were not prepared")
        generator_rows = chain.from_iterable(
            frame.iter_rows(named=True)
            for frame in (self._variable_generator_df, self._non_variable_generator_df)
        )
        match apply_mapping_records(
            generator_rows,
            plan=self.rule_plan,
            route=SelectedMappingRoute(name="generators"),
            context=self._ctx,
        ):
            case Err(error):
                return Err(str(error))
            case Ok(stats):
                logger.info(
                    "Attached {} generators; skipped {} by configured duplicate/filter policy",
                    stats.converted,
                    stats.skipped,
                )

        resource_result = apply_rules_to_context(
            self._ctx,
            on_error="stop",
            plan=self.rule_plan,
            stage="resources",
        )
        if not resource_result.success:
            failure = next(
                (
                    item.error
                    for item in resource_result.rule_results
                    if not item.success and item.error is not None
                ),
                "Resource Rule execution failed",
            )
            return Err(failure)

        transmission_result = apply_rules_to_context(
            self._ctx,
            on_error="stop",
            plan=self.rule_plan,
            stage="transmission",
        )
        if not transmission_result.success:
            failure = next(
                (
                    item.error
                    for item in transmission_result.rule_results
                    if not item.success and item.error is not None
                ),
                "Transmission Rule execution failed",
            )
            return Err(failure)

        load_result = apply_rules_to_context(
            self._ctx,
            on_error="stop",
            plan=self.rule_plan,
            stage="loads",
        )
        if not load_result.success:
            failure = next(
                (
                    item.error
                    for item in load_result.rule_results
                    if not item.success and item.error is not None
                ),
                "Load Rule execution failed",
            )
            return Err(failure)

        emission_result = apply_rules_to_context(
            self._ctx,
            on_error="stop",
            plan=self.rule_plan,
            stage="emissions",
        )
        if not emission_result.success:
            failure = next(
                (
                    item.error
                    for item in emission_result.rule_results
                    if not item.success and item.error is not None
                ),
                "Emission Rule execution failed",
            )
            return Err(failure)

        # Attach time series data
        profile_result = apply_rules_to_context(
            self._ctx,
            on_error="stop",
            plan=self.rule_plan,
            stage="profiles",
        )
        if not profile_result.success:
            failure = next(
                (
                    item.error
                    for item in profile_result.rule_results
                    if not item.success and item.error is not None
                ),
                "Profile Rule execution failed",
            )
            return Err(failure)

        hydro_profile_result = apply_rules_to_context(
            self._ctx,
            on_error="stop",
            plan=self.rule_plan,
            stage="hydro_profiles",
        )
        if not hydro_profile_result.success:
            failure = next(
                (
                    item.error
                    for item in hydro_profile_result.rule_results
                    if not item.success and item.error is not None
                ),
                "Hydro profile Rule execution failed",
            )
            return Err(failure)

        reserve_profile_result = apply_rules_to_context(
            self._ctx,
            on_error="stop",
            plan=self.rule_plan,
            stage="reserve_profiles",
        )
        if not reserve_profile_result.success:
            failure = next(
                (
                    item.error
                    for item in reserve_profile_result.rule_results
                    if not item.success and item.error is not None
                ),
                "Reserve profile Rule execution failed",
            )
            return Err(failure)

        # Post-process the system
        self._postprocess_system(system)

        logger.info("ReEDS system build complete")
        return Ok(system)

    def _postprocess_system(self, system: System) -> None:
        """Perform post-processing and finalization of the constructed system.

        Sets system-level metadata and logs summary statistics:
        - Data format version (from meta.csv tag column)
        - System description incorporating case name, scenario, solve/weather years
        - Component statistics and system validation information

        This is the final step after components and time series are built,
        ensuring the system is properly documented and ready for export.
        """
        logger.info("Post-processing ReEDS system...")
        logger.trace("Setting data format version to {}", self.ctx.current_version)

        if self.ctx.current_version is not None:
            system.data_format_version = self.ctx.current_version
        system.description = (
            f"ReEDS model system for case '{self.config.case_name}', "
            f"scenario '{self.config.scenario}', "
            f"solve years: {self.config.solve_year}, "
            f"weather years: {self.config.weather_year}"
        )

        # Count component types for summary
        component_counts = {
            comp_type.__name__: sum(1 for _ in system.get_components(comp_type))
            for comp_type in system.get_component_types()
        }

        logger.info("System name: {}", system.name)
        logger.info(
            "System composition: {} regions, {} generators, {} demands, {} reserves, {} transmission lines ({} total components)",
            component_counts.get("ReEDSRegion", 0),
            component_counts.get("ReEDSGenerator", 0),
            component_counts.get("ReEDSDemand", 0),
            component_counts.get("ReEDSReserve", 0),
            component_counts.get("ReEDSTransmissionLine", 0),
            sum(component_counts.values()),
        )
        logger.info("Post-processing complete")

    def _ensure_config_assets(self) -> Result[None, str]:
        """Load and cache plugin config assets."""
        if self._config_assets is not None:
            logger.trace("Config assets already loaded.")
            return Ok(None)

        try:
            assets = self.config.load_config()
        except FileNotFoundError as exc:
            return Err(f"Plugin config files missing: {exc}")

        self._config_assets = assets
        self._defaults = assets.get("defaults", {})
        logger.trace("Config assets loading successful")
        return Ok(None)

    def _initialize_caches(self) -> None:
        """Reset parser caches for a fresh build."""
        self._variable_generator_df = None
        self._non_variable_generator_df = None

    def _initialize_parser_globals(self) -> Result[None, str]:
        """Initialize parser configuration, rules, and metadata from loaded assets."""
        res = self._ensure_config_assets()
        if res.is_err():
            return res

        res = self.on_validate_config()
        if res.is_err():
            return res

        res = self._prepare_default_metadata()
        if res.is_err():
            return res
        logger.trace("Parser global variables set")
        return Ok(None)

    def _prepare_default_metadata(self) -> Result[None, str]:
        """Initialize important configuration from the parser."""
        self._tech_categories = self._defaults.get("tech_categories", {})
        configured_excluded_techs = self.config.excluded_techs
        self._excluded_techs = list(
            configured_excluded_techs
            if configured_excluded_techs is not None
            else self._defaults.get("excluded_techs", [])
        )
        return Ok(None)

    def _prepare_generator_datasets(self) -> Result[None, str]:
        """Execute configured generator recipes and retain component-mapping rows."""
        placeholders = {
            "solve_year": self.config.solve_year,
            "weather_year": self.config.weather_year,
            "technology_categories": self._tech_categories,
            "excluded_technologies": self._excluded_techs,
            "default_heat_rate": self._defaults.get("default_values", {}).get("default_heat_rate"),
        }
        try:
            frames = self.store.prepare_tables(
                ("variable_generator_rows", "non_variable_generator_rows"),
                placeholders=placeholders,
                context=self._ctx,
            )
        except (KeyError, OSError, TypeError, ValueError, pl.exceptions.PolarsError) as exc:
            return Err(f"Failed to prepare configured generator datasets: {exc}")

        variable_rows = frames["variable_generator_rows"]
        non_variable_rows = frames["non_variable_generator_rows"]
        if variable_rows is None or non_variable_rows is None:
            return Err("No capacity data found")

        try:
            variable_df = variable_rows.collect()
            non_variable_df = non_variable_rows.collect()
        except (OSError, ValueError, pl.exceptions.PolarsError) as exc:
            return Err(f"Failed to collect configured generator datasets: {exc}")
        if variable_df.is_empty() and non_variable_df.is_empty():
            return Err("Generator data is empty after configured policy filters")

        self._variable_generator_df = variable_df
        self._non_variable_generator_df = non_variable_df
        logger.trace(
            "Prepared generator datasets - variable rows: {}, non-variable rows: {}",
            variable_df.height,
            non_variable_df.height,
        )
        return Ok(None)
