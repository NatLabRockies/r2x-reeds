set dotenv-load := false

default:
    @just --list

# Install dev dependencies.
sync:
    uv sync --all-groups --upgrade

# Update uv.lock.
lock:
    uv lock

# Install git hooks.
hooks-install:
    uv run prek install

# Format code.
format *ARGS:
    uv run ruff format {{ARGS}}

# Lint code.
lint *ARGS:
    uv run ruff check --config=pyproject.toml {{ARGS}}

# Type check.
type:
    uv run mypy src/

# Run tests (all tests with coverage).
test *ARGS:
    uv run pytest -q --cov-report=term-missing:skip-covered {{ARGS}}

# Run fast unit tests only (~5s).
test-fast *ARGS:
    uv run pytest -m unit -q {{ARGS}}

# Run unit + quick integration tests (~15s).
test-quick *ARGS:
    uv run pytest -m "not slow" -q --cov-report=term-missing:skip-covered {{ARGS}}

# Run full test suite with HTML coverage report (CI-style).
test-ci *ARGS:
    uv run pytest -q --cov-report=term-missing:skip-covered --cov-report=html --cov-report=json {{ARGS}}

# Build documentation.
docs:
    uv run sphinx-build -M html docs/source docs/build

# Run prek hooks (format, lint, type check, file hygiene).
hooks:
    uv run prek run --all-files

# Comprehensive verification: hooks + tests with strict coverage.
verify: hooks
    uv run pytest --tb=short --cov --cov-report=term-missing:skip-covered
