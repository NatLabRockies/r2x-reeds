---
title: Compose parsing and modifiers in Python
---

Use Python when a workflow needs explicit component inspection or conditional
modifiers. Install packages into the same project environment that runs your script.
Start with the complete [parser tutorial](/r2x-reeds/tutorials/parse-run/) and keep
its `system` variable.

## Split selected generators

Append this to the tutorial script:

```python
from r2x_reeds import ReEDSGenerator
from r2x_reeds.sysmod.break_gens import BreakGensConfig, break_generators

before = len(list(system.get_components(ReEDSGenerator)))
result = break_generators(
    system,
    BreakGensConfig(drop_capacity_threshold=5, include_technologies=["coal-new"]),
)
if result.is_err():
    raise RuntimeError(result.unwrap_err())
system = result.unwrap()
print("Generators before:", before)
print("Generators after:", len(list(system.get_components(ReEDSGenerator))))
```

Run the script with `uv run python parse_reeds.py`. Counts can remain unchanged if
no eligible generators match; compare names and capacities for the selected technology.
Multiple `include_*` filters use OR matching. See the [transform reference](/r2x-reeds/reference/transforms/)
and its source links before selecting additional inputs.

Check every transform result before passing the system to the next step.
The package's functions modify systems; do not assume the pre-transform object is
an independent snapshot. Target translation and export use separate plugins;
follow [R2X's Python API](https://natlabrockies.github.io/R2X/reference/python-api/)
for their current contracts instead of relying on private local runner scripts.
