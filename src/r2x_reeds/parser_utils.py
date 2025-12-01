"""Utilities for the parser."""

from __future__ import annotations

import calendar
import importlib
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any, Literal

import numpy as np
import polars as pl
from loguru import logger
from rust_ok import Err, Ok, Result

from r2x_core import ParserError
from r2x_core.rules_utils import build_component_kwargs
from r2x_reeds.models.components import ReEDSRegion

if TYPE_CHECKING:
    from r2x_core import System
    from r2x_core.context import ParserContext
    from r2x_core.rules import Rule
    from r2x_reeds.models import ReEDSGenerator

# Columns that can be aggregated from the model.
AGG_COLUMNS = [
    "heat_rate",
    "forced_outage_rate",
    "planned_outage_rate",
    "maxage_years",
    "fuel_type",
    "fuel_price",
    "vom_price",
    "resource_class",
    "inverter_loading_ratio",
    "capacity_factor_adjustment",
    "max_capacity_factor",
    "supply_curve_cost",
    "transmission_adder",
]


def _build_generator_field_map(row: Mapping[str, Any], system: System) -> dict[str, Any]:
    """Resolve generator fields by translating region names to components."""

    fields = dict(row)
    region_name = row.get("region")

    if isinstance(region_name, str):
        try:
            region_component = system.get_component(ReEDSRegion, region_name)
        except Exception:
            region_component = None

        if region_component is not None:
            fields["region"] = region_component

    return fields


def tech_matches_category(tech: str, category_name: str, tech_categories: dict[str, Any]) -> bool:
    """Check if a technology matches a category using prefix or exact matching.

    Parameters
    ----------
    tech : str
        Technology name to check
    category_name : str
        Category name from tech_categories
    defaults : dict
        Defaults dictionary containing tech_categories

    Returns
    -------
    bool
        True if technology matches the category
    """
    if category_name not in tech_categories:
        return False

    category = tech_categories[category_name]
    tech_value = str(tech).casefold()

    if isinstance(category, list):
        normalized = [str(item).casefold() for item in category]
        return tech_value in normalized

    prefixes = [str(prefix).casefold() for prefix in category.get("prefixes", [])]
    exact = [str(item).casefold() for item in category.get("exact", [])]

    if tech_value in exact:
        return True

    return any(tech_value.startswith(prefix) for prefix in prefixes)


def get_technology_category(
    technology_name: str, technology_categories: dict[str, Any]
) -> Result[str, KeyError]:
    """Get the first matching category for a technology.

    Notes
    -----
    This function preserves the legacy behavior of returning only the first match
    based on the order of ``technology_categories``. Use
    :func:`get_technology_categories` if you need all matches.
    """
    categories_result = get_technology_categories(technology_name, technology_categories)
    if categories_result.is_ok():
        categories = categories_result.unwrap()
        return Ok(categories[0])
    return Err(categories_result.unwrap_err())


def get_technology_categories(
    technology_name: str, technology_categories: dict[str, Any]
) -> Result[list[str], KeyError]:
    """Get all matching categories for a technology.

    Parameters
    ----------
    tech : str
        Technology name
    defaults : dict
        Defaults dictionary containing tech_categories

    Returns
    -------
    Result[list[str], KeyError]
            ``Ok([category_names...])`` if technology is found, or ``Err(KeyError(...)`` if not found.
    """
    matches: list[str] = []
    for category_name in technology_categories:
        category_name_str: str = str(category_name)
        if tech_matches_category(technology_name, category_name_str, technology_categories):
            matches.append(category_name_str)

    if matches:
        return Ok(matches)

    return Err(KeyError(f"Technology {technology_name} does not have category match."))


def monthly_to_hourly_polars(year: int, monthly_profile: list[float]) -> Result[np.ndarray, ValueError]:
    """Convert a 12-element monthly profile into an hourly profile for the given year"""
    if len(monthly_profile) != 12:
        raise ValueError("monthly_profile must have 12 elements")

    hours_per_month = np.array([calendar.monthrange(year, m)[1] * 24 for m in range(1, 13)])
    hourly_profile = np.repeat(monthly_profile, hours_per_month)

    return Ok(hourly_profile)


