"""R2X plugin entry point for ReEDS package."""

from r2x_core.package import Package


def register_plugin() -> Package:
    """Return the ReEDS plugin package for R2X framework discovery."""

    from r2x_core import GitVersioningStrategy
    from r2x_core.plugin import BasePlugin, IOType, ParserPlugin, UpgraderPlugin
    from r2x_reeds.config import ReEDSConfig
    from r2x_reeds.parser import ReEDSParser
    from r2x_reeds.sysmod.break_gens import break_gens
    from r2x_reeds.sysmod.ccs_credit import add_ccs_credit
    from r2x_reeds.sysmod.electrolyzer import add_electrolizer_load
    from r2x_reeds.sysmod.emission_cap import add_emission_cap
    from r2x_reeds.sysmod.pcm_defaults import add_pcm_defaults
    from r2x_reeds.upgrader.data_upgrader import ReEDSUpgrader, ReEDSVersionDetector

    return Package(
        name="r2x-reeds",
        plugins=[
            ParserPlugin(
                name="reeds-parser",
                obj=ReEDSParser,
                call_method="build_system",
                config=ReEDSConfig,
                io_type=IOType.STDOUT,
            ),
            UpgraderPlugin(
                name="reeds-upgrader",
                obj=ReEDSUpgrader,
                call_method="upgrade",
                version_strategy=GitVersioningStrategy,
                version_reader=ReEDSVersionDetector,
                upgrade_steps=ReEDSUpgrader.steps,
            ),
            BasePlugin(
                name="add-pcm-defaults",
                obj=add_pcm_defaults,
                io_type=IOType.BOTH,
            ),
            BasePlugin(
                name="add-emission-cap",
                obj=add_emission_cap,
                io_type=IOType.BOTH,
            ),
            BasePlugin(
                name="add-electrolyzer-load",
                obj=add_electrolizer_load,
                io_type=IOType.BOTH,
            ),
            BasePlugin(
                name="add-ccs-credit",
                obj=add_ccs_credit,
                io_type=IOType.BOTH,
            ),
            BasePlugin(
                name="break-gens",
                obj=break_gens,
                io_type=IOType.BOTH,
            ),
        ],
    )
