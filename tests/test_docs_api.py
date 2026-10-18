"""Validate generated public API pages and the sidebar contract."""

import doctest
import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_generated_api_members() -> None:
    spec = importlib.util.spec_from_file_location("reeds_docs_api", ROOT / "docs/generate_api.py")
    assert spec is not None and spec.loader is not None
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    generator.generate()
    sidebar = json.loads(generator.NAVIGATION.read_text())
    labels = {entry["label"] for entry in sidebar}
    assert set(generator.public_names()) <= labels
    assert {"BreakGensConfig", "break_generators", "PurchaserLoadConfig", "add_purchaser_load"} <= labels
    for entry in sidebar:
        for member in entry["items"]:
            route, _, fragment = member["link"].partition("#")
            page = ROOT / "docs/src/content/docs" / (route.strip("/") + ".md")
            assert page.is_file(), member
            text = page.read_text()
            assert "[Source](https://github.com/NatLabRockies/r2x-reeds/blob/" in text
            if not fragment:
                snippet = re.search(r"```python doctest\n(.*?)```", text, re.DOTALL)
                assert snippet is not None
                test = doctest.DocTestParser().get_doctest(snippet.group(1), {}, entry["label"], str(page), 0)
                result = doctest.DocTestRunner().run(test)
                assert result.attempted == 2 and result.failed == 0
            if fragment:
                assert f"### {member['label']}" in text, member


def test_enum_values_and_access_contracts() -> None:
    """Check actual enum inventories and property/classmethod declarations."""
    from r2x_reeds import EmissionType, ReserveDirection, ReserveType

    navigation = json.loads((ROOT / "docs/src/generated/api-sidebar.json").read_text())
    fragments = json.loads((ROOT / "docs/public/api-fragments.json").read_text())
    for enum in (EmissionType, ReserveType, ReserveDirection):
        group = next(item for item in navigation if item["label"] == enum.__name__)
        targets = {item["label"]: item["link"] for item in group["items"]}
        page = ROOT / "docs/src/content/docs/reference/api" / f"{enum.__name__.lower()}.md"
        for name, value in enum.__members__.items():
            assert name in targets
            assert repr(value.value) in page.read_text()
            assert targets[name].endswith("#" + name.lower())
            assert fragments[f"{enum.__module__}.{enum.__name__}.{name}"] == "/r2x-reeds" + targets[name]
    config = (ROOT / "docs/src/content/docs/reference/api/reedsconfig.md").read_text()
    parser = (ROOT / "docs/src/content/docs/reference/api/reedsparser.md").read_text()
    assert "@property\nprimary_solve_year(" in config
    assert "@property\nprimary_weather_year(" in config
    assert "@classmethod\nfrom_context(" in parser
