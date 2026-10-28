from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest
from infrasys import System

from r2x_reeds.models.components import ReEDSGenerator, ReEDSRegion
from r2x_reeds.sysmod import ccs_credit

pytestmark = [pytest.mark.integration, pytest.mark.polars]


def _build_system() -> tuple[System, ReEDSRegion]:
    system = System(name="test_ccs_credit")
    region = ReEDSRegion(name="west")
    system.add_component(region)
    return system, region


def _add_generator(
    system: System,
    region: ReEDSRegion,
    name: str,
    technology: str,
    vintage: str = "2020",
    solve_year: int | None = None,
) -> ReEDSGenerator:
    generator = ReEDSGenerator(
        name=name,
        region=region,
        technology=technology,
        capacity=100.0,
        category=technology,
        vintage=vintage,
        solve_year=solve_year,
    )
    system.add_component(generator)
    return generator


def _write_csv(path: Path, data: dict[str, list]) -> str:
    pl.DataFrame(data).write_csv(path)
    return str(path)


def _run_ccs(system: System, **kwargs) -> System:
    result = ccs_credit.add_ccs_credit(system, ccs_credit.CCSCreditConfig(**kwargs))
    assert result.is_ok()
    return result.unwrap()


def test_ccs_credit_scope_direct_match(tmp_path: Path) -> None:
    """Direct technology matches apply incentive times capture rate."""
    system, region = _build_system()
    generator = _add_generator(system, region, "Coal_CCS_1", "coal_ccs")

    co2_path = _write_csv(
        tmp_path / "co2.csv",
        {"tech": ["coal_ccs"], "region": ["west"], "vintage": ["2020"], "incentive": [85.0]},
    )
    capture_path = _write_csv(
        tmp_path / "capture.csv",
        {"tech": ["coal_ccs"], "region": ["west"], "vintage": ["2020"], "capture_rate": [0.9]},
    )
    upgrade_path = _write_csv(
        tmp_path / "upgrade.csv",
        {"from": ["coal_pre"], "to": ["coal_ccs"], "region": ["west"], "vintage": ["2020"]},
    )

    _run_ccs(
        system,
        co2_incentive_fpath=co2_path,
        emission_capture_rate_fpath=capture_path,
        upgrade_link_fpath=upgrade_path,
    )

    assert generator.ext["UoS Charge"] == pytest.approx(-76.5)


def test_ccs_credit_matches_year_specific_upgrade_paths(tmp_path: Path) -> None:
    system, region = _build_system()
    generators = {
        year: _add_generator(
            system,
            region,
            f"Coal_Pre_{year}",
            "coal_pre",
            solve_year=year,
        )
        for year in (2032, 2035)
    }
    co2_path = _write_csv(
        tmp_path / "co2.csv",
        {
            "tech": ["coal_ccs", "coal_ccs"],
            "region": ["west", "west"],
            "vintage": ["2020", "2020"],
            "t": [2032, 2035],
            "incentive": [60.0, 70.0],
        },
    )
    capture_path = _write_csv(
        tmp_path / "capture.csv",
        {
            "tech": ["coal_pre", "coal_pre"],
            "region": ["west", "west"],
            "vintage": ["2020", "2020"],
            "t": [2032, 2035],
            "capture_rate": [0.5, 0.25],
        },
    )
    upgrade_path = _write_csv(
        tmp_path / "upgrade.csv",
        {
            "from": ["coal_pre", "coal_pre"],
            "to": ["coal_ccs", "coal_ccs"],
            "region": ["west", "west"],
            "vintage": ["2020", "2020"],
            "t": [2032, 2035],
        },
    )

    _run_ccs(
        system,
        co2_incentive_fpath=co2_path,
        emission_capture_rate_fpath=capture_path,
        upgrade_link_fpath=upgrade_path,
    )

    assert generators[2032].ext["UoS Charge"] == pytest.approx(-30.0)
    assert generators[2035].ext["UoS Charge"] == pytest.approx(-17.5)


def test_ccs_credit_scope_upgrade_path(tmp_path: Path) -> None:
    """Generators using pre-upgrade techs use upgrade mapping to fetch incentives."""
    system, region = _build_system()
    generator = _add_generator(system, region, "Coal_Pre", "coal_pre")

    co2_path = _write_csv(
        tmp_path / "co2.csv",
        {"tech": ["coal_ccs"], "region": ["west"], "vintage": ["2020"], "incentive": [60.0]},
    )
    capture_path = _write_csv(
        tmp_path / "capture.csv",
        {"tech": ["coal_pre"], "region": ["west"], "vintage": ["2020"], "capture_rate": [0.8]},
    )
    upgrade_path = _write_csv(
        tmp_path / "upgrade.csv",
        {"from": ["coal_pre"], "to": ["coal_ccs"], "region": ["west"], "vintage": ["2020"]},
    )

    _run_ccs(
        system,
        co2_incentive_fpath=co2_path,
        emission_capture_rate_fpath=capture_path,
        upgrade_link_fpath=upgrade_path,
    )

    assert generator.ext["UoS Charge"] == pytest.approx(-48.0)


