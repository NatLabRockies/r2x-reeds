"""Plugin manifest for the r2x-reeds package."""

from __future__ import annotations

from r2x_core import GitVersioningStrategy, PluginManifest, PluginSpec

from r2x_reeds.config import ReEDSConfig
from r2x_reeds.parser import ReEDSParser
from r2x_reeds.sysmod.break_gens import break_gens
from r2x_reeds.sysmod.ccs_credit import add_ccs_credit
from r2x_reeds.sysmod.electrolyzer import add_electrolizer_load
from r2x_reeds.sysmod.emission_cap import add_emission_cap
from r2x_reeds.sysmod.imports import add_imports
from r2x_reeds.sysmod.pcm_defaults import add_pcm_defaults
from r2x_reeds.upgrader.data_upgrader import ReEDSUpgrader, ReEDSVersionDetector

manifest = PluginManifest(package="r2x-reeds")

manifest.add(
    PluginSpec.parser(
        name="r2x_reeds.parser",
        entry=ReEDSParser,
        config=ReEDSConfig,
        description="Parse ReEDS run directories into an infrasys.System.",
    )
)

manifest.add(
    PluginSpec.upgrader(
        name="r2x_reeds.upgrader",
        entry=ReEDSUpgrader,
        version_strategy=GitVersioningStrategy,
        version_reader=ReEDSVersionDetector,
        steps=ReEDSUpgrader.steps,
        description="Apply file-level upgrades to ReEDS run folders.",
    )
)

for plugin_name, func, description in [
    (
        "r2x_reeds.add_pcm_defaults",
        add_pcm_defaults,
        "Augment generators with PCM default attributes.",
    ),
    (
        "r2x_reeds.add_emission_cap",
        add_emission_cap,
        "Add annual CO2 emission cap constraints.",
    ),
    (
        "r2x_reeds.add_electrolyzer_load",
        add_electrolizer_load,
        "Attach electrolyzer load and hydrogen price profiles.",
    ),
    (
        "r2x_reeds.add_ccs_credit",
        add_ccs_credit,
        "Apply CCS credit adjustments to generators.",
    ),
    (
        "r2x_reeds.break_gens",
        break_gens,
        "Split large generators into average-sized units.",
    ),
    (
        "r2x_reeds.add_imports",
        add_imports,
        "Create Canadian import time series for eligible regions.",
    ),
]:
    manifest.add(
        PluginSpec.function(
            name=plugin_name,
            entry=func,
            description=description,
        )
    )

__all__ = ["manifest"]
