"""Focused behavioral tests for shared ReEDS mapping policy."""

import polars as pl

from r2x_reeds.plugin_config import GeneratorClassificationOverride
from r2x_reeds.processing import (
    ClassifyGeneratorCategories,
    EmptyOptions,
    GeneratorClassificationOptions,
    GeneratorPreparationOptions,
    PrepareGeneratorRows,
    ResolveGeneratorFomCosts,
    ResolveResourceReferences,
)


def test_generator_classification_uses_overlapping_reeds_memberships() -> None:
    frame = pl.DataFrame(
        [
            {
                "technology": "upv_2",
                "subset_technology": "upv_1*upv_10",
                "re": "yes",
                "vre": "yes",
                "upv": "yes",
                "pv": "yes",
            },
            {
                "technology": "csp1_12",
                "subset_technology": "csp1_1*csp1_12",
                "re": "yes",
                "csp": "yes",
                "csp_storage": "yes",
                "storage": "yes",
                "storage_hybrid": "yes",
            },
            {
                "technology": "pvb1_3",
                "subset_technology": "pvb1_1*pvb1_10",
                "pvb": "yes",
                "pvb1": "yes",
                "storage": "yes",
                "storage_hybrid": "yes",
            },
            {
                "technology": "hyded",
                "subset_technology": "hyded",
                "hydro": "yes",
                "hydro_d": "yes",
                "re": "yes",
            },
            {
                "technology": "hydend",
                "subset_technology": "hydend",
                "hydro": "yes",
                "hydro_nd": "yes",
                "re": "yes",
            },
            {
                "technology": "electrolyzer",
                "subset_technology": "electrolyzer",
                "consume": "yes",
                "h2": "yes",
            },
            {
                "technology": "gas-cc",
                "subset_technology": "gas-cc",
                "conv": "yes",
                "fossil": "yes",
            },
        ]
    ).lazy()

    result = (
        ClassifyGeneratorCategories()
        .apply(
            frame,
            options=GeneratorClassificationOptions(
                overrides=[GeneratorClassificationOverride(technology="gas-cc", category="wind")]
            ),
        )
        .collect()
        .sort("technology")
    )

    rows = {row["technology"]: row for row in result.to_dicts()}
    assert (rows["upv_2"]["component_family"], rows["upv_2"]["category"]) == ("variable", "solar")
    assert {"upv", "pv", "re", "vre", "solar", "renewable", "variable_renewable"}.issubset(
        rows["upv_2"]["memberships"]
    )
    assert (rows["csp1_12"]["component_family"], rows["csp1_12"]["category"]) == (
        "variable",
        "solar",
    )
    assert "storage" in rows["csp1_12"]["memberships"]
    assert (rows["pvb1_3"]["component_family"], rows["pvb1_3"]["category"]) == (
        "variable",
        "solar",
    )
    assert "re" not in rows["pvb1_3"]["memberships"]
    assert (rows["hyded"]["category"], rows["hyded"]["is_dispatchable"]) == ("hydro", True)
    assert (rows["hydend"]["category"], rows["hydend"]["is_dispatchable"]) == ("hydro", False)
    assert rows["electrolyzer"]["parser_supported"] is False
    assert rows["electrolyzer"]["component_family"] is None
    assert (rows["gas-cc"]["component_family"], rows["gas-cc"]["category"]) == (
        "variable",
        "wind",
    )
    assert "thermal" not in rows["gas-cc"]["memberships"]