def merge_lazy_frames(
    left: pl.LazyFrame,
    right: pl.LazyFrame,
    *,
    on: list[str],
    how: str = "left",
    suffix: str = "_right",
) -> Result[pl.LazyFrame, ParserError]:
    """Safe wrapper around LazyFrame.join with consistent error reporting."""
    try:
        merged = left.join(right, on=on, how=how, suffix=suffix)
        return Ok(merged)
    except Exception as exc:  # pragma: no cover - defensive
        return Err(ParserError(f"Failed to merge frames on {on}: {exc}"))


def get_generator_class(
    tech: str,
    technology_categories: dict[str, Any],
    category_class_mapping: dict[str, str],
    models_path: Literal["r2x_reeds.models"] = "r2x_reeds.models",
) -> Result[type[ReEDSGenerator], TypeError]:
    """Determine the appropriate generator class based on technology category using config mapping.

    Parameters
    ----------
    tech : str
        Technology name
    technology_categories : dict[str, Any]
        Technology categories mapping from defaults (for prefix/exact matching)
    category_class_mapping : dict[str, str]
        Mapping from category names to generator class names

    Returns
    -------
    type[ReEDSGenerator]
        The appropriate generator class (Thermal, Variable, Storage, Hydro, or Consuming)
    """
    categories_result = get_technology_categories(tech, technology_categories)

    if categories_result.is_err():
        err = categories_result.unwrap_err()
        return Err(TypeError(str(err)))

    module = importlib.import_module(models_path)
    categories = categories_result.unwrap()

    for category in categories:
        class_name = category_class_mapping.get(category)
        if class_name and (model := getattr(module, class_name, None)):
            return Ok(model)

    logger.error("Technology model not found for {} on {} (categories: {})", tech, models_path, categories)
    return Err(TypeError(f"Technology model {tech} not found on {models_path} for categories {categories}"))


