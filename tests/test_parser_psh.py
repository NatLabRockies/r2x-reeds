"""Reported PSH energy determines duration before generator splitting."""

import polars as pl
import pytest

from r2x_reeds.parser_utils import _prepare_generator_dataset, resolve_psh_storage_durations


@pytest.fixture
def psh_frames():
    capacity = pl.DataFrame(
        {
            "technology": ["pumped-hydro", "pumped-hydro", "pumped-hydro-flex"],
            "vintage": ["init-1", "init-2", "new1"],
            "region": ["p1", "p1", "p2"],
            "year": [2032, 2032, 2032],
            "capacity": [100.0, 200.0, 300.0],
        }
    )
    reference = capacity.rename({"capacity": "reference_capacity"}).lazy()
    energy = capacity.with_columns(
        (pl.col("capacity") * pl.Series([4.0, 19.7, 73.3])).alias("psh_energy_capacity")
    ).drop("capacity")
    return capacity, energy.lazy(), reference


@pytest.mark.parametrize("psh_position", [0, 1, 2])
def test_psh_duration_overrides_baseline_and_detailed_duration_without_affecting_batteries(
    psh_frames, psh_position
):
    capacity, energy, reference = psh_frames
    resolved = resolve_psh_storage_durations(capacity, energy, reference).unwrap()
    battery = pl.DataFrame(
        {
            "technology": ["battery_4"],
            "vintage": ["new1"],
            "region": ["p1"],
            "year": [2032],
            "capacity": [50.0],
        }
    )
    capacity = pl.concat([capacity, battery])
    baseline = pl.DataFrame(
        {"technology": ["pumped-hydro", "pumped-hydro-flex", "battery_4"], "storage_duration": [12, 12, 4]}
    )
    detailed = capacity.select("technology", "vintage", "region", "year").with_columns(
        pl.lit(99.0).alias("storage_duration")
    )
    for baseline_data in (baseline, baseline.filter(pl.col("technology") == "battery_4")):
        duration_sources = [
            ("storage_duration", baseline_data.lazy()),
            ("storage_duration_out", detailed.lazy()),
        ]
        duration_sources.insert(psh_position, ("psh_storage_duration", resolved))
        result = _prepare_generator_dataset(
            capacity.lazy(),
            {
                "fuel_tech_map": capacity.select("technology")
                .unique()
                .with_columns(pl.lit("storage").alias("fuel_type"))
                .lazy(),
                **dict(duration_sources),
            },
            [],
            {
                "pumped_storage": {"prefixes": ["pumped-hydro"]},
                "storage": {"prefixes": ["battery"]},
            },
        ).unwrap()
        assert result["storage_duration"].to_list() == pytest.approx([4.0, 19.7, 73.3, 4.0])
        assert "psh_storage_duration" not in result.columns
        assert "energy_capacity" not in result.columns


@pytest.mark.parametrize("missing", [None, float("nan")])
def test_psh_override_uses_categories_and_precedes_missing_duration_filter(missing):
    capacity = pl.DataFrame(
        {
            "technology": ["custom-psh", "battery", "missing-battery"],
            "vintage": ["init-1"] * 3,
            "region": ["p1"] * 3,
            "year": [2032] * 3,
            "capacity": [100.0] * 3,
            "storage_duration": [missing, 4.0, missing],
        }
    )
    keys = ["technology", "vintage", "region", "year"]
    result = _prepare_generator_dataset(
        capacity.lazy(),
        {
            "fuel_tech_map": capacity.select("technology")
            .with_columns(pl.lit("storage").alias("fuel_type"))
            .lazy(),
            "storage_duration_out": capacity.select(keys)
            .with_columns(pl.lit(missing, dtype=pl.Float64).alias("storage_duration"))
            .lazy(),
            "psh_storage_duration": capacity.select(keys)
            .with_columns(pl.lit(19.7).alias("psh_storage_duration"))
            .lazy(),
        },
        [],
        {
            "pumped_storage": {"exact": ["custom-psh"]},
            "storage": {"exact": ["custom-psh", "battery", "missing-battery"]},
        },
    ).unwrap()
    assert dict(result.select("technology", "storage_duration").iter_rows()) == {
        "custom-psh": 19.7,
        "battery": 4.0,
    }


@pytest.mark.parametrize("source", ["energy", "reference"])
def test_psh_requires_both_reports(psh_frames, source):
    capacity, energy, reference = psh_frames
    result = resolve_psh_storage_durations(
        capacity, None if source == "energy" else energy, None if source == "reference" else reference
    )
    assert result.is_err()
    assert ("cap_energy_ivrt" if source == "energy" else "cap_ivrt") in str(result.unwrap_err())
    assert "no technology-duration fallback" in str(result.unwrap_err())


@pytest.mark.parametrize("key", ["technology", "vintage", "region", "year"])
def test_psh_requires_exact_report_key_matches(psh_frames, key):
    capacity, energy, reference = psh_frames
    replacement = 2040 if key == "year" else "other"
    result = resolve_psh_storage_durations(capacity, energy.with_columns(pl.lit(replacement).alias(key)), reference)
    assert result.is_err()
    assert "Missing PSH rows in 'cap_energy_ivrt'" in str(result.unwrap_err())


@pytest.mark.parametrize("source", ["energy", "reference"])
def test_psh_rejects_duplicate_report_keys(psh_frames, source):
    capacity, energy, reference = psh_frames
    if source == "energy":
        energy = pl.concat([energy, energy])
    else:
        reference = pl.concat([reference, reference])
    result = resolve_psh_storage_durations(capacity, energy, reference)
    assert result.is_err()
    assert "Duplicate PSH keys" in str(result.unwrap_err())


@pytest.mark.parametrize(
    "source,column", [("energy", "psh_energy_capacity"), ("reference", "reference_capacity")]
)
@pytest.mark.parametrize("value", [None, 0.0, -1.0, float("nan"), float("inf")])
def test_psh_rejects_invalid_report_values(psh_frames, source, column, value):
    capacity, energy, reference = psh_frames
    if source == "energy":
        energy = energy.with_columns(pl.lit(value, dtype=pl.Float64).alias(column))
    else:
        reference = reference.with_columns(pl.lit(value, dtype=pl.Float64).alias(column))
    result = resolve_psh_storage_durations(capacity, energy, reference)
    assert result.is_err()
    assert "Invalid PSH values" in str(result.unwrap_err())


def test_psh_rejects_mismatched_power_basis(psh_frames):
    capacity, energy, reference = psh_frames
    result = resolve_psh_storage_durations(capacity.with_columns(pl.col("capacity") * 0.9), energy, reference)
    assert result.is_err()
    assert "selected power does not match" in str(result.unwrap_err())


@pytest.mark.parametrize("power,mwh", [(1e-300, 1e300), (1e300, 1e-300)])
def test_psh_rejects_invalid_derived_duration(psh_frames, power, mwh):
    capacity, energy, reference = psh_frames
    result = resolve_psh_storage_durations(
        capacity.with_columns(pl.lit(power).alias("capacity")),
        energy.with_columns(pl.lit(mwh).alias("psh_energy_capacity")),
        reference.with_columns(pl.lit(power).alias("reference_capacity")),
    )
    assert result.is_err()
    assert "Invalid derived PSH duration" in str(result.unwrap_err())
