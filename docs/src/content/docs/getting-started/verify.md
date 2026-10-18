---
title: Verify installation and first use
---

In the active environment, inspect the installed distribution:

```bash
python -m pip show r2x-reeds
```

Start `python` in that environment and verify the public parser/config imports.
These checks need no ReEDS data and do not change files:

```python doctest
>>> from importlib.metadata import version
>>> from r2x_reeds import ReEDSConfig, ReEDSParser, __version__
>>> assert version("r2x-reeds") == __version__
>>> assert ReEDSParser.__name__ == "ReEDSParser"
>>> config = ReEDSConfig(solve_year=2032, weather_year=2012)
>>> assert config.primary_solve_year == 2032
>>> assert config.primary_weather_year == 2012
```

A successful session raises no assertion errors. This checks model construction,
not that a run contains those years. There is no standalone `r2x-reeds` executable.
Leave Python with `exit()` before running shell commands. If you chose the CLI
installation path, inspect that runtime separately:

```bash
r2x list r2x-reeds
```

Expect `reeds-parser` and eight transforms. Inspect the parser options without
running a pipeline:

```bash
r2x run reeds-parser --help
```

Continue with [parse, modify and reload a ReEDS fixture](/r2x-reeds/tutorials/parse-run/)
for a checked data workflow. Choose optional steps from
[available system modifiers](/r2x-reeds/getting-started/system-modifiers/), then
[prepare a PCM handoff](/r2x-reeds/how-to/pcm-handoff/) for detailed recipes.
