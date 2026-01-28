"""Tests for plugin exports."""

import pytest

pytestmark = [pytest.mark.integration]


def test_plugins_exports() -> None:
    """Verify plugin exports are available."""
    from r2x_reeds.plugins import (
        ReEDSConfig,
        ReEDSParser,
        ReEDSUpgrader,
        ReEDSVersionDetector,
        config,
        parser,
        system_modifiers,
    )

    assert parser is ReEDSParser
    assert config is ReEDSConfig
    assert isinstance(system_modifiers, dict)
    assert "add-pcm-defaults" in system_modifiers
    assert "add-emission-cap" in system_modifiers
    assert "add-electrolyzer-load" in system_modifiers
    assert "add-ccs-credit" in system_modifiers
    assert "break-gens" in system_modifiers
    assert "add-imports" in system_modifiers
    assert ReEDSUpgrader is not None
    assert ReEDSVersionDetector is not None