def test_generator_preparation_applies_shared_defaults_and_identity() -> None:
    frame = pl.DataFrame(
        {
            "technology": ["gas-cc", "biopower", "upv_1"],
            "component_family": ["thermal", "thermal", "variable"],
            "category": ["thermal", "thermal", "solar"],
            "direct_fuel_type": [None, None, None],
            "fuel_type_full": [None, "biomass", None],
            "fuel_type_base": [None, None, None],
            "heat_rate": [None, None, None],
            "heat_rate_mean": [None, None, None],
            "biofuel_price": [None, 3.5, None],
            "fuel_price": [4.0, 10.0, None],
            "storage_duration": [None, 4.0, None],
            "duration_out_value": [2.0, 9.0, None],
            "round_trip_efficiency": [None, 0.8, None],
            "maxage_years": [40, 30, 20],
            "min_load_frac": [0.3, 0.1, None],
            "vintage": ["init-1", None, "new1"],
            "region": ["p1", "p2", "p3"],
            "year": [2032, 2032, 2032],
            "capacity": [1e-9, 5.0, 10.0],
        }
    ).lazy()

    result = (
        PrepareGeneratorRows()
        .apply(frame, options=GeneratorPreparationOptions(default_heat_rate=12.0))
        .collect()
    )

    assert result.select(
        "name",
        "category",
        "capacity",
        "heat_rate",
        "fuel_type",
        "fuel_price",
        "storage_duration",
        "round_trip_efficiency",
        "max_age",
        "min_stable_level",
    ).to_dicts() == [
        {
            "name": "gas-cc_init-1_p1_2032",
            "category": "gas-cc",
            "capacity": 0.0,
            "heat_rate": 12.0,
            "fuel_type": "OTHER",
            "fuel_price": 4.0,
            "storage_duration": 2.0,
            "round_trip_efficiency": 1.0,
            "max_age": 40,
            "min_stable_level": 0.3,
        },
        {
            "name": "biopower_p2_2032",
            "category": "biopower",
            "capacity": 5.0,
            "heat_rate": 12.0,
            "fuel_type": "biomass",
            "fuel_price": 3.5,
            "storage_duration": 4.0,
            "round_trip_efficiency": 0.8,
            "max_age": 30,
            "min_stable_level": 0.1,
        },
        {
            "name": "upv_1_new1_p3_2032",
            "category": "solar",
            "capacity": 10.0,
            "heat_rate": None,
            "fuel_type": None,
            "fuel_price": None,
            "storage_duration": None,
            "round_trip_efficiency": 1.0,
            "max_age": 20,
            "min_stable_level": None,
        },
    ]


def test_generator_fom_policy_applies_precedence_in_domain_order() -> None:
    frame = pl.DataFrame(
        {
            "distpv": ["no", "yes", "no", "no", "no"],
            "source_current_retrofit": [0.0, 0.0, 0.0, 55.0, 0.0],
            "retrofit_eligible": [False, False, False, True, False],
            "prior_retrofit_fom": [None, None, None, 66.0, None],
            "target_technology": [None, None, None, "coal-ccs", "coal-ccs"],
            "vintage": ["init-1", "init-1", "init-1", "init-1", "new1"],
            "initial_target_fom": [0.0, 0.0, 0.0, 40.0, 0.0],
            "target_hydro_fom": [None, None, None, None, None],
            "target_fom": [None, None, None, 45.0, 46.0],
            "hydro_fom_cost": [0.0, 0.0, 42.0, 0.0, 0.0],
            "unit_spec_upgrade": [False, False, False, True, False],
            "target_is_ccs": [False, False, False, True, False],
            "retrofit_enabled": [False, False, False, True, False],
            "psh": ["no", "no", "no", "no", "yes"],
            "psh_fom_cost": [None, None, None, None, 60.0],
            "base_fom": [10.0, 11.0, 12.0, 13.0, 14.0],
            "hintage_fom_cost": [None, 20.0, None, None, None],
        }
    ).lazy()

    result = ResolveGeneratorFomCosts().apply(frame, options=EmptyOptions()).collect()

    assert result.get_column("fom_cost").to_list() == [10.0, 20.0, 42.0, 55.0, 60.0]
    assert result.get_column("has_upgrade_target").to_list() == [False, False, False, True, True]


def test_resource_references_prefer_supply_and_fallback_only_when_supply_absent() -> None:
    frame = pl.DataFrame(
        {
            "technology": ["upv", "upv", "wind-ons"],
            "sc_point_gid": [1, 1, 2],
            "resource_class": ["1", "1", "2"],
            "resource_source": ["supply", "candidate", "candidate"],
            "sc_gid": [10, 11, 20],
            "available_capacity": [None, 200.0, 300.0],
            "capacity_factor": [0.2, 0.4, 0.5],
            "latitude": [45.0, 46.0, 47.0],
            "longitude": [-120.0, -121.0, -122.0],
            "existing_capacity": [5.0, 6.0, 7.0],
            "online_year": [2020, 2021, 2022],
            "retire_year": [2050, 2051, 2052],
            "bin": ["init-1", "new1", "new2"],
            "capacity": [100.0, 400.0, 500.0],
            "supply_curve_cost": [10.0, 12.0, 13.0],
            "year": [None, None, None],
            "built_capacity": [None, None, None],
            "investment_bool": [None, None, None],
        }
    ).lazy()

    result = ResolveResourceReferences().apply(frame, options=EmptyOptions()).collect()
    rows = {row["technology"]: row for row in result.to_dicts()}

    assert set(rows) == {"upv", "wind-ons"}
    assert (rows["upv"]["sc_gid"], rows["upv"]["available_capacity"]) == (10, 200.0)
    assert (rows["upv"]["capacity"], rows["upv"]["supply_curve_cost"]) == (100.0, 10.0)
    assert (rows["wind-ons"]["sc_gid"], rows["wind-ons"]["supply_curve_cost"]) == (20, 13.0)
    assert "resource_source" not in result.columns
