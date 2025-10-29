"""
Example usage of ReEDSParser.

The :class:`ReEDSParser` is used to build an infrasys.System from ReEDS model output.

>>> import json
>>> from pathlib import Path
>>> from r2x_core.store import DataStore
>>> from r2x_reeds.config import ReEDSConfig
>>> from r2x_reeds.parser import ReEDSParser
>>>
>>> # Load configuration and create DataStore
>>> config = ReEDSConfig(solve_years=2030, weather_years=2012, case_name="High_Renewable")
>>> mapping_path = ReEDSConfig.get_file_mapping_path()
>>> data_folder = Path("tests/data/test_Pacific")
>>> data_store = DataStore.from_json(mapping_path, folder=data_folder)
>>>
>>> # Create parser and build system
>>> parser = ReEDSParser(config, data_store=data_store, name="ReEDS_System")
>>> system = parser.build_system()
>>> regions = list(system.get_components(ReEDSRegion))
>>> print(f"Built system with {len(regions)} regions")
Built system with 5 regions
"""

from __future__ import annotations

import calendar
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

import numpy as np
import polars as pl
from infrasys import Component
from infrasys.time_series_models import SingleTimeSeries
from loguru import logger

from r2x_core import Err, Ok, ParserError, Result, ValidationError
from r2x_core.parser import BaseParser
from r2x_reeds.parser_utils import (
    get_technology_category,
    monthly_to_hourly_polars,
    tech_matches_category,
)
from r2x_reeds.upgrader.helpers import LATEST_COMMIT

from .models.base import FromTo_ToFrom
from .models.components import (
    ReEDSDemand,
    ReEDSEmission,
    ReEDSGenerator,
    ReEDSInterface,
    ReEDSRegion,
    ReEDSReserve,
    ReEDSTransmissionLine,
)
from .models.enums import EmissionType, ReserveDirection, ReserveType

if TYPE_CHECKING:
    from r2x_core.store import DataStore

    from .config import ReEDSConfig


