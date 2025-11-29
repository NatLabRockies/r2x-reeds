# Repository Guidelines

## Project Structure & Module Organization
- `src/r2x_reeds/` holds the parser, config classes, plugin manifest, system modifiers (`sysmod/`), and the upgrader helpers; it is the package shipped to PyPI, so keep Python-only code and runtime dependencies here.
- `tests/` mirrors the package layout with `test_*` modules, reusable fixtures in `tests/fixtures`, and sample input data under `tests/data`; add new fixtures alongside related tests when they share setup.
- `docs/source/` contains the Sphinx documentation that drives the public references visible at `https://nrel.github.io/r2x-reeds/`; keep corresponding rst or markdown files next to the topics they describe (installation, configuration, API, parser, models).
- Project-level configuration files such as `pyproject.toml`, `uv.lock`, and `LICENSE.txt` live at the repo root so packaging, linting, and licensing decisions stay centralized for collaborators and automation.

## Build, Test, and Development Commands
- `uv run -- pip install --editable .` installs the package (and dependencies) in editable mode so the plugin can be imported while you iterate on `src/r2x_reeds/*`.
- `uv run pytest` runs all tests under `tests/`, respects `tests/test_*` patterns, and is the baseline check before opening a pull request.
- `uv run ruff check src tests docs/source` enforces the shared lints defined in `pyproject.toml` (PEP 8, naming, etc.) with Ruff’s rule set; rerun after changing any files touched by new code.
- `uv run mypy src` exercises the strict typing configuration and keeps the public API fully annotated; run it whenever you add or refactor exported classes or functions.
- `cd docs && uv run -- make html` (available via the shipped `make.bat` on Windows) rebuilds the Sphinx site and should be run if you update documentation files.

## Coding Style & Naming Conventions
- Use four-space indentation, short statements per line, and keep code within the 110-character Ruff limit; prefer descriptive names over acronyms.
- Follow `ruff` rules from `pyproject.toml`, including `pyupgrade` and `pep8-naming` checks, and leave intentional exemptions (e.g., `tests/**/*.py` can use `assert` directly).
- Capitalize Pydantic models and config dataclasses, prefix helpers with their module when clarity is needed (e.g., `rules_helper` helpers), and keep module-level constants in `UPPER_SNAKE`.

## Testing Guidelines
- Tests live under `tests/`, share fixtures through `tests/fixtures/conftest.py`, and reuse static input via `tests/data/`; mirror any new parser feature with both unit tests (e.g., `test_parser_utils.py`) and integration tests when multiple pieces interact.
- Name all test files and functions with the `test_*` prefix so `pytest` auto-discovers them, and describe the focus in docstrings or string literals when behavior is nuanced.
- Run `uv run pytest tests/test_parser_basic.py` to verify a specific module quickly; append `--maxfail=1` or `-k <expression>` when targeting a subset.

## Commit & Pull Request Guidelines
- The Git history follows Conventional Commit style (`feat:`, `fix:`, `chore:`, `feat(upgrades):`, etc.); keep messages lowercase, include scope when helpful, and reference relevant issue IDs in the body.
- PRs should include a short description of the change, mention the tests executed locally, and link to any related issue or documentation ticket; add screenshots or log snippets only if the change affects docs or reporting collateral.

## Documentation & References
- Keep the docs tree in sync with code changes; add new sections to `docs/source/references/` when you expose new APIs or configuration knobs.
- Point readers to generated docs via the README badges so they know when to re-run `cd docs && make html` before pushing final changes.
