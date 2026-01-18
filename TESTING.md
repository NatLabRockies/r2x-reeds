# Testing Guide

This document describes the testing setup and best practices for r2x-reeds.

## Quick Start

```bash
# Run all tests with coverage
just test

# Run only unit tests (fast, ~5s)
just test-fast

# Run unit + quick integration tests (~15s)
just test-quick

# Run full suite with HTML coverage report (CI-style)
just test-ci
```

## Test Organization

Tests are organized into two categories using pytest markers:

### Unit Tests (`@pytest.mark.unit`)
- **Fast**: Run in ~5 seconds
- **No external dependencies**: No file I/O, no real data files
- **Isolated**: Test individual functions and classes
- **Files**: `test_parser_utils.py`, `test_models_*.py`, `test_getters.py`, `test_config.py`, etc.
- **Count**: ~278 tests

Run with:
```bash
uv run pytest -m unit
just test-fast
```

### Integration Tests (`@pytest.mark.integration`)
- **Slower**: Run in ~30-60 seconds
- **Real dependencies**: Use actual data files, DataStore, parser instances
- **System-level**: Test parser, upgrader, system modifiers
- **Files**: `test_parser_integration.py`, `test_upgrader.py`, `test_sysmod_*.py`, etc.
- **Count**: ~221 tests

Run with:
```bash
uv run pytest -m integration
```

### Slow Tests (`@pytest.mark.slow`)
- **Very slow**: Individual tests that take >1 second
- **Currently**: `test_sysmod_break_gens.py::test_break_generator_with_large_dataset`
- **Exclude from quick runs**: Use `-m "not slow"`

Run with:
```bash
uv run pytest -m slow
```

## Test Execution Profiles

The `justfile` provides convenient test profiles:

| Command | Purpose | Time | Coverage |
|---------|---------|------|----------|
| `just test` | Full suite with coverage | ~60s | Yes |
| `just test-fast` | Unit tests only | ~5s | No |
| `just test-quick` | Unit + fast integration | ~15s | Yes |
| `just test-ci` | CI-style (HTML + JSON reports) | ~60s | Yes |

## Fixture Organization

All test fixtures are centralized in `tests/fixtures/`:

### `data_fixtures.py`
Session-scoped fixtures for shared test data:
- `test_data_path`: Path to test data directory
- `reeds_run_path`: Unpacked ReEDS test data (test_Pacific)
- `reeds_run_upgrader`: Unpacked upgrader test data (test_Upgrader)
- `reeds_config`: ReEDS configuration instance
- `data_store`: DataStore from test data
- `parser`: ReEDSParser instance

**Backward compatibility aliases** (for existing tests):
- `example_reeds_config` → `reeds_config`
- `example_data_store` → `data_store`
- `example_parser` → `parser`

### `component_fixtures.py`
Function-scoped fixtures for creating test components:
- `sample_region`: ReEDSRegion instance
- `thermal_generator`: ReEDSThermalGenerator instance
- `renewable_generator`: ReEDSVariableGenerator instance
- `storage_generator`: ReEDSStorage instance
- `hydro_generator`: ReEDSHydroGenerator instance
- `consuming_technology`: ReEDSConsumingTechnology instance
- `h2_storage`: ReEDSH2Storage instance
- `h2_pipeline`: ReEDSH2Pipeline instance
- `emission`: ReEDSEmission instance

### `conftest.py` (root)
- `caplog`: Loguru integration for capturing logs
- `empty_file`: Temporary empty CSV file
- `example_system`: Built System instance (session-scoped, expensive)

## Coverage Requirements

- **Minimum coverage**: 90% (enforced by `pyproject.toml`)
- **Excluded from coverage**:
  - `__repr__` methods
  - `raise AssertionError` statements
  - `raise NotImplementedError` statements
  - `if __name__ == "__main__":`
  - `if TYPE_CHECKING:` blocks
  - `@abstractmethod` decorated methods

## Best Practices

### Writing Unit Tests
1. **No fixtures from `data_fixtures.py`** - Use lightweight fixtures instead
2. **No file I/O** - Mock or use `tmp_path` for temporary files
3. **Fast execution** - Should complete in <100ms
4. **Clear names** - `test_<function>_<scenario>_<expected_result>`

Example:
```python
import pytest

pytestmark = [pytest.mark.unit]

def test_tech_matches_category_with_prefixes() -> None:
    """Test that tech matching handles prefix patterns."""
    from r2x_reeds import parser_utils
    
    categories = {"wind": {"prefixes": ["wnd"], "exact": []}}
    assert parser_utils.tech_matches_category("wnd-abc", "wind", categories)
```

### Writing Integration Tests
1. **Use fixtures from `data_fixtures.py`** - Reuse shared test data
2. **Test system-level behavior** - Parser, upgrader, modifiers
3. **Accept slower execution** - Integration tests are expected to be slower
4. **Document dependencies** - Explain what data/fixtures are needed

Example:
```python
import pytest

pytestmark = [pytest.mark.integration]

def test_parser_builds_system(example_system) -> None:
    """Test that parser successfully builds a system."""
    assert example_system is not None
    assert len(list(example_system.get_components())) > 0
```

### Marking Slow Tests
If a test takes >1 second, add the `@pytest.mark.slow` decorator:

```python
@pytest.mark.slow
def test_expensive_operation() -> None:
    """This test takes a long time."""
    # ... slow test code ...
```

## Continuous Integration

The CI workflow (`.github/workflows/ci.yaml`) runs:
1. **Pre-commit checks** (lint, format, type check)
2. **Tests** on 8 matrix combinations (2 OS × 4 Python versions)
3. **Coverage upload** to Codecov
4. **Package smoke test** (build and import)

The CI uses `uv run pytest --cov --cov-report=xml` for efficient coverage reporting.

## Troubleshooting

### Tests fail with "Test data archive not found"
- Ensure `tests/data/test_Pacific.zip` and `tests/data/test_Upgrader.zip` exist
- Check that the zip files are not corrupted

### Fixture scope issues
- Session-scoped fixtures are shared across all tests in a session
- Function-scoped fixtures are created fresh for each test
- Use function-scoped fixtures for tests that modify state

### Coverage not meeting 90% threshold
- Run `just test` to see coverage report
- Check `htmlcov/index.html` for detailed coverage breakdown
- Add tests for uncovered lines or mark with `# pragma: no cover`

## Performance Tips

1. **Use `just test-fast`** for quick feedback during development
2. **Run `just test-quick`** before committing to catch integration issues
3. **Use `just test`** only when you need full coverage report
4. **Mark slow tests** with `@pytest.mark.slow` to exclude from quick runs
5. **Reuse fixtures** - Don't create new DataStore/parser instances in tests

## References

- [pytest documentation](https://docs.pytest.org/)
- [pytest markers](https://docs.pytest.org/en/stable/how-to/mark.html)
- [pytest fixtures](https://docs.pytest.org/en/stable/how-to/fixtures.html)
- [Coverage.py](https://coverage.readthedocs.io/)
