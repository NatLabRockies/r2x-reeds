"""Public FOM precedence and temporal-boundary regressions."""

import shutil
from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory

import h5py
import numpy as np
import polars as pl
import pytest

from r2x_core import PluginContext, System
from r2x_core.exceptions import PluginError
from r2x_reeds import ReEDSConfig, ReEDSParser
from r2x_reeds.models.components import ReEDSGenerator, ReEDSVariableGenerator
from tests.fixtures.data_fixtures import csv_file_mapping, current_data_store, write_unitspec_upgrades_h5

pytestmark = [pytest.mark.integration, pytest.mark.polars]


@pytest.fixture
def fom_run_path(reeds_run_path: Path, tmp_path: Path) -> Iterator[Path]:
    """Release each case's copied inputs rather than retaining every large fixture."""
    with TemporaryDirectory(prefix="fom-", dir=tmp_path) as directory:
        run_path = Path(directory) / "run"
        shutil.copytree(reeds_run_path, run_path)
        yield run_path


def build_fom_system(run_path: Path, *, config: ReEDSConfig) -> System:
    """Run the real parser against one independently prepared source directory."""
    store = current_data_store(run_path)
    context = PluginContext(config=config, store=store)
    result = ReEDSParser.from_context(context).run()
    assert result.system is not None
    return result.system


@pytest.mark.parametrize("source_state", ["missing", "empty", "wrong-year"])
def test_parser_validation_requires_cost_fom_for_the_solve_year(
    fom_run_path: Path, source_state: str
) -> None:
    path = fom_run_path / "inputs_case" / "plantcharout.csv"
    path.write_text("*i,t,variable,value\nGas-CC,2032,fom,20081\n")
    if source_state == "missing":
        path.unlink()
    elif source_state == "empty":
        path.write_text("*i,t,variable,value\n")
    else:
        path.write_text("*i,t,variable,value\nGas-CC,2029,fom,20081\n")
    config = ReEDSConfig(solve_year=2032, weather_year=2012)
    parser = ReEDSParser.from_context(PluginContext(config=config, store=current_data_store(fom_run_path)))

    with pytest.raises(PluginError) as captured:
        parser.run()

    if source_state == "missing":
        assert isinstance(captured.value.__cause__, FileNotFoundError)
        assert "plantcharout.csv" in str(captured.value.__cause__)
    else:
        from r2x_core.exceptions import ReaderError

        assert isinstance(captured.value.__cause__, ReaderError)
        assert isinstance(captured.value.__cause__.__cause__, ValueError)
        assert "cost_fom" in str(captured.value.__cause__)


def test_cost_fom_must_cover_every_requested_solve_year(fom_run_path: Path) -> None:
    inputs = fom_run_path / "inputs_case"
    (inputs / "plantcharout.csv").write_text("*i,t,variable,value\nGas-CC,2032,fom,20081\n")
    load_path = inputs / "load.h5"
    with h5py.File(load_path, "r") as source:
        columns = source["columns"][:]
    with h5py.File(load_path, "w") as destination:
        destination.create_dataset("columns", data=columns)
        destination.create_dataset("data", data=np.zeros((2, len(columns)), dtype=np.float32))
        destination.create_dataset("index_0", data=np.asarray([2032, 2035], dtype=np.int64))
        destination.create_dataset(
            "index_1",
            data=np.asarray([b"2012-01-01T00:00:00", b"2012-01-01T00:00:00"], dtype="S19"),
        )
        destination.create_dataset("index_names", data=np.asarray([b"year", b"datetime"], dtype="S8"))
    config = ReEDSConfig(solve_year=[2032, 2035], weather_year=2012)
    parser = ReEDSParser.from_context(PluginContext(config=config, store=current_data_store(fom_run_path)))

    with pytest.raises(PluginError, match="cost_fom"):
        parser.run()


