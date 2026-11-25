"""Explicit technology relationships determine fractional generator ramp rates."""

import json
from importlib.resources import files

import polars as pl
import pytest

from r2x_reeds.parser_utils import resolve_generator_ramp_rates


@pytest.fixture
def technology_categories():
    return json.loads(files("r2x_reeds.config").joinpath("defaults.json").read_text())["tech_categories"]


def ramp_data(rows=()):
    return pl.DataFrame(rows, schema={"technology": pl.String, "ramp_rate": pl.Float64}, orient="row")


def upgrade_links(rows=()):
    return pl.DataFrame(rows, schema={"technology": pl.String, "target_technology": pl.String}, orient="row")


def cooling_links(rows=()):
    return pl.DataFrame(rows, schema={"technology": pl.String, "base_technology": pl.String}, orient="row")


@pytest.mark.parametrize(
    "technology,destination,base,expected",
    [
        ("gas-CC_r_fsa", None, "gas-CC", 0.05),
        ("gas-CC_r_fsa_H2-CC", "H2-CC", None, 0.08),
        (
            "CoalOldUns_r_fsa_coal-CCS_mod_r_fsa",
            "coal-CCS_mod_r_fsa",
            "coal-CCS_mod",
            0.02,
        ),
        (
            "gas-CC_r_fsa_Gas-CC-CCS_mod_r_fsa",
            "Gas-CC-CCS_mod_r_fsa",
            "Gas-CC-CCS_mod",
            0.05,
        ),
    ],
)
def test_cooling_and_upgrade_relationships_resolve_base_rates(
    technology_categories, technology, destination, base, expected
):
    result = resolve_generator_ramp_rates(
        [technology],
        ramp_data([(technology, 0.9), (base or destination, expected)]),
        upgrade_links([(technology, destination)] if destination else []),
        technology_categories,
        cooling_links=cooling_links([(destination or technology, base)] if base else []),
    ).unwrap()

    assert result.to_dicts() == [{"technology": technology, "ramp_rate": expected}]


@pytest.mark.parametrize(
    "technology,destination,base",
    [
        ("Gas-CC_H_1x1_r_fsa", None, "Gas-CC_H_1x1"),
        (
            "Gas-CC_H_1x1_r_fsa_Gas-CC_H_1x1-CCS_mod_r_fsa",
            "Gas-CC_H_1x1-CCS_mod_r_fsa",
            "Gas-CC_H_1x1-CCS_mod",
        ),
    ],
)
def test_cooling_lookup_is_case_insensitive_and_preserves_technology_labels(
    technology_categories, technology, destination, base
):
    result = resolve_generator_ramp_rates(
        [technology],
        ramp_data([(base.swapcase(), 0.05)]),
        upgrade_links([(technology.swapcase(), destination.swapcase())] if destination else []),
        technology_categories,
        cooling_links=cooling_links([((destination or technology).swapcase(), base.swapcase())]),
    ).unwrap()

    assert result.to_dicts() == [{"technology": technology, "ramp_rate": 0.05}]


@pytest.mark.parametrize(
    "technology",
    ["Gas-CC_H_1x1_r_fsa", "Gas-CC_H_1x1_r_fsa_H2-CC"],
)
def test_cooling_names_do_not_imply_relationships(technology_categories, technology):
    result = resolve_generator_ramp_rates(
        [technology],
        ramp_data([("Gas-CC", 0.04), ("Gas-CC_H_1x1", 0.05), ("H2-CC", 0.08)]),
        upgrade_links(),
        technology_categories,
        cooling_links=cooling_links(),
    ).unwrap()

    assert result.to_dicts() == [{"technology": technology, "ramp_rate": None}]


