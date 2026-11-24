"""Reported PSH energy determines duration before generator splitting."""

import shutil

import h5py
import numpy as np
import polars as pl
import pytest

from r2x_core import DataStore, PluginContext
from r2x_reeds import ReEDSConfig, ReEDSParser
from r2x_reeds.models import ReEDSStorage
from r2x_reeds.parser_utils import _prepare_generator_dataset, resolve_psh_storage_durations
from r2x_reeds.sysmod.break_gens import BreakGensConfig, break_generators


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
def test_psh_requires_reports_even_with_a_technology_default(psh_frames, source):
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
    energy = energy.with_columns(pl.lit(replacement).alias(key))
    result = resolve_psh_storage_durations(capacity, energy, reference)
    assert result.is_err()
    assert "Missing PSH rows in 'cap_energy_ivrt'" in str(result.unwrap_err())
    assert "init-1" in str(result.unwrap_err())
    assert "p1" in str(result.unwrap_err())


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


def test_psh_rejects_a_mismatched_selected_power_basis(psh_frames):
    capacity, energy, reference = psh_frames
    capacity = capacity.with_columns(pl.col("capacity") * 0.9)
    result = resolve_psh_storage_durations(capacity, energy, reference)
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


@pytest.fixture
def psh_parser(reeds_run_path, tmp_path):
    run_path = tmp_path / "run"
    shutil.copytree(reeds_run_path, run_path)

    def build(**kwargs):
        kwargs.setdefault("use_psh_energy_capacity_duration", True)
        config = ReEDSConfig(solve_year=2032, weather_year=2012, **kwargs)
        store = DataStore.from_plugin_config(config, path=run_path)
        context = PluginContext(config=config, store=store)
        parser = ReEDSParser.from_context(context)
        assert parser._ensure_config_assets().is_ok()
        assert parser._prepare_default_metadata().is_ok()
        return parser, context

    return run_path, build


@pytest.mark.parametrize("energy_report_exists", [False, True])
def test_disabled_psh_duration_preserves_original_workflow(psh_parser, energy_report_exists):
    run_path, build = psh_parser
    energy_path = run_path / "outputs" / "cap_energy_ivrt.csv"
    if energy_report_exists:
        energy = pl.read_csv(energy_path)
        energy.with_columns((pl.col("Value") * 2).alias("Value")).write_csv(energy_path)
    else:
        energy_path.unlink()
    parser, _ = build(use_psh_energy_capacity_duration=False)
    result = parser._prepare_generator_datasets()
    assert result.is_ok(), result
    prepared = parser._non_variable_generator_df
    assert prepared is not None
    psh = prepared.filter(pl.col("technology").str.starts_with("pumped-hydro"))
    assert psh.height > 0
    assert psh["storage_duration"].to_list() == [12.0] * psh.height
    assert "psh_storage_duration" not in prepared.columns


def test_disabled_psh_duration_does_not_read_reports(psh_parser, monkeypatch):
    _, build = psh_parser
    parser, _ = build(use_psh_energy_capacity_duration=False)

    def unexpected_read(name):
        pytest.fail(f"Disabled PSH feature read dataset: {name}")

    monkeypatch.setattr(parser, "read_data_file", unexpected_read)
    capacity = pl.LazyFrame({"technology": ["pumped-hydro"], "capacity": [100.0]})
    assert parser._prepare_psh_storage_durations(capacity).unwrap() is None