def test_enabled_water_upgrade_requires_its_physical_file(
    fom_run_path: Path, reeds_config: ReEDSConfig
) -> None:
    write_upgrade_inputs(
        fom_run_path,
        initial_rate=45000.0,
        hydro_rate=0.0,
        retrofit_enabled=False,
    )
    switches_path = fom_run_path / "inputs_case" / "switches.csv"
    switches = switches_path.read_text()
    assert "GSw_WaterMain,0" in switches
    switches_path.write_text(switches.replace("GSw_WaterMain,0", "GSw_WaterMain,1"))
    (fom_run_path / "inputs_case" / "upgradelink_water.csv").unlink(missing_ok=True)
    parser = ReEDSParser.from_context(
        PluginContext(config=reeds_config, store=current_data_store(fom_run_path))
    )

    with pytest.raises(PluginError) as captured:
        parser.run()

    assert isinstance(captured.value.__cause__, FileNotFoundError)
    assert "upgradelink_water.csv" in str(captured.value.__cause__)


def get_initial_upgrade(system: System, /) -> ReEDSGenerator:
    """Find the controlled upgrade without assuming its concrete generator subtype."""
    matches = [
        generator
        for generator in system.get_components(ReEDSGenerator)
        if generator.name == "coalolduns_coal-ccs_mod_init-1_p1_2032"
    ]
    assert len(matches) == 1
    return matches[0]


def write_upgrade_inputs(
    run_path: Path,
    *,
    initial_rate: float | None,
    hydro_rate: float,
    retrofit_enabled: bool,
) -> None:
    """Prepare one controlled initial-vintage upgrade using real ReEDS files."""
    inputs = run_path / "inputs_case"
    costs = [
        "*i,t,variable,value\n",
        "Gas-CC,2028,fom,20081\n",
        "Gas-CC,2032,fom,20081\n",
        "coal-ccs_mod,2032,fom,46000\n",
    ]
    if initial_rate is not None:
        costs.append(f"coal-ccs_mod,2028,fom,{initial_rate}\n")
    (inputs / "plantcharout.csv").write_text("".join(costs))

    hydro_path = inputs / "hyd_fom.csv"
    hydro = pl.read_csv(hydro_path).filter(pl.col("i").str.to_lowercase() != "coal-ccs_mod")
    target_hydro = {column: "coal-ccs_mod" if column == "i" else hydro_rate for column in hydro.columns}
    pl.concat([hydro, pl.DataFrame([target_hydro])], how="diagonal_relaxed").write_csv(hydro_path)

    (inputs / "upgrade_link.csv").write_text(
        "*TO,FROM,DELTA\nCoalOldUns_Coal-CCS_mod,CoalOldUns,coal-ccs_mod\n"
    )
    switches_path = inputs / "switches.csv"
    switches = switches_path.read_text()
    assert "GSw_UpgradeFOM_Nems,1" in switches
    switches_path.write_text(
        switches.replace("GSw_UpgradeFOM_Nems,1", f"GSw_UpgradeFOM_Nems,{int(retrofit_enabled)}")
    )
    with (run_path / "outputs" / "cap_ivrt.csv").open("a") as output:
        output.write("CoalOldUns_Coal-CCS_mod,init-1,p1,2032,100\n")
    if retrofit_enabled:
        write_unitspec_upgrades_h5(inputs / "inputs.h5", ["coalolduns_coal-ccs_mod"])


def test_distpv_fom_is_capacity_weighted_after_source_precedence(
    fom_run_path: Path,
    reeds_config: ReEDSConfig,
) -> None:
    outputs = fom_run_path / "outputs"
    (outputs / "cap_ivrt.csv").write_text("i,v,r,t,Value\ndistpv,new1,p1,2032,10\ndistpv,new2,p1,2032,30\n")
    history_path = fom_run_path / "inputs_case" / "hintage_data.csv"
    history_path.write_text(
        "TECH,bin,r,yr,cap,wFOM,wCCS_Retro_FOM\ndistpv,new1,p1,2032,10,100,0\ndistpv,new2,p1,2032,30,200,0\n"
    )

    system = build_fom_system(fom_run_path, config=reeds_config)

    generators = [
        unit for unit in system.get_components(ReEDSVariableGenerator) if unit.technology == "distpv"
    ]
    assert [(unit.name, unit.capacity, unit.fom_cost) for unit in generators] == [
        ("distpv_p1_2032", 40.0, 175.0)
    ]