@pytest.mark.parametrize(
    "technology,destination,expected",
    [
        ("gas-cc_gas-cc-ccs_mod", "gas-cc-ccs_mod", 0.05),
        ("gas-cc_h2-cc", "h2-cc", 0.08),
        ("gas-ct_h2-ct", "h2-ct", 0.08),
        ("coal-new_coal-ccs_mod", "coal-ccs_mod", 0.02),
        ("coaloldscr_coal-ccs_mod", "coal-ccs_mod", 0.02),
        ("coalolduns_coal-ccs_mod", "coal-ccs_mod", 0.02),
    ],
)
def test_upgrades_inherit_destination_not_own_rate(technology_categories, technology, destination, expected):
    result = resolve_generator_ramp_rates(
        [technology],
        ramp_data([(technology, 0.9), (destination, expected)]),
        upgrade_links([(technology, destination)]),
        technology_categories,
    ).unwrap()

    assert result.to_dicts() == [{"technology": technology, "ramp_rate": expected}]


def test_multistep_upgrade_lookup_is_case_insensitive_and_preserves_labels(technology_categories):
    result = resolve_generator_ramp_rates(
        ["Gas-CC_First", "GAS-CC_SECOND"],
        ramp_data([("H2-CC", 0.08)]),
        upgrade_links([("gas-cc_first", "gas-cc_second"), ("Gas-CC_Second", "h2-cc")]),
        technology_categories,
    ).unwrap()

    assert result.to_dicts() == [
        {"technology": "Gas-CC_First", "ramp_rate": 0.08},
        {"technology": "GAS-CC_SECOND", "ramp_rate": 0.08},
    ]


@pytest.mark.parametrize("technology", ["hydD", "hydSD", "hydUD", "hydNPD", "HyDeD", "hydro-d"])
def test_dispatchable_hydro_inherits_generic_rate(technology_categories, technology):
    result = resolve_generator_ramp_rates(
        [technology],
        ramp_data([("Hydro", 1.0), (technology, 0.05)]),
        upgrade_links(),
        technology_categories,
    ).unwrap()

    assert result["ramp_rate"].to_list() == [1.0]


@pytest.mark.parametrize("technology", ["hydND", "hydSND", "hydUND", "hydNPND", "hydEND"])
@pytest.mark.parametrize("explicit_rate", [None, 0.12])
def test_nondispatchable_hydro_only_uses_its_exact_rate(technology_categories, technology, explicit_rate):
    rows = [("Hydro", 1.0)]
    if explicit_rate is not None:
        rows.append((technology, explicit_rate))
    result = resolve_generator_ramp_rates(
        [technology], ramp_data(rows), upgrade_links(), technology_categories
    ).unwrap()

    assert result["ramp_rate"].to_list() == [explicit_rate]


@pytest.mark.parametrize("value", [0.0, 0.05, 1.0, 3.0])
def test_exact_rates_are_not_scaled_or_restricted_to_one(technology_categories, value):
    result = resolve_generator_ramp_rates(
        ["Gas-CC", "wind-ons_1"],
        ramp_data([("gas-cc", value), ("wind-ons_1", value)]),
        upgrade_links(),
        technology_categories,
    ).unwrap()

    assert result["ramp_rate"].to_list() == [value, value]


@pytest.mark.parametrize("data", [None, ramp_data(), ramp_data([("gas-cc", None)])])
def test_missing_rates_remain_nullable_float64(technology_categories, data):
    result = resolve_generator_ramp_rates(
        ["gas-cc", "hyded", "unknown", "gas-cc_missing"],
        data,
        upgrade_links([("gas-cc_missing", "missing-destination")]),
        technology_categories,
    ).unwrap()

    assert result.schema == {"technology": pl.String, "ramp_rate": pl.Float64}
    assert result["ramp_rate"].to_list() == [None] * 4


@pytest.mark.parametrize(
    "base_rows,expected", [([], None), ([("gas-cc", None)], None), ([("gas-cc", 0.0)], 0.0)]
)
@pytest.mark.parametrize("upgraded", [False, True])
def test_cooling_base_missing_rates_and_zero_do_not_fall_back(
    technology_categories, base_rows, expected, upgraded
):
    destination = "gas-cc_r_fsa"
    technology = "gas-cc_r_fsa_upgrade" if upgraded else destination
    result = resolve_generator_ramp_rates(
        [technology],
        ramp_data([("gas-cc_r_fsa_upgrade", 0.9), (destination, 0.8), *base_rows]),
        upgrade_links([(technology, destination)] if upgraded else []),
        technology_categories,
        cooling_links=cooling_links([(destination, "gas-cc")]),
    ).unwrap()

    assert result.schema == {"technology": pl.String, "ramp_rate": pl.Float64}
    assert result.to_dicts() == [{"technology": technology, "ramp_rate": expected}]


