---
title: Environment and inputs
---

Use Python **3.11–3.13** (`>=3.11,<3.14`). On macOS/Linux, create an empty workspace
and virtual environment with an available supported interpreter:

```bash
mkdir reeds-example
cd reeds-example
python3.12 -m venv .venv
source .venv/bin/activate
```

On Windows, activate the environment with `.venv\Scripts\Activate.ps1` in PowerShell.
Keep the environment active for installation and every Python example. Follow
[installation](/r2x-reeds/getting-started/installation/) next.

A Python project environment and r2x-cli's managed runtime are separate. Install the
plugin in the environment that will execute it. The CLI installation path is on the
installation page; it does not require a project checkout.

The [ReEDS model](https://github.com/ReEDS-Model/ReEDS) produces the source runs.
You need matching input/output files, a solve year and a weather year. Keep a copy:
parser input upgrades can change files. The [fixture tutorial](/r2x-reeds/tutorials/parse-run/)
downloads sample data separately and requires `curl`; the wheel does not
include those fixtures. No target-model license is needed for parsing and inspection.
