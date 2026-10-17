---
title: Contributors
---

## Source checkout

Source installation is for contributors. Normal users should follow
[published installation](/r2x-reeds/getting-started/installation/).

```bash
git clone https://github.com/NatLabRockies/r2x-reeds.git
cd r2x-reeds
```

Install locked project dependencies from the repository root:

```bash
uv sync --locked --all-groups
```

Run the repository's hooks and focused checks:

```bash
uv run prek run --all-files --hook-stage pre-push
uv run pytest -q -m "not slow" --maxfail=1 --disable-warnings
uv run ty check ./src/r2x_reeds/
```

For a docs-only change, run hooks against the changed files so unrelated runtime
files are not formatted. The full pre-push suite remains the final repository gate.
Use the configured commands rather than the older `just type` recipe's `mypy` invocation.

Build the Astro site with `npm ci` and `npm run build` from `docs/`. Preview the
production output to check links and Pagefind search. See
[docs/README.md](https://github.com/NatLabRockies/r2x-reeds/blob/main/docs/README.md).
Keep changelogs canonical, link to actual source revisions and avoid manufacturing
versioned site archives. Update examples when public contracts change.
