import pytest

pytestmark = [pytest.mark.unit]


# TODO: Re-enable when manifest API is available in r2x_core
@pytest.mark.skip(reason="PluginKind not yet available in r2x_core")
def test_manifest_exports_parser() -> None:
    # from r2x_core import PluginKind
    # from r2x_reeds.plugins import manifest
    #
    # parser = manifest.get_plugin("r2x-reeds.parser")
    #
    # assert parser.entry.endswith("ReEDSParser")
    # assert parser.resources is not None
    # assert parser.io.produces
    pass


@pytest.mark.skip(reason="PluginKind not yet available in r2x_core")
def test_manifest_has_modifiers() -> None:
    # from r2x_core import PluginKind
    # from r2x_reeds.plugins import manifest
    #
    # modifiers = manifest.group_by_kind(PluginKind.MODIFIER)
    # names = {plugin.name for plugin in modifiers}
    #
    # assert "r2x-reeds.add-pcm-defaults" in names
    # assert "r2x-reeds.break-gens" in names
    pass
