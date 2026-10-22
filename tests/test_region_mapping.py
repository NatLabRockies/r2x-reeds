"""Public tests for ReEDS county membership and region alignment."""

from pathlib import Path

import pytest

from r2x_reeds import (
    CountyMembership,
    CountyMembershipError,
    RegionAlignmentError,
    RegionAlignmentPolicy,
    RegionResolution,
    align_regions,
    load_county_membership,
)

TEST_DATA = Path(__file__).parent / "data"
EDGE_FIXTURES = TEST_DATA / "region_alignment"
INPUT_CASE = TEST_DATA / "test_Upgrader" / "inputs_case"


def _county_level_membership(balancing_areas: CountyMembership) -> CountyMembership:
    county_regions = {county: f"p{county}" for county in balancing_areas.county_to_region}
    return CountyMembership(
        region_to_counties={region: (county,) for county, region in county_regions.items()},
        county_to_region=county_regions,
        county_labels=balancing_areas.county_labels,
    )


def test_load_county2zone_normalizes_fips_and_preserves_labels() -> None:
    membership = load_county_membership(INPUT_CASE / "county2zone.csv")

    assert "53007" in membership.region_to_counties["p1"]
    assert membership.county_to_region["53007"] == "p1"
    assert membership.county_labels["53007"] == "chelan"


def test_align_county_and_balancing_area_memberships_in_both_orders() -> None:
    balancing_areas = load_county_membership(INPUT_CASE / "county2zone.csv")
    counties = _county_level_membership(balancing_areas)

    alignment = align_regions(balancing_areas, counties)
    reversed_alignment = align_regions(counties, balancing_areas)

    assert alignment.left_coverage == alignment.right_coverage == 1.0
    assert alignment.unmatched_left_regions == alignment.unmatched_right_regions == ()
    assert alignment.resolution is RegionResolution.LEFT_COARSER
    assert reversed_alignment.resolution is RegionResolution.RIGHT_COARSER
    assert (reversed_alignment.left_coverage, reversed_alignment.right_coverage) == (
        alignment.right_coverage,
        alignment.left_coverage,
    )
    assert {(item.left_region, item.right_region, item.counties) for item in alignment.matched_regions} == {
        (item.right_region, item.left_region, item.counties) for item in reversed_alignment.matched_regions
    }
    assert tuple(
        sorted(
            county
            for item in alignment.matched_regions
            if item.left_region == "p1"
            for county in item.counties
        )
    ) == (
        "53007",
        "53029",
        "53033",
        "53035",
        "53037",
        "53053",
        "53055",
        "53057",
        "53061",
        "53067",
        "53073",
    )


def test_explicit_policies_accept_nested_and_identical_partitions() -> None:
    balancing_areas = load_county_membership(INPUT_CASE / "county2zone.csv")
    counties = _county_level_membership(balancing_areas)
    run_counties = load_county_membership(INPUT_CASE / "r_county.csv")

    nested = align_regions(balancing_areas, counties, policy=RegionAlignmentPolicy.NESTED)
    identical = align_regions(balancing_areas, run_counties, policy="same_partition")

    assert nested.resolution is RegionResolution.LEFT_COARSER
    assert identical.resolution is RegionResolution.SAME_PARTITION


def test_partial_coverage_is_reported_and_can_be_required() -> None:
    balancing_areas = load_county_membership(INPUT_CASE / "county2zone.csv")
    partial_counties = load_county_membership(EDGE_FIXTURES / "r_county_partial.csv")

    alignment = align_regions(balancing_areas, partial_counties)

    assert alignment.left_coverage == 2 / len(balancing_areas.county_to_region)
    assert alignment.right_coverage == 1.0
    assert alignment.resolution is None
    assert "p1" in alignment.unmatched_left_regions
    assert "p2" not in alignment.unmatched_left_regions
    assert "p3" not in alignment.unmatched_left_regions
    with pytest.raises(RegionAlignmentError, match="missing from right: 06001"):
        align_regions(balancing_areas, partial_counties, require_complete=True)
    with pytest.raises(RegionAlignmentError, match="requires complete county coverage"):
        align_regions(balancing_areas, partial_counties, policy=RegionAlignmentPolicy.NESTED)


def test_county_universe_validation_uses_existing_complete_mapping_fixture() -> None:
    expected = load_county_membership(INPUT_CASE / "county2zone.csv")
    actual = load_county_membership(INPUT_CASE / "r_county.csv")

    result = align_regions(
        expected,
        actual,
        county_universe=expected.county_to_region,
        policy=RegionAlignmentPolicy.SAME_PARTITION,
    )

    assert result.left_coverage == result.right_coverage == 1.0
    assert result.resolution is RegionResolution.SAME_PARTITION


def test_county_universe_validation_reports_missing_expected_counties() -> None:
    expected = load_county_membership(INPUT_CASE / "county2zone.csv")
    partial = load_county_membership(EDGE_FIXTURES / "r_county_partial.csv")

    with pytest.raises(RegionAlignmentError, match="right is missing expected counties"):
        align_regions(expected, partial, county_universe=expected.county_to_region)


def test_county_universe_validation_reports_unexpected_counties() -> None:
    expected = load_county_membership(INPUT_CASE / "county2zone.csv")
    extra = CountyMembership(
        region_to_counties={"p1": ("53001", "53003", "99999"), "p2": ("53005", "53007")},
        county_to_region={
            "53001": "p1",
            "53003": "p1",
            "53005": "p2",
            "53007": "p2",
            "99999": "p1",
        },
        county_labels={},
    )

    with pytest.raises(RegionAlignmentError, match="right has counties outside the expected universe: 99999"):
        align_regions(expected, extra, county_universe=expected.county_to_region)


def test_nested_policy_rejects_crossing_region_partitions() -> None:
    left = CountyMembership(
        region_to_counties={"a": ("00001", "00002"), "b": ("00003", "00004")},
        county_to_region={"00001": "a", "00002": "a", "00003": "b", "00004": "b"},
        county_labels={},
    )
    right = CountyMembership(
        region_to_counties={"x": ("00001", "00003"), "y": ("00002", "00004")},
        county_to_region={"00001": "x", "00002": "y", "00003": "x", "00004": "y"},
        county_labels={},
    )

    assert align_regions(left, right).resolution is RegionResolution.CROSSING
    with pytest.raises(RegionAlignmentError, match="partitions cross"):
        align_regions(left, right, policy=RegionAlignmentPolicy.NESTED)


def test_ambiguous_county_assignment_reports_split() -> None:
    with pytest.raises(CountyMembershipError, match="split or ambiguously assigned"):
        load_county_membership(EDGE_FIXTURES / "r_county_ambiguous.csv")


def test_duplicate_county_assignment_is_rejected() -> None:
    with pytest.raises(CountyMembershipError, match="Duplicate county assignment"):
        load_county_membership(EDGE_FIXTURES / "r_county_duplicate.csv")