def _prepare_generator_dataset(
    capacity_data: pl.LazyFrame,
    optional_data: dict[str, pl.LazyFrame | None],
    excluded_technologies: list[str],
    technology_categories: dict[str, Any],
) -> Result[pl.DataFrame, ParserError]:
    """Join all generator data sources and add technology categories.

    Parameters
    ----------
    capacity_data : pl.LazyFrame
        Online capacity data (required). Must have columns: technology, region, capacity
    optional_data : dict[str, pl.LazyFrame | None]
        Dictionary of optional data sources to join (fuel_price, heat_rate, etc.)
    excluded_technologies : list[str]
        Technologies to exclude from output
    technology_categories : dict[str, Any]
        Technology category definitions for classification

    Returns
    -------
    Result[pl.DataFrame, ParserError]
        Ok(prepared_data) collected DataFrame with categories added, or Err on failure

    Notes
    -----
    - All joins are left joins to preserve capacity data
    - Excluded technologies filtered after all joins
    - Returns collected DataFrame for fail-fast error detection
    """
    if capacity_data is None:
        return Err(ParserError("No capacity data found"))

    df = capacity_data

    join_overrides: dict[str, list[str]] = {
        "storage_duration_out": ["technology", "vintage", "region", "year"],
        "consume_characteristics": ["technology", "year"],
    }

    def _transform_optional(name: str, frame: pl.LazyFrame) -> pl.LazyFrame:
        """Normalize optional data frames before joining."""
        if name == "storage_duration_out":
            return frame.select(
                pl.col("technology"),
                pl.col("vintage"),
                pl.col("region"),
                pl.col("year"),
                pl.col("storage_duration").alias("storage_duration_out_value"),
            )
        if name == "consume_characteristics":
            return frame.filter(pl.col("parameter") == "electricity_efficiency").select(
                pl.col("technology"),
                pl.col("year"),
                pl.col("value").alias("electricity_efficiency"),
            )
        return frame

    for name, next_df in optional_data.items():
        if next_df is None:
            continue

        if name == "fuel_tech_map":
            try:
                if "technology" not in next_df.collect_schema().names():
                    continue

                join_key = "__technology_join"
                df = df.with_columns(
                    pl.col("technology").str.split("_").list.get(0).str.to_lowercase().alias(join_key)
                )
                mapping = next_df.with_columns(
                    pl.col("technology").str.split("_").list.get(0).str.to_lowercase().alias(join_key)
                ).select(pl.col(join_key), pl.col("fuel_type"))
                df = df.join(mapping, how="left", on=join_key).drop(join_key)
            except Exception as e:
                return Err(ParserError(f"Failed to join {name} data: {e}"))
            continue

        try:
            transformed = _transform_optional(name, next_df)
            df_cols = set(df.collect_schema().names())
            transformed_cols = set(transformed.collect_schema().names())
            override_keys = join_overrides.get(name)
            if override_keys:
                common_cols = [col for col in override_keys if col in df_cols and col in transformed_cols]
            else:
                common_cols = list(df_cols & transformed_cols)
            if common_cols:
                df = df.join(transformed, how="left", on=common_cols)
                if (
                    name == "storage_duration_out"
                    and "storage_duration_out_value" in df.collect_schema().names()
                ):
                    df = df.with_columns(
                        pl.when(pl.col("storage_duration").is_null())
                        .then(pl.col("storage_duration_out_value"))
                        .otherwise(pl.col("storage_duration"))
                        .alias("storage_duration")
                    ).drop("storage_duration_out_value")
        except Exception as e:
            return Err(ParserError(f"Failed to join {name} data: {e}"))

    df = df.collect()
    df = df.with_columns(pl.col("technology").str.split("_").list.get(0).alias("technology_base"))

    if "fuel_type" not in df.columns:
        return Err(ParserError("Generator fuel_type column is missing from the fuel2tech mapping"))

    def _categories_for_tech(tech: str) -> list[str]:
        """Return category names for a technology, logging misses."""
        result = get_technology_categories(tech, technology_categories)
        if result.is_err():
            logger.debug("Technology %s has no category match: %s", tech, result.err())
            return []
        categories = result.ok()
        return categories if categories is not None else []

    df = df.with_columns(
        pl.col("technology_base")
        .map_elements(
            _categories_for_tech,
            return_dtype=pl.List(pl.Utf8),
        )
        .alias("categories")
    ).with_columns(pl.col("categories").list.first().alias("category"))

    df = df.with_columns(
        pl.col("technology")
        .map_elements(
            lambda tech: tech_matches_category(tech, "thermal", technology_categories),
            return_dtype=pl.Boolean,
        )
        .alias("is_thermal")
    )

    df = df.drop("technology_base")

    df = df.with_columns(
        pl.when(pl.col("is_thermal") & pl.col("fuel_type").is_null())
        .then(pl.lit("OTHER"))
        .otherwise(pl.col("fuel_type"))
        .alias("fuel_type")
    ).drop("is_thermal")

    if df.is_empty():
        return Err(ParserError("Generator data is empty after joining"))

    if excluded_technologies:
        initial_count = len(df)
        df = df.filter(~pl.col("technology").is_in(excluded_technologies))
        excluded_count = initial_count - len(df)
        if excluded_count > 0:
            logger.info("Excluded {} generators with excluded technologies", excluded_count)

    if df.is_empty():
        return Err(ParserError("All generators were excluded"))

    return Ok(df)


def aggregate_variable_generators(df: pl.DataFrame) -> pl.DataFrame:
    """Aggregate variable renewable generators by tech-region-category.

    Parameters
    ----------
    df : pl.DataFrame
        Generator data (pre-filtered to variable renewable only)

    Returns
    -------
    pl.DataFrame
        Aggregated data with one row per tech-region-category combination
        - Capacity summed
        - Specific fields use first() (resource_class, fuel_type)
        - Other fields averaged
    """
    first_fields = {"resource_class", "fuel_type"}
    agg_exprs = [pl.col("capacity").sum()]

    for col in AGG_COLUMNS:
        if col not in df.columns:
            agg_exprs.append(pl.lit(None).alias(col))
        elif col in first_fields:
            agg_exprs.append(pl.col(col).first())
        else:
            agg_exprs.append(pl.col(col).mean().alias(col))

    agg_exprs.append(pl.col("categories").first().alias("categories"))

    group_keys = ["technology", "region", "category"]
    return df.group_by(group_keys).agg(agg_exprs)