class ReEDSParser(BaseParser):
    """Parser for ReEDS model data following r2x-core framework patterns.

    This parser builds an :class:`infrasys.System` from ReEDS model output through three main phases:

    1. **Component Building** (:meth:`build_system_components`):
       - Regions from hierarchy data with regional attributes
       - Generators split into renewable (aggregated by tech-region) and non-renewable (with vintage)
       - Transmission interfaces and lines with bi-directional ratings
       - Loads with peak demand by region
       - Reserves by transmission region and type
       - Emissions as supplemental attributes on generators

    2. **Time Series Attachment** (:meth:`build_time_series`):
       - Load profiles filtered by weather year and solve year
       - Renewable capacity factors from CF data
       - Reserve requirements calculated from wind/solar/load contributions

    3. **Post-Processing** (:meth:`post_process_system`):
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
    data_store : DataStore
        Initialized DataStore with ReEDS file mappings loaded
    auto_add_composed_components : bool, default=True
        Whether to automatically add composed components
    skip_validation : bool, default=False
        Skip Pydantic validation for performance (use with caution)
    **kwargs
        Additional keyword arguments passed to parent :class:`BaseParser`

    Attributes
    ----------
    system : infrasys.System
        The constructed power system model
    config : ReEDSConfig
        The ReEDS configuration instance
    data_store : DataStore
        The DataStore for accessing ReEDS data files

    Methods
    -------
    build_system()
        Build and return the complete infrasys.System
    build_system_components()
        Construct all system components (regions, generators, transmission, loads, reserves)
    build_time_series()
        Attach time series data to components
    post_process_system()
        Apply post-processing steps to the system

    See Also
    --------
    :class:`BaseParser` : Parent class with core system building logic
    :class:`ReEDSConfig` : Configuration class for ReEDS parser
    :class:`DataStore` : Data storage and access interface

    Examples
    --------
    Build a ReEDS system from test data:

    >>> from pathlib import Path
    >>> from r2x_core.store import DataStore
    >>> from r2x_reeds.config import ReEDSConfig
    >>> from r2x_reeds.parser import ReEDSParser
    >>>
    >>> config = ReEDSConfig(solve_years=2030, weather_years=2012, case_name="High_Renewable")
    >>> mapping_path = ReEDSConfig.get_file_mapping_path()
    >>> data_folder = Path("tests/data/test_Pacific")
    >>> data_store = DataStore.from_json(mapping_path, folder=data_folder)
    >>> parser = ReEDSParser(config, data_store=data_store, name="ReEDS_System")
    >>> system = parser.build_system()

    Notes
    -----
    The parser uses internal caches for regions and generators to optimize cross-referencing
    during component construction. These caches are populated during :meth:`build_system_components`
    and are used for all subsequent operations.
    """

    def __init__(
        self,
        /,
        config: ReEDSConfig,
        *,
        data_store: DataStore,
        auto_add_composed_components: bool = True,
        skip_validation: bool = False,
        **kwargs,
    ) -> None:
        """Initialize ReEDS parser."""
        super().__init__(
            config=config,
            data_store=data_store,
            auto_add_composed_components=auto_add_composed_components,
            skip_validation=skip_validation,
            **kwargs,
        )

    def validate_inputs(self) -> Result[None, ValidationError]:
        """Validate input data and configuration before building system.

        Checks that:
        - Required data files (modeled_years, hour_map) are non-empty
        - Configured solve_years exist in the modeled data
        - Configured weather_years exist in the hour_map data

        Returns
        -------
        Result[None, ValidationError]
            Ok() if all validations pass, Err() with ValidationError details if any fail
        """
        assert self._store, "REeDS parser requires DataStore object."

        modeled_years = self.read_data_file("modeled_years")
        if modeled_years.limit(1).collect().is_empty():
            modeled_data_meta = self._store["modeled_years"]
            msg = f"modeled_years data is empty. Check that file {modeled_data_meta.fpath} has data."
            return Err(error=ValidationError(msg))
        hour_map_data = self.read_data_file("hour_map")
        if hour_map_data.limit(1).collect().is_empty():
            hour_map_meta = self._store["hour_map"]
            msg = f"hour_map data is empty. Check that file {hour_map_meta.fpath} has data."
            return Err(ValidationError(msg))

        solve_years = (
            [self.config.solve_year]
            if isinstance(self.config.solve_year, int)
            else list(self.config.solve_year)
        )

        model_solve_years = set(modeled_years.collect()["modeled_years"].to_list())
        missing_solve_years = [y for y in solve_years if y not in model_solve_years]
        if missing_solve_years:
            modeled_data_meta = self._store["modeled_years"]
            msg = f"Solve year(s) {missing_solve_years} not found in {modeled_data_meta.fpath}. "
            msg += f"Available years: {sorted(model_solve_years)}"
            return Err(ValidationError(msg))

        weather_years = (
            [self.config.weather_year]
            if isinstance(self.config.weather_year, int)
            else list(self.config.weather_year)
        )
        model_weather_years = set(
            hour_map_data.select(pl.col("year")).unique().collect().to_series().to_list()
        )
        missing_weather_years = [y for y in weather_years if y not in model_weather_years]
        if missing_weather_years := [y for y in weather_years if y not in model_weather_years]:
            hour_map_meta = self._store["hour_map"]
            msg = f"Weather year(s) {missing_weather_years} not found in {hour_map_meta.fpath}. "
            msg += f"Available years: {sorted(model_weather_years)}"
            return Err(ValidationError(msg))

        logger.debug("Input validation complete")
        return Ok()

    def prepare_data(self) -> Result[None, ParserError]:
        """Prepare and normalize configuration and time-related data.

        Initializes internal data structures required for component building:
        - Normalizes solve_years and weather_years to lists
        - Creates hourly and daily time indices based on primary weather year
        - Builds lookup tables for month/year/day/hour calculations
        - Loads default technology categories and exclusion lists
        - Initializes component caches for efficient cross-referencing

        Returns
        -------
        Result[None, ParserError]
            Ok() on success, Err() with ParserError on failure
        """
        self.solve_years = (
            [self.config.solve_year]
            if isinstance(self.config.solve_year, int)
            else list(self.config.solve_year)
        )

        self.weather_years = (
            [self.config.weather_year]
            if isinstance(self.config.weather_year, int)
            else list(self.config.weather_year)
        )

        weather_year = self.config.primary_weather_year

        self.hourly_time_index = np.arange(f"{weather_year}", f"{weather_year + 1}", dtype="datetime64[h]")
        self.daily_time_index = np.arange(f"{weather_year}", f"{weather_year + 1}", dtype="datetime64[D]")
        self.initial_timestamp = self.hourly_time_index[0].astype("datetime64[s]").astype(datetime)
        self.month_map = {calendar.month_abbr[i].lower(): i for i in range(1, 13)}
        self.year_month_day_hours = pl.DataFrame(
            {
                "year": [y for y in self.solve_years for _ in range(1, 13)],
                "month_num": [m for _ in self.solve_years for m in range(1, 13)],
                "days_in_month": [
                    calendar.monthrange(y, m)[1] for y in self.solve_years for m in range(1, 13)
                ],
                "hours_in_month": [
                    calendar.monthrange(y, m)[1] * 24 for y in self.solve_years for m in range(1, 13)
                ],
            }
        )

        self.defaults = self.config.load_defaults()
        self.technology_categories = self.defaults.get("tech_categories")
        self.excluded_technologies = self.defaults.get("excluded_techs", [])

        logger.debug(
            "Created time indices for weather year {}: {} hours, {} days starting at {}",
            weather_year,
            len(self.hourly_time_index),
            len(self.daily_time_index),
            self.initial_timestamp,
        )

        self._region_cache: dict[str, Any] = {}
        self._generator_cache: dict[str, Any] = {}
        self._interface_cache: dict[str, Any] = {}
        return Ok()

    def build_system_components(self) -> Result[None, ParserError]:
        """Create all system components from ReEDS data.

        Components are built in dependency order:
        regions → generators → transmission → loads → reserves → emissions
        """
        logger.info("Building ReEDS system components...")

        self._build_regions()
        self._build_generators()
        self._build_transmission()
        self._build_loads()
        self._build_reserves()
        self._build_emissions()

        total_components = len(list(self.system.get_components(Component)))
        logger.info(
            "Built {} total components: regions, generators, transmission, loads, reserves, emissions",
            total_components,
        )
        return Ok()

    def build_time_series(self) -> Result[None, ParserError]:
        """Attach time series data to all system components.

        Applies time series in order:
        1. Load profiles to demand components
        2. Renewable capacity factors to renewable generators
        3. Reserve requirement profiles
        4. Hydro budget constraints

        Returns
        -------
        None
        """
        logger.info("Building time series data...")
        self._attach_load_profiles()
        self._attach_renewable_profiles()
        self._attach_reserve_profiles()
        self._attach_hydro_budgets()
        logger.info("Time series attachment complete")
        return Ok()

    def post_process_system(self) -> Result[None, ParserError]:
        """Perform post-processing on the built system.

        Sets system metadata including:
        - Data format version
        - System description with case, scenario, and year information
        - Logs component summary statistics

        Returns
        -------
        None
        """
        logger.info("Post-processing ReEDS system...")

        self.system.data_format_version = LATEST_COMMIT
        self.system.description = (
            f"ReEDS model system for case '{self.config.case_name}', "
            f"scenario '{self.config.scenario}', "
            f"solve years: {self.config.solve_year}, "
            f"weather years: {self.config.weather_year}"
        )

        total_components = len(list(self.system.get_components(Component)))
        logger.info("System name: {}", self.system.name)
        logger.info("Total components: {}", total_components)
        logger.info("Post-processing complete")
        return Ok()

    def _build_regions(self) -> None:
        """Build region components from hierarchy data.

        Creates ReEDSRegion components with all hierarchical attributes
        (state, NERC region, transmission region, interconnect, etc.).
        """
        logger.info("Building regions...")

        hierarchy_data = self.read_data_file("hierarchy").collect()
        if hierarchy_data is None:
            logger.warning("No hierarchy data found, skipping regions")
            return

        region_count = 0
        for row in hierarchy_data.iter_rows(named=True):
            region_name = row.get("region_id") or row.get("region") or row.get("r") or row.get("*r")
            if not region_name:
                continue

            region = self.create_component(
                ReEDSRegion,
                name=region_name,
                description=f"ReEDS region {region_name}",
                category=row.get("region_type"),
                state=row.get("state") or row.get("st"),
                nerc_region=row.get("nerc_region") or row.get("nercr"),
                transmission_region=row.get("transmission_region") or row.get("transreg"),
                transmission_group=row.get("transmission_group") or row.get("transgrp"),
                interconnect=row.get("interconnect"),
                country=row.get("country"),
                timezone=row.get("timezone"),
                cendiv=row.get("cendiv"),
                usda_region=row.get("usda_region"),
                h2ptc_region=row.get("h2ptc_region") or row.get("h2ptcreg"),
                hurdle_region=row.get("hurdle_region") or row.get("hurdlereg"),
                cc_region=row.get("cc_region") or row.get("ccreg"),
            )

            self.add_component(region)
            self._region_cache[region_name] = region
            region_count += 1

        logger.info("Built {} regions", region_count)

    def _build_generators(self) -> None:
        """Build generator components from capacity data.

        Renewable generators (wind/solar) are aggregated by technology and region.
        Non-renewable generators retain vintage information for tracking.
        Joins capacity with fuel prices, heat rates, outage rates, and other attributes.
        """
        logger.info("Building generators...")

        capacity_data = self.read_data_file("online_capacity")
        if capacity_data is None:
            logger.warning("No capacity data found, skipping generators")
            return

        df = capacity_data
        fuel_price = self.read_data_file("fuel_price")
        biofuel = self.read_data_file("biofuel_price")
        gen_fuel = self.read_data_file("fuel_tech_map")
        if biofuel is not None and gen_fuel is not None:
            biofuel_mapped = (
                biofuel.with_columns(pl.lit("biomass").alias("fuel_type"))
                .join(gen_fuel, on="fuel_type")
                .select(pl.exclude("fuel_type"))
            )
            if not biofuel_mapped.collect().is_empty():
                fuel_price = pl.concat([fuel_price, biofuel_mapped], how="diagonal")
                # fuel_price = fuel_price.rename({"value": "fuel_price"})

        for next_df in [
            self.read_data_file("fuel_tech_map"),
            fuel_price,
            self.read_data_file("heat_rate"),
            self.read_data_file("cost_vom"),
            self.read_data_file("forced_outages"),
            self.read_data_file("planned_outages"),
            self.read_data_file("maxage"),
        ]:
            if next_df is not None:
                common_cols = list(set(df.collect_schema().names()) & set(next_df.collect_schema().names()))
                df = df.join(next_df, how="left", on=common_cols)

        df = df.collect()
        if df.is_empty():
            logger.warning("Generator data is empty, skipping generators")
            return

        if self.excluded_technologies:
            initial_count = len(df)
            df = df.filter(~pl.col("technology").is_in(self.excluded_technologies))
            excluded_count = initial_count - len(df)
            if excluded_count > 0:
                logger.info("Excluded {} generators with technologies in excluded_techs list", excluded_count)

        if df.is_empty():
            logger.warning("All generators were excluded, skipping generators")
            return

        df = df.with_columns(
            pl.col("technology")
            .map_elements(
                lambda tech: get_technology_category(tech, self.technology_categories).unwrap_or(None),
                return_dtype=pl.String,
            )
            .alias("category")
        )

        df_renewable = df.filter(pl.col("category").is_in(["wind", "solar"]))
        df_non_renewable = df.filter(
            (~pl.col("category").is_in(["wind", "solar"])) | pl.col("category").is_null()
        )

        renewable_count = 0
        if not df_renewable.is_empty():
            agg_cols = [
                "heat_rate",
                "forced_outage_rate",
                "planned_outage_rate",
                "maxage_years",
                "fuel_type",
                "fuel_price",
                "vom_price",
            ]
            agg_exprs = [pl.col("capacity").sum()] + [
                pl.col(col).first() if col in df_renewable.columns else pl.lit(None).alias(col)
                for col in agg_cols
            ]
            for row in (
                df_renewable.group_by(["technology", "region", "category"])
                .agg(agg_exprs)
                .iter_rows(named=True)
            ):
                if (tech := row.get("technology")) and (region := row.get("region")):
                    self._create_generator(tech, region, None, row, gen_suffix=f"{region}")
                    renewable_count += 1

        gen_count = 0
        for row in df_non_renewable.iter_rows(named=True):
            if (tech := row.get("technology")) and (region := row.get("region")):
                self._create_generator(tech, region, row.get("vintage"), row)
                gen_count += 1

        total_gen_count = renewable_count + gen_count
        if total_gen_count == 0:
            logger.warning("No generators were created")
        else:
            logger.info(
                "Built {} generators ({} renewable aggregated, {} non-renewable)",
                total_gen_count,
                renewable_count,
                gen_count,
            )

    def _build_transmission(self) -> None:
        """Build transmission interface and line components.

        Creates bi-directional transmission lines with separate forward/reverse ratings.
        Uses canonical alphabetical ordering for interface naming to avoid duplicates.
        """
        logger.info("Building transmission interfaces...")

        trancap_data = self.read_data_file("transmission_capacity")
        if trancap_data is None:
            logger.warning("No transmission capacity data found, skipping transmission")
            return

        trancap = trancap_data.collect()

        if trancap.is_empty():
            logger.warning("Transmission capacity data is empty, skipping transmission")
            return

        line_count = 0
        interface_count = 0

        for row in trancap.iter_rows(named=True):
            from_region_name = row.get("from_region")
            to_region_name = row.get("to_region")
            line_type = row.get("trtype", "AC")
            capacity_from_to = float(row.get("capacity") or 0.0)

            if not from_region_name or not to_region_name:
                continue

            from_region = self._region_cache.get(from_region_name)
            to_region = self._region_cache.get(to_region_name)

            if not from_region or not to_region:
                logger.debug("Skipping line {}-{}: region not found", from_region_name, to_region_name)
                continue

            reverse_row = trancap.filter(
                (pl.col("from_region") == to_region_name)
                & (pl.col("to_region") == from_region_name)
                & (pl.col("trtype") == line_type)
            )
            if not reverse_row.is_empty():
                capacity_to_from = reverse_row["capacity"].item()
            else:
                capacity_to_from = capacity_from_to

            regions_sorted = sorted([from_region_name, to_region_name])
            interface_name = f"{regions_sorted[0]}||{regions_sorted[1]}"

            if from_region_name == regions_sorted[0]:
                interface_from = from_region
                interface_to = to_region
                forward_cap = capacity_from_to
                reverse_cap = capacity_to_from
            else:
                interface_from = to_region
                interface_to = from_region
                forward_cap = capacity_to_from
                reverse_cap = capacity_from_to

            if interface_name not in self._interface_cache:
                interface = ReEDSInterface(
                    name=interface_name,
                    from_region=interface_from,
                    to_region=interface_to,
                    category=line_type,
                )
                self.system.add_component(interface)
                self._interface_cache[interface_name] = interface
                interface_count += 1
            else:
                interface = self._interface_cache[interface_name]

            line_name = f"{from_region_name}_{to_region_name}_{line_type}"
            line = ReEDSTransmissionLine(
                name=line_name,
                interface=interface,
                max_active_power=FromTo_ToFrom(from_to=forward_cap, to_from=reverse_cap),
                category=line_type,
                line_type=line_type,
            )
            self.system.add_component(line)
            line_count += 1

        logger.info("Built {} transmission interfaces and {} lines", interface_count, line_count)

    def _build_loads(self) -> Result[None, ParserError]:
        """Build load components from demand data.

        Filters load data by weather year and solve year.
        Stores filtered data for later time series attachment.
        """
        logger.info("Building loads...")

        load_profiles = self.read_data_file("load_profiles").collect()

        if load_profiles.is_empty():
            msg = "Load data is empty and must exist for proper translation."
            return ParserError(msg)

        load_count = 0
        for region_name, region_obj in self._region_cache.items():
            if region_name not in load_profiles.columns:
                logger.debug("No load data for region {}", region_name)
                continue

            load_profile = load_profiles[region_name].to_numpy()
            peak_load = float(load_profile.max())

            demand = self.create_component(
                ReEDSDemand,
                name=f"{region_name}_load",
                region=region_obj,
                max_active_power=peak_load,
            )

            self.add_component(demand)
            load_count += 1

        logger.info("Built {} load components", load_count)
        return Ok()

    def _build_reserves(self) -> None:
        """Build reserve requirement components.

        Creates reserve components for each transmission region and reserve type.
        Configuration loaded from defaults.json includes types, duration, timeframe, etc.
        """
        logger.info("Building reserves...")

        hierarchy_data = self.read_data_file("hierarchy")
        if hierarchy_data is None:
            logger.warning("No hierarchy data found, skipping reserves")
            return

        df = hierarchy_data.collect()
        if df.is_empty():
            logger.warning("Hierarchy data is empty, skipping reserves")
            return

        defaults = self.config.load_defaults()
        reserve_types = defaults.get("default_reserve_types", [])
        reserve_duration = defaults.get("reserve_duration", {})
        reserve_time_frame = defaults.get("reserve_time_frame", {})
        reserve_vors = defaults.get("reserve_vors", {})
        reserve_direction = defaults.get("reserve_direction", {})

        if not reserve_types:
            logger.debug("No reserve types configured, skipping reserves")
            return

        reserve_type_map = {
            "SPINNING": ReserveType.SPINNING,
            "FLEXIBILITY": ReserveType.FLEXIBILITY_UP,
            "REGULATION": ReserveType.REGULATION,
        }

        direction_map = {"Up": ReserveDirection.UP, "Down": ReserveDirection.DOWN}

        if "transmission_region" in df.columns:
            transmission_regions = df["transmission_region"].unique().to_list()
        else:
            transmission_regions = []

        reserve_count = 0
        for region_name in transmission_regions:
            for reserve_type_name in reserve_types:
                reserve_type = reserve_type_map.get(reserve_type_name)
                if not reserve_type:
                    logger.warning("Unknown reserve type: {}", reserve_type_name)
                    continue

                duration = reserve_duration.get(reserve_type_name)
                time_frame = reserve_time_frame.get(reserve_type_name)
                vors = reserve_vors.get(reserve_type_name)
                direction_str = reserve_direction.get(reserve_type_name, "Up")
                direction = direction_map.get(direction_str, ReserveDirection.UP)

                reserve = self.create_component(
                    ReEDSReserve,
                    name=f"{region_name}_{reserve_type_name}",
                    reserve_type=reserve_type,
                    duration=duration,
                    time_frame=time_frame,
                    vors=vors,
                    direction=direction,
                )

                self.add_component(reserve)
                reserve_count += 1

        logger.info("Built {} reserve components", reserve_count)

    def _build_emissions(self) -> None:
        """Attach emission supplemental attributes to generators.

        Only processes combustion emissions. Emission types are normalized to uppercase
        for enum validation.
        """
        logger.info("Building emissions...")

        emit_data = self.read_data_file("emission_rates")
        if emit_data is None:
            logger.warning("No emission rates data found, skipping emissions")
            return

        df = emit_data.collect()
        if df.is_empty():
            logger.warning("Emission rates data is empty, skipping emissions")
            return

        emission_count = 0

        for row in df.iter_rows(named=True):
            tech = row.get("technology") or row.get("tech") or row.get("i")
            region = row.get("region") or row.get("r")
            emission_type = row.get("emission_type") or row.get("e")
            rate = row.get("emission_rate")
            emission_source = row.get("emission_source", "combustion")

            if not tech or not region or not emission_type or rate is None:
                continue

            if emission_source != "combustion":
                continue

            emission_type = str(emission_type).upper()

            gen_name = f"{region}_{tech}"
            generator = self._generator_cache.get(gen_name)

            if not generator:
                logger.debug("Generator {} not found for emission {}, skipping", gen_name, emission_type)
                continue

            emission = ReEDSEmission(
                emission_type=EmissionType(emission_type),
                rate=float(rate),
            )

            self.system.add_supplemental_attribute(generator, emission)
            emission_count += 1

        logger.info("Attached {} emissions to generators", emission_count)

    def _attach_load_profiles(self) -> Result[None, ParserError]:
        """Attach load time series to demand components.

        Extracts hourly load profiles from load data filtered by weather and solve years.
        Matches profile columns to demand components by region name.

        Returns
        -------
        Result[None, ParserError]
            Ok() on success, Err() with ParserError if data is empty or demands not found

        Notes
        -----
        Load data must be filtered during :meth:`_build_loads` before calling this method.
        """
        logger.info("Attaching load profiles...")

        load_profiles = self.read_data_file("load_profiles").collect()
        demands = list(self.system.get_components(ReEDSDemand))

        if load_profiles.is_empty() or not demands:
            return ParserError("Load data is empty or demands not found on the system.")

        resolution = (self.hourly_time_index[1] - self.hourly_time_index[0]).astype("timedelta64[us]").item()

        attached_count = 0
        for demand in demands:
            region_name = demand.name.replace("_load", "")
            if region_name in load_profiles.columns:
                ts = SingleTimeSeries.from_array(
                    data=load_profiles[region_name].to_numpy(),
                    name="max_active_power",
                    initial_timestamp=self.initial_timestamp,
                    resolution=resolution,
                )
                self.system.add_time_series(ts, demand)
                attached_count += 1

        logger.debug("Attached {} load profiles to demand components", attached_count)
        return Ok()

    def _attach_renewable_profiles(self) -> Result[None, ParserError]:
        """Attach renewable capacity factor profiles to generator components.

        Matches renewable profile columns (format: technology|region) to generators.
        Validates that weather years in profiles match configured weather years.

        Returns
        -------
        Result[None, ParserError]
            Ok() on success, Err() with ParserError if data is empty or years mismatch

        Raises
        ------
        ParserError
            If renewable profiles are empty or contain unexpected weather years
        """
        logger.info("Attaching renewable profiles to generators...")

        renewable_profiles = self.read_data_file("renewable_profiles").collect()
        if renewable_profiles.is_empty():
            renewable_profile_meta = self.read_data("renewable_profiles")
            return ParserError(f"Renewable profile is empty. Check {renewable_profile_meta.fpath}")

        if not renewable_profiles["datetime"].dt.year().unique().is_in(self.weather_years).all():
            year_list = renewable_profiles["datetime"].dt.year().unique().to_list()
            msg = "Weather year filter process failed. "
            msg += f"Renewable profiles have the following weather_years {year_list}"
            return ParserError(msg)

        resolution = (self.hourly_time_index[1] - self.hourly_time_index[0]).astype("timedelta64[us]").item()

        profile_count = 0
        tech_regions = (
            pl.DataFrame({"col": renewable_profiles.columns})
            .filter(pl.col("col") != "datetime")
            .with_columns(
                [
                    pl.col("col").str.split("|").alias("parts"),
                    pl.col("col").str.split("|").list.len().alias("len"),
                ]
            )
            .filter(pl.col("len") == 2)
            .with_columns(
                [
                    pl.col("parts").list.get(0).alias("tech"),
                    pl.col("parts").list.get(1).alias("region"),
                ]
            )
            .select("col", "tech", "region")
        )

        for row in tech_regions.iter_rows(named=True):
            tech = row["tech"]
            region_name = row["region"]
            col_name = row["col"]

            matching_generators = [
                gen
                for gen in self._generator_cache.values()
                if gen.technology == tech and gen.region.name == region_name
            ]

            if not matching_generators:
                continue

            data = renewable_profiles[col_name].to_numpy()
            ts = SingleTimeSeries.from_array(
                data=data,
                name="max_active_power",
                initial_timestamp=self.initial_timestamp,
                resolution=resolution,
            )

            for generator in matching_generators:
                self.system.add_time_series(ts, generator)
                profile_count += 1

        logger.info("Attached {} renewable profiles", profile_count)
        return Ok()

    def _attach_reserve_profiles(self) -> None:
        """Attach reserve requirement time series to reserve components.

        Calculates dynamic reserve requirements from wind, solar, and load contributions
        using configurable percentages from defaults. Applies requirements to reserve
        components by transmission region.

        Returns
        -------
        None

        See Also
        --------
        :meth:`_calculate_reserve_requirement` : Computes individual reserve requirements
        """
        logger.info("Attaching reserve profiles...")

        defaults = self.config.load_defaults()
        excluded_from_reserves = defaults.get("excluded_from_reserves", {})

        if not excluded_from_reserves:
            logger.warning("No excluded_from_reserves configured in defaults, skipping reserve profiles")
            return

        for reserve in self.system.get_components(ReEDSReserve):
            requirement_profile = self._calculate_reserve_requirement(reserve)

            if requirement_profile is None or len(requirement_profile) == 0:
                logger.warning(f"No reserve requirement calculated for {reserve.name}, skipping")
                continue

            initial_timestamp = self.hourly_time_index[0].astype("datetime64[s]").astype(datetime)
            resolution = timedelta(hours=1)

            ts = SingleTimeSeries.from_array(
                data=requirement_profile,
                name="requirement",
                initial_timestamp=initial_timestamp,
                resolution=resolution,
            )
            self.system.add_time_series(ts, reserve)

        logger.info("Reserve profile attachment complete")

    def _calculate_reserve_requirement(self, reserve: ReEDSReserve) -> np.ndarray | None:
        """Calculate reserve requirement based on wind, solar, and load profiles.

        Reserve requirement = (wind_capacity * wind_pct) + (solar_capacity * solar_pct) + (load * load_pct)

        Wind contribution: Sum of individual generator capacities weighted by percentage
        Solar contribution: Total capacity when any solar is active, weighted by percentage
        Load contribution: Load value weighted by percentage

        Parameters
        ----------
        reserve : ReEDSReserve
            Reserve component to calculate requirement for

        Returns
        -------
        np.ndarray | None
            Array of reserve requirements over time, or None if cannot be calculated
        """
        reserve_type_name = reserve.reserve_type.value.upper()
        if reserve_type_name in ("FLEXIBILITY_UP", "FLEXIBILITY_DOWN"):
            reserve_type_name = "FLEXIBILITY"

        region_name = reserve.name.rsplit("_", 1)[0]

        logger.debug(
            f"Calculating reserve requirement for {reserve.name} (region: {region_name}, type: {reserve_type_name})"
        )

        defaults = self.config.load_defaults()
        wind_percentages = defaults.get("wind_reserves", {})
        solar_percentages = defaults.get("solar_reserves", {})
        load_percentages = defaults.get("load_reserves", {})

        wind_pct = wind_percentages.get(reserve_type_name, 0.0)
        solar_pct = solar_percentages.get(reserve_type_name, 0.0)
        load_pct = load_percentages.get(reserve_type_name, 0.0)

        num_hours = len(self.hourly_time_index)
        requirement = np.zeros(num_hours)

        if wind_pct > 0:
            wind_generators = [
                gen
                for gen in self.system.get_components(ReEDSGenerator)
                if gen.region
                and gen.region.transmission_region == region_name
                and tech_matches_category(gen.technology, "wind", self.technology_categories)
            ]

            for gen in wind_generators:
                if self.system.has_time_series(gen):
                    ts = self.system.get_time_series(gen)
                    data_length = min(len(ts.data), len(requirement))
                    requirement[:data_length] += ts.data[:data_length] * wind_pct

        if solar_pct > 0:
            solar_generators = [
                gen
                for gen in self.system.get_components(ReEDSGenerator)
                if gen.region
                and gen.region.transmission_region == region_name
                and tech_matches_category(gen.technology, "solar", self.technology_categories)
            ]

            total_solar_capacity = sum(gen.capacity for gen in solar_generators)
            solar_active = np.zeros(num_hours)

            for gen in solar_generators:
                if self.system.has_time_series(gen):
                    ts = self.system.get_time_series(gen)
                    data_length = min(len(ts.data), len(solar_active))
                    solar_active[:data_length] = np.maximum(
                        solar_active[:data_length], (ts.data[:data_length] > 0).astype(float)
                    )

            requirement += solar_active * total_solar_capacity * solar_pct

        if load_pct > 0:
            loads = [
                load
                for load in self.system.get_components(ReEDSDemand)
                if load.region and load.region.transmission_region == region_name
            ]

            for load in loads:
                if self.system.has_time_series(load):
                    ts = self.system.get_time_series(load)
                    data_length = min(len(ts.data), len(requirement))
                    requirement[:data_length] += ts.data[:data_length] * load_pct

        if requirement.sum() == 0:
            logger.warning(f"Reserve requirement for {reserve.name} is zero")
            return None

        return requirement

    def _create_generator(
        self,
        tech: str,
        region_name: str,
        vintage: str | None,
        row: dict[str, object],
        gen_suffix: str = "",
    ) -> None:
        """Helper to create and cache a generator component."""
        region_obj = self._region_cache.get(region_name)
        if not region_obj:
            logger.warning("Region '{}' not found for generator {}, skipping", region_name, tech)
            return

        gen_name = f"{tech}_{vintage}_{region_name}" if vintage else f"{tech}_{region_name}"
        if gen_suffix:
            gen_name = f"{tech}_{gen_suffix}"

        generator = self.create_component(
            ReEDSGenerator,
            name=gen_name,
            category=row.get("category"),
            region=region_obj,
            technology=tech,
            capacity=row.get("capacity"),
            heat_rate=row.get("heat_rate"),
            forced_outage_rate=row.get("forced_outage_rate"),
            planned_outage_rate=row.get("planned_outage_rate"),
            max_age=row.get("maxage_years"),
            fuel_type=row.get("fuel_type"),
            fuel_price=row.get("fuel_price"),
            vom_cost=row.get("vom_price"),
            vintage=vintage,
        )

        self.add_component(generator)
        self._generator_cache[gen_name] = generator

    def _attach_hydro_budgets(self) -> None:
        """Attach daily energy budgets to hydro dispatch generators.

        Creates daily energy constraints based on monthly capacity factors.
        Budget = capacity * monthly_cf * hours_in_month
        """
        logger.info("Attaching hydro budget profiles...")

        hydro_cf = self.read_data_file("hydro_cf")
        hydro_generators = [
            gen
            for gen_name, gen in self._generator_cache.items()
            if tech_matches_category(gen.technology, "hydro", self.technology_categories)
        ]

        if not hydro_generators:
            logger.warning("No hydro generators found, skipping hydro budgets")
            return

        hydro_cf: pl.DataFrame = (
            hydro_cf.with_columns(
                pl.col("month")
                .map_elements(lambda x: self.month_map.get(x, x), return_dtype=pl.Int16)
                .alias("month_num"),
            )
            .sort(["year", "technology", "region", "month_num"])
            .collect()
        )

        hydro_cf = hydro_cf.join(self.year_month_day_hours, on=["year", "month_num"], how="left")

        hydro_capacity = pl.DataFrame(
            [
                (gen.name, gen.technology, gen.region.name, gen.capacity, gen.vintage)
                for gen in hydro_generators
            ],
            schema=["name", "technology", "region", "capacity", "vintage"],
            orient="row",
        )

        hydro_data = hydro_capacity.join(hydro_cf, on=["technology", "region"], how="left")

        # Daily Energy budget units in MWh
        hydro_data = hydro_data.with_columns(
            (
                pl.col("hydro_cf") * pl.col("hours_in_month") * pl.col("capacity") / pl.col("days_in_month")
            ).alias("daily_energy_budget")
        )

        for generator in hydro_generators:
            tech_region_filter = (
                (pl.col("technology") == generator.technology)
                & (pl.col("region") == generator.region.name)
                & (pl.col("vintage") == generator.vintage)
            )
            for row, month_budget_by_vintage in hydro_data.filter(tech_region_filter).group_by(
                ["year", "vintage"]
            ):
                year = row[0]
                hourly_budget = monthly_to_hourly_polars(year, month_budget_by_vintage["daily_energy_budget"])
                ts = SingleTimeSeries.from_array(
                    data=hourly_budget.unwrap(),
                    name="hydro_budget",
                    initial_timestamp=self.initial_timestamp,
                    resolution=timedelta(hours=1),
                )

                self.system.add_time_series(ts, generator, solve_year=year)
                logger.debug("Adding hydro budget to {}", generator.label)
        return