def test_ccs_credit_scope_missing_production_rate(tmp_path: Path, caplog) -> None:
    """Generators with no capture rate entry are skipped."""
    system, region = _build_system()
    generator = _add_generator(system, region, "Coal_CCS_1", "coal_ccs")

    co2_path = _write_csv(
        tmp_path / "co2.csv",
        {"tech": ["coal_ccs"], "region": ["west"], "vintage": ["2020"], "incentive": [85.0]},
    )
    capture_path = _write_csv(
        tmp_path / "capture.csv",
        {"tech": ["other"], "region": ["west"], "vintage": ["2020"], "capture_rate": [0.9]},
    )
    upgrade_path = _write_csv(
        tmp_path / "upgrade.csv",
        {"from": ["coal_pre"], "to": ["coal_ccs"], "region": ["west"], "vintage": ["2020"]},
    )

    _run_ccs(
        system,
        co2_incentive_fpath=co2_path,
        emission_capture_rate_fpath=capture_path,
        upgrade_link_fpath=upgrade_path,
    )

    assert "does not appear in the production rate file" in caplog.text
    assert "UoS Charge" not in generator.ext


def test_ccs_credit_scope_missing_paths(caplog) -> None:
    """If any file path is missing the plugin exits early."""
    system, _ = _build_system()

    _run_ccs(system)

    assert "Missing required data file paths for ccs_credit" in caplog.text


def test_ccs_credit_scope_no_incentive(caplog, tmp_path: Path) -> None:
    """Generators matching CCS technologies without incentive entries are skipped."""
    system, region = _build_system()
    generator = _add_generator(system, region, "Coal_CCS_1", "coal_ccs")

    co2_path = _write_csv(
        tmp_path / "co2.csv",
        {"tech": ["coal_ccs"], "region": ["other"], "vintage": ["2030"], "incentive": [60.0]},
    )
    capture_path = _write_csv(
        tmp_path / "capture.csv",
        {"tech": ["coal_ccs"], "region": ["west"], "vintage": ["2020"], "capture_rate": [0.8]},
    )
    upgrade_path = _write_csv(
        tmp_path / "upgrade.csv",
        {"from": ["coal_ccs"], "to": ["coal_ccs"], "region": ["other"], "vintage": ["2030"]},
    )

    caplog.set_level("DEBUG", logger="r2x_reeds.sysmod.ccs_credit")
    _run_ccs(
        system,
        co2_incentive_fpath=co2_path,
        emission_capture_rate_fpath=capture_path,
        upgrade_link_fpath=upgrade_path,
    )

    assert "no incentive found" in caplog.text.lower()
    assert "UoS Charge" not in generator.ext


def test_ccs_credit_returns_error_for_malformed_capture_rate(tmp_path: Path) -> None:
    """A malformed capture-rate table is not reported as a successful no-op."""
    system, region = _build_system()
    _add_generator(system, region, "Coal_CCS_1", "coal_ccs")

    co2_path = _write_csv(
        tmp_path / "co2.csv",
        {"tech": ["coal_ccs"], "region": ["west"], "vintage": ["2020"], "incentive": [70.0]},
    )
    capture_path = _write_csv(
        tmp_path / "capture_bad.csv",
        {"tech": ["coal_ccs"], "region": ["west"], "vintage": ["2020"], "wrong_column": [0.9]},
    )
    upgrade_path = _write_csv(
        tmp_path / "upgrade.csv",
        {"from": ["coal_ccs"], "to": ["coal_ccs"], "region": ["west"], "vintage": ["2020"]},
    )

    result = ccs_credit.add_ccs_credit(
        system,
        ccs_credit.CCSCreditConfig(
            co2_incentive_fpath=co2_path,
            emission_capture_rate_fpath=capture_path,
            upgrade_link_fpath=upgrade_path,
        ),
    )

    assert result.is_err()
    assert "capture_rate" in str(result.unwrap_err())


def test_cast_string_columns_handles_empty_frame():
    result = ccs_credit._cast_string_columns(None, ("tech",))
    assert result.is_empty()


def test_add_ccs_credit_missing_configured_file_preserves_error(tmp_path: Path, caplog) -> None:
    system, _ = _build_system()
    missing = tmp_path / "missing.csv"
    caplog.set_level("ERROR", logger="r2x_reeds.sysmod.ccs_credit")

    result = ccs_credit.add_ccs_credit(
        system,
        ccs_credit.CCSCreditConfig(
            co2_incentive_fpath=missing,
            emission_capture_rate_fpath=missing,
            upgrade_link_fpath=missing,
        ),
    )

    assert result.is_err()
    assert "CCS credit plugin failed" in caplog.text
    error = result.unwrap_err()
    while error.__cause__ is not None:
        error = error.__cause__
    assert isinstance(error, FileNotFoundError)


def test_apply_ccs_credit_rejects_ambiguous_incentive_rows():
    system, region = _build_system()
    _add_generator(system, region, "Coal_CCS_1", "coal_ccs")

    co2_incentive = pl.DataFrame(
        {
            "tech": ["coal_ccs", "coal_ccs"],
            "region": ["west", "west"],
            "vintage": ["2020", "2020"],
            "incentive": [60.0, 70.0],
        }
    )
    emission_capture_rate = pl.DataFrame(
        {"tech": ["coal_ccs"], "region": ["west"], "vintage": ["2020"], "capture_rate": [0.5]}
    )
    upgrade_link = pl.DataFrame(
        {"from": ["coal_ccs"], "to": ["coal_ccs"], "region": ["west"], "vintage": ["2020"]}
    )

    with pytest.raises(ValueError, match="Ambiguous CCS incentive rows"):
        ccs_credit._apply_ccs_credit(system, co2_incentive, emission_capture_rate, upgrade_link)