def calculate_reserve_requirement(
    wind_generators: list[dict],
    solar_generators: list[dict],
    loads: list[dict],
    hourly_time_index: np.ndarray,
    wind_pct: float,
    solar_pct: float,
    load_pct: float,
) -> Result[np.ndarray, ParserError]:
    """Calculate reserve requirement profile from component data.

    Reserve requirement = (wind_capacity * wind_pct) + (solar_capacity * solar_pct) + (load * load_pct)

    Parameters
    ----------
    wind_generators : list[dict]
        Wind generator data with 'capacity' and 'time_series' keys
    solar_generators : list[dict]
        Solar generator data with 'capacity' and 'time_series' keys
    loads : list[dict]
        Load data with 'time_series' key
    hourly_time_index : np.ndarray
        Hourly time index for sizing
    wind_pct : float
        Wind contribution percentage (0-1)
    solar_pct : float
        Solar contribution percentage (0-1)
    load_pct : float
        Load contribution percentage (0-1)

    Returns
    -------
    Result[np.ndarray, ParserError]
        Ok(requirement_array) or Err if calculation fails
    """
    try:
        num_hours = len(hourly_time_index)
        requirement = np.zeros(num_hours)

        if wind_pct > 0 and wind_generators:
            for gen in wind_generators:
                ts_data = gen.get("time_series")
                if ts_data is not None:
                    data_len = min(len(ts_data), num_hours)
                    requirement[:data_len] += ts_data[:data_len] * wind_pct

        if solar_pct > 0 and solar_generators:
            solar_active = np.zeros(num_hours)
            total_solar_capacity = sum(gen.get("capacity", 0) for gen in solar_generators)
            for gen in solar_generators:
                ts_data = gen.get("time_series")
                if ts_data is not None:
                    data_len = min(len(ts_data), num_hours)
                    solar_active[:data_len] = np.maximum(
                        solar_active[:data_len], (ts_data[:data_len] > 0).astype(float)
                    )
            requirement += solar_active * total_solar_capacity * solar_pct

        if load_pct > 0 and loads:
            for load in loads:
                ts_data = load.get("time_series")
                if ts_data is not None:
                    data_len = min(len(ts_data), num_hours)
                    requirement[:data_len] += ts_data[:data_len] * load_pct

        if requirement.sum() == 0:
            return Err(ParserError("Reserve requirement is zero"))

        return Ok(requirement)

    except Exception as e:
        return Err(ParserError(f"Failed to calculate reserve requirement: {e}"))


def _collect_component_kwargs_from_rule(
    data: pl.DataFrame,
    *,
    rule_provider: Rule | Callable[[Mapping[str, Any]], Result[Rule, ParserError]],
    parser_context: ParserContext,
    row_identifier_getter: Callable[[Mapping[str, Any]], Result[str, Exception]],
) -> Result[list[tuple[str, dict[str, Any]]], ParserError]:
    """Collect kwargs dictionaries for rule-driven components."""

    errors: list[str] = []
    collected: list[tuple[str, dict[str, Any]]] = []

    for row in data.iter_rows(named=True):
        identifier_result = row_identifier_getter(row)
        identifier_value: str | None
        match identifier_result:
            case Ok(identifier) if identifier:
                identifier_value = identifier
            case Ok(_):
                msg = "Missing identifier value"
                errors.append(msg)
                logger.error("Failed to derive identifier for row: %s", msg)
                continue
            case Err(error):
                errors.append(str(error))
                logger.error("Failed to derive identifier from row: %s", error)
                continue
            case _:
                continue

        rule_result = rule_provider(row) if callable(rule_provider) else Ok(rule_provider)
        if rule_result.is_err():
            rule_error = rule_result.err()
            errors.append(f"{identifier_value}: {rule_error}")
            logger.error("Failed to resolve rule for %s: %s", identifier_value, rule_error)
            continue
        selected_rule = rule_result.ok()

        result = build_component_kwargs(selected_rule, row, parser_context)
        if result.is_err():
            error_value = result.err()
            errors.append(f"{identifier_value}: {error_value}")
            logger.error("Failed to build kwargs for %s: %s", identifier_value, error_value)
            continue

        component_kwargs = result.ok()
        if component_kwargs is None:
            error_msg = "Empty kwargs result"
            errors.append(f"{identifier_value}: {error_msg}")
            logger.error("Failed to build kwargs for %s: %s", identifier_value, error_msg)
            continue

        collected.append((identifier_value, component_kwargs))

    if errors:
        failure_list = "; ".join(errors)
        return Err(ParserError(f"Failed to build the following components: {failure_list}"))

    return Ok(collected)