@pytest.mark.parametrize("use_degraded_capacity", [False, True])
@pytest.mark.parametrize("hdf", [False, True], ids=["csv", "hdf"])
def test_psh_report_reaches_storage_objects_and_split_units(psh_parser, use_degraded_capacity, hdf):
    run_path, build = psh_parser
    outputs = run_path / "outputs"
    power = pl.read_csv(outputs / "cap_ivrt.csv")
    if use_degraded_capacity:
        power.write_csv(outputs / "cap_deg_ivrt.csv")
    energy = pl.read_csv(outputs / "cap_energy_ivrt.csv").join(
        power.rename({"Value": "power"}), on=["i", "v", "r", "t"]
    )
    energy = energy.with_columns((pl.col("power") * 19.7).alias("Value")).drop("power")
    if hdf:
        with h5py.File(outputs / "outputs.h5", "w") as bundle:
            group = bundle.create_group("cap_energy_ivrt")
            group.create_dataset("columns", data=np.array(energy.columns, dtype="S"))
            for name in energy.columns:
                values = energy[name].to_numpy()
                if energy[name].dtype == pl.String:
                    values = np.array(energy[name].to_list(), dtype="S")
                group.create_dataset(name, data=values)
    else:
        energy.write_csv(outputs / "cap_energy_ivrt.csv")
    parser, context = build(use_degraded_capacity=use_degraded_capacity)
    try:
        result = parser.run(ctx=context)
        assert result.system is not None
        system = result.system
        psh = [
            gen for gen in system.get_components(ReEDSStorage) if gen.technology.startswith("pumped-hydro")
        ]
        assert psh
        assert all(gen.storage_duration == pytest.approx(19.7) for gen in psh)
        assert all(gen.energy_capacity is None for gen in psh)
        original_power = sum(gen.capacity for gen in psh)
        original_energy = sum(gen.capacity * gen.storage_duration for gen in psh)
        break_generators(
            system,
            BreakGensConfig(
                reference_units={"pumped-hydro": {"capacity_MW": 50.0}},
                break_category="technology",
                drop_capacity_threshold=0.0,
            ),
        ).unwrap()
        split = [
            gen for gen in system.get_components(ReEDSStorage) if gen.technology.startswith("pumped-hydro")
        ]
        assert len(split) > len(psh)
        assert all(gen.storage_duration == pytest.approx(19.7) for gen in split)
        assert all(gen.energy_capacity is None for gen in split)
        assert sum(gen.capacity for gen in split) == pytest.approx(original_power)
        assert sum(gen.capacity * gen.storage_duration for gen in split) == pytest.approx(original_energy)
    finally:
        parser._close_outputs_h5()


@pytest.mark.parametrize("dataset", ["cap_energy_ivrt", "cap_ivrt"])
def test_psh_missing_report_fails_before_generator_preparation(psh_parser, dataset):
    run_path, build = psh_parser
    outputs = run_path / "outputs"
    shutil.copyfile(outputs / "cap_ivrt.csv", outputs / "cap_deg_ivrt.csv")
    (outputs / f"{dataset}.csv").unlink()
    parser, _ = build(use_degraded_capacity=True)
    result = parser._prepare_generator_datasets()
    assert result.is_err()
    assert f"'{dataset}'" in result.unwrap_err()
    assert parser._non_variable_generator_df is None


def test_psh_degraded_capacity_must_match_the_independent_reference(psh_parser):
    run_path, build = psh_parser
    outputs = run_path / "outputs"
    pl.read_csv(outputs / "cap_ivrt.csv").with_columns(
        pl.when(pl.col("i").str.starts_with("pumped-hydro"))
        .then(pl.col("Value") * 0.9)
        .otherwise(pl.col("Value"))
        .alias("Value")
    ).write_csv(outputs / "cap_deg_ivrt.csv")
    parser, _ = build(use_degraded_capacity=True)
    result = parser._prepare_generator_datasets()
    assert result.is_err()
    assert "selected power does not match" in result.unwrap_err()


@pytest.mark.parametrize(
    "technology,config",
    [
        ("gas-cc", {}),
        ("pumped-hydro", {"excluded_techs": ["pumped-hydro"]}),
        ("pumped-hydro", {"drop_gen_capacity_threshold": 200.0}),
    ],
)
def test_unneeded_psh_reports_are_not_read(psh_parser, monkeypatch, technology, config):
    _, build = psh_parser
    parser, _ = build(**config)
    capacity = pl.LazyFrame({"technology": [technology], "capacity": [100.0]})

    def unexpected_read(name):
        pytest.fail(f"Unneeded PSH dataset read: {name}")

    monkeypatch.setattr(parser, "read_data_file", unexpected_read)
    assert parser._prepare_psh_storage_durations(capacity).unwrap() is None
