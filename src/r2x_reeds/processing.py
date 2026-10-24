"""Typed ReEDS policies shared by the declarative input mapping."""

from __future__ import annotations

import re

import polars as pl
from pydantic import BaseModel, ConfigDict, Field, model_validator

from r2x_core.tabular_backend import StepHandlers

from .plugin_config import GeneratorClassificationOverride


class EmptyOptions(BaseModel):
    """Reject undeclared options for policy steps without configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class GeneratorClassificationOptions(BaseModel):
    """Exact exceptions layered over source technology-subset metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    overrides: list[GeneratorClassificationOverride] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_overrides(self) -> GeneratorClassificationOptions:
        technologies = [override.technology.casefold() for override in self.overrides]
        if len(set(technologies)) != len(technologies):
            msg = "Generator classification overrides must name each technology once"
            raise ValueError(msg)
        return self


class GeneratorPreparationOptions(BaseModel):
    """Configured fallback values used while preparing generator rows."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    default_heat_rate: float = Field(gt=0, allow_inf_nan=False)


_CATEGORY_FAMILY: dict[str, str] = {
    "thermal": "thermal",
    "solar": "variable",
    "wind": "variable",
    "geothermal": "variable",
    "hydro": "hydro",
    "storage": "storage",
    "pumped_storage": "storage",
    "imports": "generator",
}
_SUBSET_RANGE = re.compile(r"^(.*?)([0-9]+)\*(.*?)([0-9]+)$")
_THERMAL_MEMBERSHIPS = {"fossil", "nuclear", "bio", "ogs", "lfill", "h2_combustion"}
_SOLAR_MEMBERSHIPS = {"upv", "distpv", "pv", "pvb", "csp"}


def subset_flags(record: dict[str, object]) -> set[str]:
    """Return affirmative technology-subset columns from a normalized row."""
    return {
        name.casefold()
        for name, value in record.items()
        if name not in {"technology", "subset_technology"}
        and (value is True or (isinstance(value, str) and value.casefold() == "yes"))
    }


def matches_subset_name(technology: str, subset_name: str) -> bool:
    """Match exact names and ReEDS inclusive numeric-range notation."""
    normalized_name = subset_name.casefold()
    if "*" not in normalized_name:
        return technology.casefold() == normalized_name
    match = _SUBSET_RANGE.fullmatch(normalized_name)
    if match is None:
        msg = f"Invalid ReEDS technology range {subset_name!r}"
        raise ValueError(msg)
    start_prefix, start_number, end_prefix, end_number = match.groups()
    if start_prefix != end_prefix or not technology.casefold().startswith(start_prefix):
        return False
    suffix = technology.casefold()[len(start_prefix) :]
    return suffix.isdigit() and int(start_number) <= int(suffix) <= int(end_number)


def matched_subset_rows(technology: str, records: list[dict[str, object]]) -> list[dict[str, object]]:
    """Resolve exact metadata, numeric ranges, then underscore variants."""
    normalized = technology.casefold()
    exact = [record for record in records if str(record["subset_technology"]).casefold() == normalized]
    if exact:
        return exact

    ranged = [
        record
        for record in records
        if "*" in str(record["subset_technology"])
        and matches_subset_name(normalized, str(record["subset_technology"]))
    ]
    if ranged:
        return ranged

    suffix_matches = [
        record
        for record in records
        if "*" not in str(record["subset_technology"])
        and normalized.startswith(f"{str(record['subset_technology']).casefold()}_")
    ]
    if not suffix_matches:
        return []
    longest_name = max(len(str(record["subset_technology"])) for record in suffix_matches)
    return [record for record in suffix_matches if len(str(record["subset_technology"])) == longest_name]


def category_from_subset(flags: set[str], *, technology: str) -> str | None:
    """Derive the parser category from ReEDS memberships and narrow aliases."""
    if "consume" in flags:
        return None
    if "canada" in flags:
        return "imports"
    if "hydro" in flags:
        return "hydro"
    if "geo" in flags:
        return "geothermal"
    if "wind" in flags:
        return "wind"
    if flags & _SOLAR_MEMBERSHIPS:
        return "solar"
    if "psh" in flags:
        return "pumped_storage"
    if flags & {"storage_standalone", "battery"}:
        return "storage"
    if flags & _THERMAL_MEMBERSHIPS:
        return "thermal"

    if technology == "caes" or technology.startswith("battery_"):
        return "storage"
    if technology == "dupv":
        return "solar"
    if technology.startswith("rtes"):
        return "geothermal"
    return None


class ClassifyGeneratorCategories:
    """Normalize source memberships into parser family, category, and policy flags."""

    options_model: type[GeneratorClassificationOptions] = GeneratorClassificationOptions
    input_type: type[pl.LazyFrame] = pl.LazyFrame
    output_type: type[pl.LazyFrame] = pl.LazyFrame

    def apply(self, value: pl.LazyFrame, *, options: GeneratorClassificationOptions) -> pl.LazyFrame:
        """Classify each technology from its matching subset-table row."""
        records = value.collect().to_dicts()
        if not records:
            return pl.DataFrame(
                schema={
                    "technology": pl.String,
                    "component_family": pl.String,
                    "category": pl.String,
                    "is_dispatchable": pl.Boolean,
                    "parser_supported": pl.Boolean,
                    "memberships": pl.List(pl.String),
                }
            ).lazy()

        technologies = sorted({str(record["technology"]) for record in records})
        rows_by_technology = {
            technology: [record for record in records if str(record["technology"]) == technology]
            for technology in technologies
        }
        overrides = {override.technology.casefold(): override for override in options.overrides}
        classified: list[dict[str, object]] = []
        for technology in technologies:
            normalized = technology.casefold()
            matched = matched_subset_rows(normalized, rows_by_technology[technology])
            flags = subset_flags(matched[0]) if matched else set()
            if {"hydro_d", "hydro_nd"}.issubset(flags):
                msg = f"Technology {technology!r} is both dispatchable and nondispatchable hydro"
                raise ValueError(msg)

            category = category_from_subset(flags, technology=normalized)
            dispatchable = "hydro_d" in flags
            parser_supported = category is not None and "consume" not in flags
            memberships = set(flags)
            if "re" in flags:
                memberships.add("renewable")
            if "vre" in flags:
                memberships.add("variable_renewable")
            if "hydro_d" in flags:
                memberships.add("hydro_dispatchable")
            if "hydro_nd" in flags:
                memberships.add("hydro_nondispatchable")

            override = overrides.get(normalized)
            if override is not None:
                category = override.category
                dispatchable = dispatchable if override.is_dispatchable is None else override.is_dispatchable
                parser_supported = True if override.parser_supported is None else override.parser_supported

            component_family = _CATEGORY_FAMILY.get(category) if category is not None else None
            if category is not None:
                memberships.add(category)
            if component_family == "thermal":
                memberships.add("thermal")
            classified.append(
                {
                    "technology": technology,
                    "component_family": component_family,
                    "category": category,
                    "is_dispatchable": dispatchable,
                    "parser_supported": parser_supported,
                    "memberships": sorted(memberships),
                }
            )

        return pl.DataFrame(classified).lazy()


class PrepareGeneratorRows:
    """Apply shared ReEDS generator defaults and identity preparation."""

    options_model: type[GeneratorPreparationOptions] = GeneratorPreparationOptions
    input_type: type[pl.LazyFrame] = pl.LazyFrame
    output_type: type[pl.LazyFrame] = pl.LazyFrame

    def apply(self, value: pl.LazyFrame, *, options: GeneratorPreparationOptions) -> pl.LazyFrame:
        """Resolve fuel policy, defaults, names, and normalized capacity."""
        thermal = pl.col("component_family") == "thermal"
        frame = value.with_columns(
            pl.coalesce("direct_fuel_type", "fuel_type_full", "fuel_type_base").alias("fuel_type")
        )
        return frame.with_columns(
            pl.when(thermal)
            .then(pl.coalesce("heat_rate", "heat_rate_mean", pl.lit(options.default_heat_rate)))
            .otherwise(pl.col("heat_rate"))
            .alias("heat_rate"),
            pl.when(thermal)
            .then(pl.coalesce("fuel_type", pl.lit("OTHER")))
            .otherwise(pl.col("fuel_type"))
            .alias("fuel_type"),
            pl.when(pl.col("fuel_type") == "biomass")
            .then(pl.coalesce("biofuel_price", "fuel_price"))
            .otherwise(pl.col("fuel_price"))
            .alias("fuel_price"),
            pl.coalesce("storage_duration", "duration_out_value").alias("storage_duration"),
            pl.coalesce("round_trip_efficiency", pl.lit(1.0)).alias("round_trip_efficiency"),
            pl.col("maxage_years").alias("max_age"),
            pl.col("min_load_frac").alias("min_stable_level"),
            pl.when(thermal).then(pl.col("technology")).otherwise(pl.col("category")).alias("category"),
            pl.when(pl.col("vintage").is_null())
            .then(
                pl.concat_str(
                    [
                        pl.col("technology"),
                        pl.lit("_"),
                        pl.col("region"),
                        pl.lit("_"),
                        pl.col("year").cast(pl.String),
                    ]
                )
            )
            .otherwise(
                pl.concat_str(
                    [
                        pl.col("technology"),
                        pl.lit("_"),
                        pl.col("vintage"),
                        pl.lit("_"),
                        pl.col("region"),
                        pl.lit("_"),
                        pl.col("year").cast(pl.String),
                    ]
                )
            )
            .alias("name"),
            pl.when(pl.col("capacity") <= 1e-8)
            .then(pl.lit(0.0))
            .otherwise(pl.col("capacity"))
            .alias("capacity"),
        )


class ResolveGeneratorFomCosts:
    """Apply ordered fixed O&M precedence to prepared generator policy rows."""

    options_model: type[EmptyOptions] = EmptyOptions
    input_type: type[pl.LazyFrame] = pl.LazyFrame
    output_type: type[pl.LazyFrame] = pl.LazyFrame

    def apply(self, value: pl.LazyFrame, *, options: EmptyOptions) -> pl.LazyFrame:
        """Resolve base, hintage, hydro, upgrade, retrofit, and storage costs."""
        del options
        distpv = pl.col("distpv") == "yes"
        has_upgrade = pl.col("target_technology").is_not_null()
        resolved_retrofit = (
            pl.when(pl.col("source_current_retrofit") != 0)
            .then(pl.col("source_current_retrofit"))
            .when(pl.col("retrofit_eligible"))
            .then(pl.col("prior_retrofit_fom"))
            .otherwise(None)
        )
        base_fom = pl.when(distpv).then(pl.col("hintage_fom_cost")).otherwise(pl.col("base_fom"))
        upgrade_fom = pl.when(pl.col("vintage").str.starts_with("init"))
        upgrade_fom = upgrade_fom.then(
            pl.col("initial_target_fom") + pl.col("target_hydro_fom").fill_null(0)
        ).otherwise(pl.col("target_fom"))
        fom = pl.when(pl.col("hydro_fom_cost") != 0).then(pl.col("hydro_fom_cost")).otherwise(base_fom)
        fom = pl.when(has_upgrade).then(upgrade_fom).otherwise(fom)
        retrofit_applies = (
            pl.col("vintage").str.starts_with("init")
            & has_upgrade
            & pl.col("unit_spec_upgrade")
            & pl.col("target_is_ccs")
            & pl.col("retrofit_enabled")
            & (resolved_retrofit != 0)
        )
        fom = pl.when(retrofit_applies).then(resolved_retrofit).otherwise(fom)
        fom = pl.when(pl.col("psh") == "yes").then(pl.col("psh_fom_cost")).otherwise(fom)
        return value.with_columns(
            has_upgrade.alias("has_upgrade_target"),
            fom.alias("fom_cost"),
        )


class ResolveResourceReferences:
    """Prefer supply-curve rows, enrich matches, and use candidates when supply is absent."""

    options_model: type[EmptyOptions] = EmptyOptions
    input_type: type[pl.LazyFrame] = pl.LazyFrame
    output_type: type[pl.LazyFrame] = pl.LazyFrame

    def apply(self, value: pl.LazyFrame, *, options: EmptyOptions) -> pl.LazyFrame:
        """Resolve the shared ReEDS resource-source precedence once across technologies."""
        del options
        keys = ["technology", "sc_point_gid", "resource_class"]
        fields = [
            "sc_gid",
            "available_capacity",
            "capacity_factor",
            "latitude",
            "longitude",
            "existing_capacity",
            "online_year",
            "retire_year",
            "bin",
            "capacity",
            "supply_curve_cost",
        ]
        supply_rows = value.filter(pl.col("resource_source") == "supply").drop("resource_source")
        candidate_rows = value.filter(pl.col("resource_source") == "candidate").drop("resource_source")
        candidate_values = candidate_rows.select(
            *keys,
            *(pl.col(field).alias(f"candidate_{field}") for field in fields),
        ).unique(subset=keys)
        enriched_supply = (
            supply_rows.join(candidate_values, on=keys, how="left")
            .with_columns([pl.coalesce(field, f"candidate_{field}").alias(field) for field in fields])
            .drop([f"candidate_{field}" for field in fields])
        )
        supply_technologies = supply_rows.select("technology").unique()
        candidate_fallback = candidate_rows.join(supply_technologies, on="technology", how="anti")
        return pl.concat([enriched_supply, candidate_fallback], how="vertical")


def reeds_step_handlers() -> StepHandlers:
    """Register typed ReEDS policy operations with core's mapping executor."""
    return {
        "classify_generator_categories": ClassifyGeneratorCategories(),
        "prepare_generator_rows": PrepareGeneratorRows(),
        "resolve_generator_fom_costs": ResolveGeneratorFomCosts(),
        "resolve_resource_references": ResolveResourceReferences(),
    }
