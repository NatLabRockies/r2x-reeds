"""Plugin manifest for the r2x-reeds package."""

from __future__ import annotations

from r2x_core import GitVersioningStrategy, PluginManifest, PluginSpec
from r2x_reeds import ReEDSConfig, ReEDSParser
from r2x_reeds.sysmod.break_gens import _break_generators
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

manifest.add(
    PluginSpec.function(
        name="r2x_reeds.add_pcm_defaults",
        entry=add_pcm_defaults,
        description="Augment generators with PCM default attributes.",
    )
)

manifest.add(
    PluginSpec.function(
        name="r2x_reeds.add_emission_cap",
        entry=add_emission_cap,
        description="Add annual CO2 emission cap constraints.",
    )
)

manifest.add(
    PluginSpec.function(
        name="r2x_reeds.add_electrolyzer_load",
        entry=add_electrolizer_load,
        description="Attach electrolyzer load and hydrogen price profiles.",
    )
)

manifest.add(
    PluginSpec.function(
        name="r2x_reeds.add_ccs_credit",
        entry=add_ccs_credit,
        description="Apply CCS credit adjustments to generators.",
    )
)

manifest.add(
    PluginSpec.function(
        name="r2x_reeds.break_gens",
        entry=_break_generators,
        description="Split large generators into average-sized units.",
    )
)

manifest.add(
    PluginSpec.function(
        name="r2x_reeds.add_imports",
        entry=add_imports,
        description="Create Canadian import time series for eligible regions.",
    )
)
__all__ = ["manifest"]