def _resolve_generator_rule_from_row(
    row: Mapping[str, Any],
    technology_categories: dict[str, Any],
    category_class_mapping: dict[str, str],
    rules_by_target: dict[str, list[Rule]],
) -> Result[Rule, ParserError]:
    """Return the parser rule that matches the generator technology."""

    technology = row.get("technology")
    if technology is None:
        return Err(ParserError("Generator row missing technology"))

    class_result = get_generator_class(
        str(technology),
        technology_categories,
        category_class_mapping,
    )
    if class_result.is_err():
        return Err(ParserError(f"Generator {technology} class lookup failed: {class_result.err()}"))

    generator_class = class_result.ok()
    if generator_class is None:
        return Err(ParserError(f"Generator class not resolved for {technology}"))

    rules = rules_by_target.get(generator_class.__name__, [])
    if not rules:
        return Err(ParserError(f"No parser rule found for {generator_class.__name__}"))

    return Ok(rules[0])


def prepare_generator_inputs(
    capacity_data: pl.LazyFrame,
    optional_data: dict[str, pl.LazyFrame | None],
    excluded_technologies: list[str],
    technology_categories: dict[str, Any],
    *,
    variable_categories: list[str] | None = None,
) -> Result[tuple[pl.DataFrame, pl.DataFrame], ParserError]:
    """Prepare cached generator datasets separated into variable renewables and others."""

    variable_categories = variable_categories or ["wind", "solar"]
    base_result = _prepare_generator_dataset(
        capacity_data=capacity_data,
        optional_data=optional_data,
        excluded_technologies=excluded_technologies,
        technology_categories=technology_categories,
    )
    if base_result.is_err():
        return base_result

    df = base_result.ok()
    if df is None:
        return Err(ParserError("Generator dataset preparation returned no data"))

    mask = None
    for category in variable_categories:
        contains_expr = pl.col("categories").list.contains(category)
        mask = contains_expr if mask is None else mask | contains_expr

    mask_expr = mask if mask is not None else pl.lit(False)

    variable_df = df.filter(mask_expr)
    non_variable_df = df.filter(~mask_expr)

    if variable_df.is_empty():
        aggregated_variable_df = variable_df.with_columns(pl.lit(False).alias("is_aggregated"))
    else:
        aggregated_variable_df = aggregate_variable_generators(variable_df).with_columns(
            pl.lit(True).alias("is_aggregated")
        )

    if "is_aggregated" not in non_variable_df.columns:
        non_variable_df = non_variable_df.with_columns(pl.lit(False).alias("is_aggregated"))

    return Ok((aggregated_variable_df, non_variable_df))


def get_rules_by_target(rules: list[Rule] | list[str]) -> Result[dict[str, list[Rule]], ParserError]:
    """Group parser rules by their target component types."""

    from collections import defaultdict

    rules_by_target: defaultdict[Any, list[Rule]] = defaultdict(list)
    for rule in rules:
        for target_type in rule.get_target_types():
            rules_by_target[target_type].append(rule)
    return Ok(rules_by_target)


def get_rule_for_target(
    rules_by_target: dict[str, list[Rule]],
    *,
    target_type: str,
    name: str | None = None,
) -> Result[Rule, ParserError]:
    """Retrieve a rule for a specific target type, optionally filtering by name."""
    candidates = rules_by_target.get(target_type, [])
    if not candidates:
        return Err(ParserError(f"No parser rule found for {target_type}"))

    if name is not None:
        for rule in candidates:
            if rule.name == name:
                return Ok(rule)

    return Ok(candidates[0])