def test_missing_cooling_map_does_not_infer_destination_base(technology_categories):
    technology = "CoalOldUns_r_fsa_coal-CCS_mod_r_fsa"
    result = resolve_generator_ramp_rates(
        [technology],
        ramp_data([(technology, 0.9), ("coalolduns", 0.03), ("coal-ccs_mod", 0.02)]),
        upgrade_links([(technology, "coal-CCS_mod_r_fsa")]),
        technology_categories,
        cooling_links=cooling_links(),
    ).unwrap()

    assert result.to_dicts() == [{"technology": technology, "ramp_rate": None}]


def test_underscore_names_do_not_imply_upgrade_relationships(technology_categories):
    result = resolve_generator_ramp_rates(
        ["gas-cc_h2-cc"],
        ramp_data([("gas-cc", 0.05), ("h2-cc", 0.08)]),
        upgrade_links(),
        technology_categories,
    ).unwrap()

    assert result["ramp_rate"].to_list() == [None]


def test_identical_duplicate_rates_and_destinations_are_allowed(technology_categories):
    result = resolve_generator_ramp_rates(
        ["gas-cc_h2-cc"],
        ramp_data([("h2-cc", 0.08), ("H2-CC", 0.08)]),
        upgrade_links([("gas-cc_h2-cc", "h2-cc"), ("GAS-CC_H2-CC", "H2-CC")]),
        technology_categories,
    ).unwrap()

    assert result["ramp_rate"].to_list() == [0.08]


def test_identical_duplicate_cooling_bases_are_allowed(technology_categories):
    result = resolve_generator_ramp_rates(
        ["gas-cc_r_fsa"],
        ramp_data([("gas-cc", 0.05)]),
        upgrade_links(),
        technology_categories,
        cooling_links=cooling_links([("gas-cc_r_fsa", "gas-cc"), ("GAS-CC_R_FSA", "GAS-CC")]),
    ).unwrap()

    assert result["ramp_rate"].to_list() == [0.05]


@pytest.mark.parametrize(
    "cooling_rows,upgrade_rows,message",
    [
        (
            [("gas-cc_r_fsa", "gas-cc"), ("GAS-CC_R_FSA", "h2-cc")],
            [],
            "Ambiguous cooling base technologies",
        ),
        ([("gas-cc_r_fsa", "gas-cc_r_fsa")], [], "Cyclic"),
        (
            [("gas-cc_r_fsa", "gas-cc"), ("gas-cc", "gas-cc_r_fsa")],
            [],
            "Cyclic",
        ),
        (
            [("gas-cc_r_fsa", "gas-cc_h2-cc")],
            [("gas-cc_h2-cc", "gas-cc_r_fsa")],
            "Cyclic",
        ),
    ],
)
def test_invalid_cooling_relationships_fail_even_outside_active_technologies(
    technology_categories, cooling_rows, upgrade_rows, message, caplog
):
    result = resolve_generator_ramp_rates(
        ["gas-ct"],
        ramp_data([("gas-ct", 0.08)]),
        upgrade_links(upgrade_rows),
        technology_categories,
        cooling_links=cooling_links(cooling_rows),
    )

    assert result.is_err()
    error = result.unwrap_err()
    assert message in error
    assert "gas-cc_r_fsa" in error.casefold()
    assert error in caplog.text
    if message == "Cyclic":
        assert " -> " in error
        assert all(technology.casefold() in error for technology, _ in cooling_rows + upgrade_rows)


