"""Validate generated public API pages and the sidebar contract."""

import doctest
import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def generated_api(tmp_path_factory: pytest.TempPathFactory) -> ModuleType:
    spec = importlib.util.spec_from_file_location("reeds_docs_api", ROOT / "docs/generate_api.py")
    assert spec is not None and spec.loader is not None
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    output = tmp_path_factory.mktemp("generated-api")
    generator.PAGES = output / "pages"
    generator.NAVIGATION = output / "sidebar.json"
    generator.FRAGMENTS = output / "fragments.json"
    generator.generate()
    return generator


def test_generated_api_members(generated_api: ModuleType) -> None:
    generator = generated_api
    sidebar = json.loads(generator.NAVIGATION.read_text())
    labels = {entry["label"] for entry in sidebar}
    assert set(generator.public_names()) <= labels
    assert {"BreakGensConfig", "break_generators", "PurchaserLoadConfig", "add_purchaser_load"} <= labels
    for entry in sidebar:
        for member in entry["items"]:
            route, _, fragment = member["link"].partition("#")
            page = generator.PAGES / (route.strip("/").rsplit("/", 1)[-1] + ".md")
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


def test_enum_values_and_access_contracts(generated_api: ModuleType) -> None:
    """Check actual enum inventories and property/classmethod declarations."""
    from r2x_reeds import EmissionType, ReserveDirection, ReserveType

    navigation = json.loads(generated_api.NAVIGATION.read_text())
    fragments = json.loads(generated_api.FRAGMENTS.read_text())
    for enum in (EmissionType, ReserveType, ReserveDirection):
        group = next(item for item in navigation if item["label"] == enum.__name__)
        targets = {item["label"]: item["link"] for item in group["items"]}
        page = generated_api.PAGES / f"{enum.__name__.lower()}.md"
        for name, value in enum.__members__.items():
            assert name in targets
            assert repr(value.value) in page.read_text()
            assert targets[name].endswith("#" + name.lower())
            assert fragments[f"{enum.__module__}.{enum.__name__}.{name}"] == "/r2x-reeds" + targets[name]
    config = (generated_api.PAGES / "reedsconfig.md").read_text()
    parser = (generated_api.PAGES / "reedsparser.md").read_text()
    assert "@property\nprimary_solve_year(" in config
    assert "@property\nprimary_weather_year(" in config
    assert "@classmethod\nfrom_context(" in parser