@pytest.mark.parametrize(
    ("base_rate", "regional_rate", "psh_rate", "expected_rate"),
    [
        (41000.0, 0.0, 13030.0, 41000.0),
        (41000.0, 42000.0, 13030.0, 42000.0),
        (0.0, 0.0, 0.0, 0.0),
    ],
    ids=["hydro-zero-does-not-override", "regional-hydro-overrides", "known-zero-rates"],
)
def test_hydro_and_storage_distinguish_zero_from_unknown(
    fom_run_path: Path,
    reeds_config: ReEDSConfig,
    base_rate: float,
    regional_rate: float,
    psh_rate: float,
    expected_rate: float,
) -> None:
    """A hydro zero is a non-override, while base and storage zeros are known costs."""
    run_path = fom_run_path
    inputs = run_path / "inputs_case"
    (inputs / "plantcharout.csv").write_text(
        f"*i,t,variable,value\nhyded,2032,fom,{base_rate}\nGas-CC,2032,fom,20081\n"
    )
    hydro_path = inputs / "hyd_fom.csv"
    hydro = pl.read_csv(hydro_path)
    hydro.with_columns(
        pl.lit(regional_rate).alias(column) for column in hydro.columns if column != "i"
    ).write_csv(hydro_path)
    (inputs / "scalars.csv").write_text(f"cost_fom_psh,{psh_rate},2004$/MW-year\n")

    system = build_fom_system(run_path, config=reeds_config)

    hydro_generators = [
        generator for generator in system.get_components(ReEDSGenerator) if generator.technology == "hyded"
    ]
    storage_generators = [
        generator
        for generator in system.get_components(ReEDSGenerator)
        if generator.technology == "pumped-hydro"
    ]
    assert hydro_generators
    assert storage_generators
    assert all(generator.fom_cost == expected_rate for generator in hydro_generators)
    assert all(generator.fom_cost == psh_rate for generator in storage_generators)


@pytest.mark.parametrize(
    ("initial_rate", "hydro_rate", "expected_rate"),
    [(None, 42000.0, None), (0.0, 0.0, 0.0), (10000.0, 42000.0, 52000.0)],
    ids=["unknown-base-stays-unknown", "known-zero-total", "known-hydro-adder"],
)
def test_initial_upgrade_preserves_unknown_cost_when_adding_hydro(
    fom_run_path: Path,
    reeds_config: ReEDSConfig,
    initial_rate: float | None,
    hydro_rate: float,
    expected_rate: float | None,
) -> None:
    """The hydro adder cannot turn an unknown initial target cost into a known rate."""
    run_path = fom_run_path
    write_upgrade_inputs(
        run_path,
        initial_rate=initial_rate,
        hydro_rate=hydro_rate,
        retrofit_enabled=False,
    )

    if expected_rate is None:
        with pytest.raises(PluginError, match="fixed O&M"):
            build_fom_system(run_path, config=reeds_config)
        return

    system = build_fom_system(run_path, config=reeds_config)
    generator = get_initial_upgrade(system)
    assert generator.fom_cost == expected_rate


