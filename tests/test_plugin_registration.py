from r2x_core import PluginKind
from r2x_reeds.plugins import manifest


def test_manifest_exports_parser() -> None:
    parser = manifest.get_plugin("r2x_reeds.parser")

    assert parser.entry.endswith("ReEDSParser")
    assert parser.resources is not None
    assert parser.io.produces


def test_manifest_has_modifiers() -> None:
    modifiers = manifest.group_by_kind(PluginKind.MODIFIER)
    names = {plugin.name for plugin in modifiers}

    assert "r2x_reeds.add_pcm_defaults" in names
    assert "r2x_reeds.break_gens" in names
