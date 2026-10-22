"""County membership loading and region alignment for ReEDS runs."""

from __future__ import annotations

import csv
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType


class CountyMembershipError(ValueError):
    """A county membership file contains invalid or conflicting assignments."""


class RegionAlignmentError(ValueError):
    """Two county memberships cannot satisfy the requested alignment rules."""


class RegionAlignmentPolicy(StrEnum):
    """Compatibility rule to apply when aligning two region partitions."""

    CROSSWALK = "crosswalk"
    NESTED = "nested"
    SAME_PARTITION = "same_partition"


class RegionResolution(StrEnum):
    """Observed relationship between two complete county partitions."""

    SAME_PARTITION = "same_partition"
    LEFT_COARSER = "left_coarser"
    RIGHT_COARSER = "right_coarser"
    CROSSING = "crossing"


@dataclass(frozen=True, slots=True)
class CountyMembership:
    """County assignments for one ReEDS run.

    ``region_to_counties`` maps each displayed region label to normalized,
    five-digit FIPS keys. ``county_to_region`` is its inverse, and
    ``county_labels`` retains the source display label for each FIPS key.
    """

    region_to_counties: Mapping[str, tuple[str, ...]]
    county_to_region: Mapping[str, str]
    county_labels: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "region_to_counties",
            MappingProxyType(
                {region: tuple(counties) for region, counties in self.region_to_counties.items()}
            ),
        )
        object.__setattr__(self, "county_to_region", MappingProxyType(dict(self.county_to_region)))
        object.__setattr__(self, "county_labels", MappingProxyType(dict(self.county_labels)))


@dataclass(frozen=True, slots=True)
class RegionMatch:
    """One overlapping region pair and the counties contributing to it."""

    left_region: str
    right_region: str
    counties: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RegionAlignment:
    """County-based alignment between two runs, independent of load data.

    Coverage is the fraction of each run's mapped counties present in both
    memberships. Matches may pair one balancing area with many county regions.
    """

    matched_regions: tuple[RegionMatch, ...]
    unmatched_left_regions: tuple[str, ...]
    unmatched_right_regions: tuple[str, ...]
    left_coverage: float
    right_coverage: float
    resolution: RegionResolution | None


def normalize_county_fips(value: str) -> str:
    """Normalize a county identifier to its stable five-digit FIPS key.

    ReEDS ``r_county.csv`` values commonly prefix FIPS with ``p`` (for
    example, ``p53033``); ``county2zone.csv`` uses the bare five-digit form.
    """
    text = value.strip()
    if text[:1].casefold() == "p":
        text = text[1:]
    if not text.isdigit() or len(text) > 5:
        raise CountyMembershipError(f"Invalid county FIPS value {value!r}; expected up to five digits.")
    return text.zfill(5)


def load_county_membership(path: str | Path) -> CountyMembership:
    """Read a supported ReEDS county mapping CSV.

    Supports ``county2zone.csv`` (``FIPS``, ``ba``, optionally
    ``county_name``) and ``r_county.csv`` (``r``, ``county``). County keys
    are normalized to five-digit FIPS strings while region and county display
    labels are retained from the source.

    Raises
    ------
    CountyMembershipError
        If headers are unsupported, a county identifier is invalid, an
        assignment is duplicated, or a county maps to multiple regions.
    """
    mapping_path = Path(path)
    with mapping_path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise CountyMembershipError(f"County mapping file {mapping_path} has no header row.")
        columns = {name.strip().casefold(): name for name in reader.fieldnames if name is not None}
        if {"fips", "ba"} <= columns.keys():
            region_column, county_column = columns["ba"], columns["fips"]
            label_column = columns.get("county_name")
        elif {"r", "county"} <= columns.keys():
            region_column, county_column = columns["r"], columns["county"]
            label_column = county_column
        else:
            raise CountyMembershipError(
                f"Unsupported county mapping headers in {mapping_path}; expected FIPS/ba or r/county."
            )

        region_counties: dict[str, list[str]] = defaultdict(list)
        county_regions: dict[str, str] = {}
        county_labels: dict[str, str] = {}
        seen: set[tuple[str, str]] = set()
        for row_number, row in enumerate(reader, start=2):
            region = (row.get(region_column) or "").strip()
            county_value = (row.get(county_column) or "").strip()
            if not region or not county_value:
                raise CountyMembershipError(
                    f"Missing region or county value in {mapping_path} at row {row_number}."
                )
            county = normalize_county_fips(county_value)
            assignment = (region, county)
            if assignment in seen:
                raise CountyMembershipError(
                    f"Duplicate county assignment: FIPS {county} is repeated in region {region!r} "
                    f"at row {row_number} of {mapping_path}."
                )
            seen.add(assignment)
            previous_region = county_regions.get(county)
            if previous_region is not None and previous_region != region:
                raise CountyMembershipError(
                    f"County FIPS {county} is split or ambiguously assigned to regions "
                    f"{previous_region!r} and {region!r} in {mapping_path} (row {row_number})."
                )
            county_regions[county] = region
            region_counties[region].append(county)
            label = (row.get(label_column) or "").strip() if label_column else ""
            county_labels[county] = label or county_value

    if not county_regions:
        raise CountyMembershipError(f"County mapping file {mapping_path} contains no assignments.")

    return CountyMembership(
        region_to_counties={region: tuple(counties) for region, counties in region_counties.items()},
        county_to_region=county_regions,
        county_labels=county_labels,
    )