@pytest.mark.parametrize(
    ("prior_rate", "current_rate", "eligibility_capacity", "expected_rate"),
    [
        (66.0, 0.0, 100.0, 66000.0),
        (66.0, 0.0, 0.0, 45000.0),
        (66.0, 55.0, 0.0, 55000.0),
        (0.0, 0.0, 100.0, 45000.0),
    ],
    ids=[
        "strict-prior-before-eligibility-year",
        "ineligible-carry",
        "current-does-not-need-carry-eligibility",
        "future-and-zero-history-ignored",
    ],
)
def test_retrofit_uses_current_or_eligible_strictly_prior_nonzero_rate(
    fom_run_path: Path,
    reeds_config: ReEDSConfig,
    prior_rate: float,
    current_rate: float,
    eligibility_capacity: float,
    expected_rate: float,
) -> None:
    """Carry-forward excludes current/future years and uses eligibility only for carry."""
    run_path = fom_run_path
    write_upgrade_inputs(run_path, initial_rate=45000.0, hydro_rate=0.0, retrofit_enabled=True)
    history_path = run_path / "inputs_case" / "hintage_data.csv"
    history = pl.read_csv(history_path)
    controlled_group = (
        (pl.col("TECH").str.to_lowercase() == "coalolduns")
        & (pl.col("bin") == "init-1")
        & (pl.col("r") == "p1")
    ).fill_null(False)
    history = history.filter(~controlled_group)
    selected_history = pl.DataFrame(
        {
            "TECH": ["CoalOldUns"] * 5,
            "bin": ["init-1"] * 5,
            "r": ["p1"] * 5,
            "yr": [2027, 2028, 2031, 2032, 2034],
            "cap": [100.0, eligibility_capacity, 100.0, 100.0, 100.0],
            "wFOM": [50000.0] * 5,
            "wCCS_Retro_FOM": [prior_rate, 0.0, 0.0, current_rate, 99.0],
        }
    )
    pl.concat([history, selected_history], how="diagonal_relaxed").write_csv(history_path)

    system = build_fom_system(run_path, config=reeds_config)

    generator = get_initial_upgrade(system)
    assert generator.fom_cost == expected_rate


def test_active_upgrades_fail_when_the_global_upgrade_switch_is_disabled(
    fom_run_path: Path,
    reeds_config: ReEDSConfig,
) -> None:
    """Disabling upgrades cannot silently turn active upgrades into ordinary units."""
    run_path = fom_run_path
    write_upgrade_inputs(run_path, initial_rate=45000.0, hydro_rate=0.0, retrofit_enabled=True)
    switches_path = run_path / "inputs_case" / "switches.csv"
    switches = switches_path.read_text()
    assert "GSw_Upgrades,1" in switches
    switches_path.write_text(switches.replace("GSw_Upgrades,1", "GSw_Upgrades,0"))

    with pytest.raises(PluginError, match="GSw_Upgrades"):
        build_fom_system(run_path, config=reeds_config)


def test_standard_upgrade_link_precedes_conflicting_enabled_water_link(
    fom_run_path: Path, reeds_config: ReEDSConfig
) -> None:
    """An enabled water link cannot override the declared standard upgrade identity."""
    write_upgrade_inputs(fom_run_path, initial_rate=45000.0, hydro_rate=0.0, retrofit_enabled=False)
    inputs = fom_run_path / "inputs_case"
    switches_path = inputs / "switches.csv"
    switches = switches_path.read_text()
    assert "GSw_WaterMain,0" in switches
    switches_path.write_text(switches.replace("GSw_WaterMain,0", "GSw_WaterMain,1"))
    (inputs / "upgradelink_water.csv").write_text("*TO,FROM,DELTA\nCoalOldUns_Coal-CCS_mod,Gas-CC,Gas-CC\n")

    system = build_fom_system(fom_run_path, config=reeds_config)

    assert get_initial_upgrade(system).fom_cost == 45000.0


def test_initial_upgrade_costs_use_the_configured_characteristic_source_and_year(
    fom_run_path: Path, reeds_config: ReEDSConfig
) -> None:
    """A separate configured source supplies characteristic-year costs, not solve-year costs."""
    write_upgrade_inputs(fom_run_path, initial_rate=45000.0, hydro_rate=0.0, retrofit_enabled=False)
    (fom_run_path / "inputs_case" / "alternate_upgrade_costs.csv").write_text(
        "*i,t,variable,value\ncoal-ccs_mod,2028,fom,62000\ncoal-ccs_mod,2032,fom,99999\n"
    )
    mapping = csv_file_mapping()
    initial_costs = next(item for item in mapping if item["name"] == "fom_upgrade_characteristics")
    initial_costs["relative_fpath"] = "inputs_case/alternate_upgrade_costs.csv"
    store = current_data_store(fom_run_path, data_files=mapping)
    context = PluginContext(config=reeds_config, store=store)
    result = ReEDSParser.from_context(context).run()
    assert result.system is not None
    system = result.system

    assert get_initial_upgrade(system).fom_cost == 62000.0
