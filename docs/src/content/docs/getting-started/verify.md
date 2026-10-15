---
title: Verify installation
---

In the active environment, confirm the installed distribution and public parser import:

```bash
python -m pip show r2x-reeds
python -c "from importlib.metadata import version; from r2x_reeds import ReEDSParser, ReEDSConfig; print(version('r2x-reeds')); print(ReEDSParser.__name__, ReEDSConfig.__name__)"
```

Expect a package version followed by `ReEDSParser ReEDSConfig`. There is no standalone
`r2x-reeds` executable. If you chose the CLI installation path, verify that runtime instead:

```bash
r2x list r2x-reeds
r2x run reeds-parser --help
```

The inventory should include `reeds-parser` and eight transforms. Continue with
[parse, modify and reload a ReEDS fixture](/r2x-reeds/tutorials/parse-run/) for the first
complete data workflow, then [prepare a PCM handoff](/r2x-reeds/how-to/pcm-handoff/).
