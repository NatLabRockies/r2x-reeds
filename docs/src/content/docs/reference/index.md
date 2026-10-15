---
title: Reference
---

Use [Python API](/r2x-reeds/reference/python-api/) for imports and lifecycle calls,
[configuration](/r2x-reeds/reference/configuration/) for parser settings and assets,
[transforms](/r2x-reeds/reference/transforms/) for optional modifiers, and
[upgrader](/r2x-reeds/reference/upgrader/) for input-file upgrade behavior.

The parser entry point is `reeds-parser` under `r2x_plugin`. Transform entry points
are registered separately under `r2x.transforms`. In Python, import the functions
and their configuration models from the corresponding `r2x_reeds.sysmod` module.
