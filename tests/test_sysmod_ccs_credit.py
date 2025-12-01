from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest
from infrasys import System

from r2x_reeds.models.components import ReEDSGenerator, ReEDSRegion
from r2x_reeds.sysmod import ccs_credit


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
) -> ReEDSGenerator:
    generator = ReEDSGenerator(
        name=name,
        region=region,
        technology=technology,
        capacity=100.0,
        category=technology,
        vintage=vintage,
    )
    system.add_component(generator)
    return generator


def _write_csv(path: Path, data: dict[str, list]) -> str:
    pl.DataFrame(data).write_csv(path)
    return str(path)


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

    ccs_credit.add_ccs_credit(
        system,
        co2_incentive_fpath=co2_path,
        emission_capture_rate_fpath=capture_path,
        upgrade_link_fpath=upgrade_path,
    )

    assert generator.ext["UoS Charge"] == pytest.approx(-76.5)


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

    ccs_credit.add_ccs_credit(
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

    ccs_credit.add_ccs_credit(
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

    ccs_credit.add_ccs_credit(
        system, co2_incentive_fpath=None, emission_capture_rate_fpath=None, upgrade_link_fpath=None
    )

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
    ccs_credit.add_ccs_credit(
        system,
        co2_incentive_fpath=co2_path,
        emission_capture_rate_fpath=capture_path,
        upgrade_link_fpath=upgrade_path,
    )

    assert "no incentive found" in caplog.text.lower()
    assert "UoS Charge" not in generator.ext


def test_ccs_credit_scope_caught_exception(caplog, tmp_path: Path) -> None:
    """Exceptions during incentive calculation are logged and skipped."""
    system, _ = _build_system()

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

    ccs_credit.add_ccs_credit(
        system,
        co2_incentive_fpath=co2_path,
        emission_capture_rate_fpath=capture_path,
        upgrade_link_fpath=upgrade_path,
    )


def test_cast_string_columns_handles_empty_frame():
    result = ccs_credit._cast_string_columns(None, ("tech",))
    assert result.is_empty()


def test_add_ccs_credit_logs_load_failure(monkeypatch, caplog):
    system, _ = _build_system()

    def fail_load(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(ccs_credit.DataStore, "load_file", staticmethod(fail_load))
    caplog.set_level("ERROR", logger="r2x_reeds.sysmod.ccs_credit")

    ccs_credit.add_ccs_credit(
        system,
        co2_incentive_fpath="co2",
        emission_capture_rate_fpath="capture",
        upgrade_link_fpath="upgrade",
    )

    assert "CCS credit plugin failed" in caplog.text


def test_apply_ccs_credit_logs_warning_on_incentive_item_error(caplog):
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

    caplog.set_level("WARNING", logger="r2x_reeds.sysmod.ccs_credit")

    ccs_credit._apply_ccs_credit(system, co2_incentive, emission_capture_rate, upgrade_link)

    assert "Failed to apply CCS credit" in caplog.text