def test_upgrade_destination_precedes_cooling_base(technology_categories):
    technology = "gas-CC_r_fsa_H2-CC"
    result = resolve_generator_ramp_rates(
        [technology],
        ramp_data([(technology, 0.9), ("gas-cc", 0.05), ("h2-cc", 0.08)]),
        upgrade_links([(technology, "h2-cc")]),
        technology_categories,
        cooling_links=cooling_links([(technology, "gas-cc")]),
    ).unwrap()

    assert result.to_dicts() == [{"technology": technology, "ramp_rate": 0.08}]


@pytest.mark.parametrize("exact_rate", [None, 0.12])
def test_nonthermal_nonhydro_technologies_do_not_inherit_cooling_rates(technology_categories, exact_rate):
    technology = "csp1_1_r_fsa"
    rows = [("csp1_1", 0.05)]
    if exact_rate is not None:
        rows.append((technology, exact_rate))
    result = resolve_generator_ramp_rates(
        [technology],
        ramp_data(rows),
        upgrade_links(),
        technology_categories,
        cooling_links=cooling_links([(technology, "csp1_1")]),
    ).unwrap()

    assert result.to_dicts() == [{"technology": technology, "ramp_rate": exact_rate}]


@pytest.mark.parametrize(
    "rows",
    [
        [("gas-cc", 0.05), ("GAS-CC", 0.08)],
        [("gas-cc", None), ("gas-cc", 0.05)],
    ],
)
def test_conflicting_duplicate_rates_fail_loudly(technology_categories, rows, caplog):
    result = resolve_generator_ramp_rates(["gas-cc"], ramp_data(rows), upgrade_links(), technology_categories)

    assert result.is_err()
    assert "Conflicting ramp rates" in result.unwrap_err()
    assert "Conflicting ramp rates" in caplog.text


@pytest.mark.parametrize("value", [-0.1, float("nan"), float("inf"), -float("inf"), True])
def test_invalid_rates_fail_loudly(technology_categories, value, caplog):
    data = pl.DataFrame({"technology": ["gas-cc"], "ramp_rate": [value]})
    result = resolve_generator_ramp_rates(["gas-cc"], data, upgrade_links(), technology_categories)

    assert result.is_err()
    assert "Invalid ramp rate" in result.unwrap_err()
    assert "gas-cc" in result.unwrap_err()
    assert "Invalid ramp rate" in caplog.text


@pytest.mark.parametrize(
    "rows,message",
    [
        ([("gas-cc_upgrade", "h2-cc"), ("GAS-CC_UPGRADE", "gas-cc")], "Ambiguous"),
        ([("gas-cc_upgrade", "gas-cc_upgrade")], "Cyclic"),
        ([("gas-cc_a", "gas-cc_b"), ("gas-cc_b", "gas-cc_a")], "Cyclic"),
    ],
)
def test_invalid_relationships_fail_even_outside_active_technologies(
    technology_categories, rows, message, caplog
):
    result = resolve_generator_ramp_rates(
        ["gas-cc"], ramp_data([("gas-cc", 0.05)]), upgrade_links(rows), technology_categories
    )

    assert result.is_err()
    assert message in result.unwrap_err()
    assert rows[-1][0] in result.unwrap_err()
    assert message in caplog.text


@pytest.mark.parametrize("invalid_label", ["", "  ", None, 123])
@pytest.mark.parametrize("source", ["generator", "ramp", "upgrade", "destination"])
def test_invalid_technology_labels_fail(technology_categories, invalid_label, source):
    technologies = [invalid_label] if source == "generator" else ["gas-cc"]
    data = (
        pl.DataFrame({"technology": [invalid_label], "ramp_rate": [0.05]})
        if source == "ramp"
        else ramp_data()
    )
    links = (
        pl.DataFrame(
            {
                "technology": [invalid_label if source == "upgrade" else "gas-cc_upgrade"],
                "target_technology": [invalid_label if source == "destination" else "gas-cc"],
            }
        )
        if source in {"upgrade", "destination"}
        else upgrade_links()
    )
    result = resolve_generator_ramp_rates(technologies, data, links, technology_categories)

    assert result.is_err()
    assert "Invalid technology label" in result.unwrap_err()
