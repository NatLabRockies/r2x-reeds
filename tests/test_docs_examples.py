"""Execute the console examples against an isolated copy of the public fixture."""

from __future__ import annotations

import doctest
import re
import shutil
from contextlib import chdir
from pathlib import Path
from typing import Any

import pytest

DOCS = Path(__file__).resolve().parents[1] / "docs/src/content/docs"
TUTORIAL = DOCS / "tutorials/parse-run.md"
FENCES = re.compile(r"^```python doctest\n(.*?)^```", re.MULTILINE | re.DOTALL)
PAGES = sorted(
    path
    for path in DOCS.rglob("*.md")
    if "/reference/api/" not in str(path) and FENCES.search(path.read_text())
)


def run_console(path: Path, namespace: dict[str, Any]) -> dict[str, Any]:
    """Run a page in one console namespace so its sequential steps share state."""
    blocks = FENCES.findall(path.read_text())
    assert blocks, f"No executable console blocks in {path}"
    assert all(">>> " in block and "doctest: +SKIP" not in block for block in blocks)
    test = doctest.DocTestParser().get_doctest("\n\n".join(blocks), namespace, path.name, str(path), 0)
    runner = doctest.DocTestRunner()
    result = runner.run(test, clear_globs=False)
    assert result.attempted > 0, f"No examples discovered in {path}"
    assert result.failed == 0, f"{result.failed}/{result.attempted} console checks failed in {path}"
    return test.globs


@pytest.fixture(scope="session")
def tutorial_console(
    reeds_run_path: Path, fixed_om_inputs: Path, tmp_path_factory: pytest.TempPathFactory
) -> tuple[Path, dict[str, Any]]:
    """Run the actual tutorial once, including parse, profile checks, split and reload."""
    workspace = tmp_path_factory.mktemp("docs-console")
    run = workspace / "tutorial-inputs/test_Pacific"
    shutil.copytree(reeds_run_path, run)
    shutil.copyfile(fixed_om_inputs / "unitspec_upgrades.csv", run / "inputs_case/unitspec_upgrades.csv")
    with chdir(workspace):
        namespace = run_console(TUTORIAL, {})
    return workspace, namespace


@pytest.mark.parametrize("page", PAGES, ids=lambda path: str(path.relative_to(DOCS)))
def test_documented_console(
    page: Path, tutorial_console: tuple[Path, dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Check each page against its documented tutorial prerequisites."""
    from r2x_core import System
    from r2x_reeds.sysmod.pcm_defaults import PCMDefaultsConfig, add_pcm_defaults

    workspace, tutorial = tutorial_console
    monkeypatch.chdir(workspace)
    if page == TUTORIAL:
        assert tutorial["restored"] is not None
        return
    namespace = dict(tutorial)
    system = System.from_json("outputs/pacific-system.json")
    namespace.update(system=system, sys=system)
    run_console(page, namespace)
    if page.name == "pcm-handoff.md":
        result = add_pcm_defaults(
            system,
            PCMDefaultsConfig(
                pcm_defaults_dict={"gas-cc": {"startup_cost": 50.0}}, pcm_defaults_override=True
            ),
        )
        assert result.is_ok(), result.unwrap_err()
        exec(Path("inspect_pcm.py").read_text(), {"sys": system})


def test_console_fences_are_discoverable() -> None:
    """Prevent prompt-bearing examples from silently falling outside collection."""
    assert len(PAGES) >= 8
    for path in DOCS.rglob("*.md"):
        if "/reference/api/" in str(path):
            continue
        text = path.read_text()
        assert "```python\n" not in text, f"Mark executable Python as python doctest: {path}"
        assert all(">>> " in block for block in FENCES.findall(text)), path


def test_parser_docstring(
    tutorial_console: tuple[Path, dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keep the public parser docstring's lifecycle example executable too."""
    from r2x_reeds import ReEDSParser

    workspace, _ = tutorial_console
    monkeypatch.chdir(workspace)
    assert ReEDSParser.__doc__ is not None
    test = doctest.DocTestParser().get_doctest(
        ReEDSParser.__doc__, {}, "ReEDSParser", "src/r2x_reeds/parser.py", 0
    )
    result = doctest.DocTestRunner().run(test)
    assert result.attempted >= 8
    assert result.failed == 0


def test_tutorial_pins_the_current_fixture_archive() -> None:
    """The published ZIP must be the same tracked archive used by console tests."""
    import subprocess

    revision = "86db7099fd409cff64f96e51b09a32a010b13cf5"
    archive = "tests/data/test_Pacific.zip"
    root = DOCS.parents[3]
    expected = "c610f6045df78ec21d61733dcae23ef4c01155be"
    actual = subprocess.check_output(["git", "hash-object", archive], cwd=root, text=True).strip()
    assert actual == expected
    assert f"/{revision}/{archive}" in TUTORIAL.read_text()