def align_regions(
    left: CountyMembership,
    right: CountyMembership,
    *,
    require_complete: bool = False,
    county_universe: Iterable[str] | None = None,
    policy: RegionAlignmentPolicy | str = RegionAlignmentPolicy.CROSSWALK,
) -> RegionAlignment:
    """Align two runs through shared county FIPS keys.

    A region may match multiple regions on the other side, which explicitly
    represents aggregation such as county-level regions into balancing areas.
    By default, partial coverage is returned in the result. Set
    ``require_complete=True`` to raise when either run contains counties absent
    from the other membership. ``county_universe`` can be supplied from a
    trusted, complete mapping to validate that both runs cover the expected
    geography. ``policy`` controls whether arbitrary crosswalks, nested
    partitions, or only identical partitions are accepted.

    The result's ``resolution`` is populated only when both memberships have
    complete, equal county coverage. ``LEFT_COARSER`` means each right-side
    region belongs to exactly one left-side region, while at least one left
    region contains multiple right-side regions; ``RIGHT_COARSER`` is the
    inverse. ``CROSSING`` means the partitions overlap without being nested.
    """
    try:
        policy = RegionAlignmentPolicy(policy)
    except ValueError as error:
        supported = ", ".join(item.value for item in RegionAlignmentPolicy)
        raise ValueError(f"Unsupported region alignment policy {policy!r}; choose {supported}.") from error

    left_counties = set(left.county_to_region)
    right_counties = set(right.county_to_region)
    common_counties = left_counties & right_counties
    missing_from_right = left_counties - right_counties
    missing_from_left = right_counties - left_counties

    if county_universe is not None:
        expected_counties = {normalize_county_fips(county) for county in county_universe}
        if not expected_counties:
            raise RegionAlignmentError("The expected county universe cannot be empty.")
        mismatches = []
        for side, counties in (("left", left_counties), ("right", right_counties)):
            missing = expected_counties - counties
            unexpected = counties - expected_counties
            if missing:
                mismatches.append(f"{side} is missing expected counties: {_format_counties(missing)}")
            if unexpected:
                mismatches.append(
                    f"{side} has counties outside the expected universe: {_format_counties(unexpected)}"
                )
        if mismatches:
            raise RegionAlignmentError("County universe validation failed (" + "; ".join(mismatches) + ").")

    if policy is not RegionAlignmentPolicy.CROSSWALK and (missing_from_right or missing_from_left):
        raise RegionAlignmentError(
            f"The {policy.value} policy requires complete county coverage ("
            + "; ".join(_coverage_differences(missing_from_right, missing_from_left))
            + ")."
        )
    if require_complete and (missing_from_right or missing_from_left):
        raise RegionAlignmentError(
            "County coverage is incomplete ("
            + "; ".join(_coverage_differences(missing_from_right, missing_from_left))
            + ")."
        )

    contributors: dict[tuple[str, str], list[str]] = defaultdict(list)
    matched_left: set[str] = set()
    matched_right: set[str] = set()
    for county in sorted(common_counties):
        left_region = left.county_to_region[county]
        right_region = right.county_to_region[county]
        contributors[(left_region, right_region)].append(county)
        matched_left.add(left_region)
        matched_right.add(right_region)

    matches = tuple(
        RegionMatch(left_region, right_region, tuple(counties))
        for (left_region, right_region), counties in sorted(contributors.items())
    )
    resolution = _classify_resolution(left, right, common_counties)
    if policy is RegionAlignmentPolicy.NESTED and resolution is RegionResolution.CROSSING:
        raise RegionAlignmentError(
            "The region partitions cross; the nested policy requires one partition to contain the other."
        )
    if policy is RegionAlignmentPolicy.SAME_PARTITION and resolution is not RegionResolution.SAME_PARTITION:
        observed = resolution.value if resolution is not None else "unresolved"
        raise RegionAlignmentError(
            f"The same_partition policy requires identical county groupings; observed {observed}."
        )

    return RegionAlignment(
        matched_regions=matches,
        unmatched_left_regions=tuple(sorted(set(left.region_to_counties) - matched_left)),
        unmatched_right_regions=tuple(sorted(set(right.region_to_counties) - matched_right)),
        left_coverage=len(common_counties) / len(left_counties) if left_counties else 0.0,
        right_coverage=len(common_counties) / len(right_counties) if right_counties else 0.0,
        resolution=resolution,
    )


def _classify_resolution(
    left: CountyMembership,
    right: CountyMembership,
    common_counties: set[str],
) -> RegionResolution | None:
    if common_counties != set(left.county_to_region) or common_counties != set(right.county_to_region):
        return None

    left_to_right: dict[str, set[str]] = defaultdict(set)
    right_to_left: dict[str, set[str]] = defaultdict(set)
    for county in common_counties:
        left_region = left.county_to_region[county]
        right_region = right.county_to_region[county]
        left_to_right[left_region].add(right_region)
        right_to_left[right_region].add(left_region)

    left_is_nested = all(len(regions) == 1 for regions in left_to_right.values())
    right_is_nested = all(len(regions) == 1 for regions in right_to_left.values())
    if left_is_nested and right_is_nested:
        return RegionResolution.SAME_PARTITION
    if right_is_nested:
        return RegionResolution.LEFT_COARSER
    if left_is_nested:
        return RegionResolution.RIGHT_COARSER
    return RegionResolution.CROSSING


def _coverage_differences(missing_from_right: set[str], missing_from_left: set[str]) -> list[str]:
    details = []
    if missing_from_right:
        details.append(f"missing from right: {_format_counties(missing_from_right)}")
    if missing_from_left:
        details.append(f"missing from left: {_format_counties(missing_from_left)}")
    return details


def _format_counties(counties: set[str]) -> str:
    ordered = sorted(counties)
    preview = ", ".join(ordered[:10])
    if len(ordered) > 10:
        preview += f", ... ({len(ordered) - 10} more)"
    return preview
