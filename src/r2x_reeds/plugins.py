"""Plugin exports for r2x-reeds package.

This module exports the main parser plugin and callable transforms.
Discovery for r2x-core relies on entry points defined in pyproject.toml.
"""

from __future__ import annotations

from r2x_reeds import ReEDSConfig, ReEDSParser
from r2x_reeds.sysmod.break_gens import break_generators
from r2x_reeds.sysmod.ccs_credit import add_ccs_credit
from r2x_reeds.sysmod.electrolyzer import add_electrolizer_load
from r2x_reeds.sysmod.emission_cap import add_emission_cap
from r2x_reeds.sysmod.imports import add_imports
from r2x_reeds.sysmod.pcm_defaults import add_pcm_defaults
from r2x_reeds.upgrader.data_upgrader import ReEDSUpgrader, ReEDSVersionDetector

# Main parser plugin
parser = ReEDSParser
config = ReEDSConfig

# System modifier functions (signature: system, config -> Result[System, str])
system_modifiers = {
    "add-pcm-defaults": add_pcm_defaults,
    "add-emission-cap": add_emission_cap,
    "add-electrolyzer-load": add_electrolizer_load,
    "add-ccs-credit": add_ccs_credit,
    "break-gens": break_generators,
    "add-imports": add_imports,
}

__all__ = [
    "ReEDSConfig",
    "ReEDSParser",
    "ReEDSUpgrader",
    "ReEDSVersionDetector",
    "config",
    "parser",
    "system_modifiers",
]
