---
title: ReEDS input upgrades
---

The parser integrates file upgrades with the core plugin lifecycle. Work on a
copy of the run: steps can rename, create or normalize files in the supplied directory.

`ReEDSVersionDetector.read_version(folder_path: Path)` reads `meta.csv` and uses the
`tag` column when present; missing or empty tags use the legacy marker.
Missing `meta.csv` fails version reading.

`ReEDSUpgrader(path).upgrade(*, current_version=None, target_version=None,
strategy=None, upgrader_context=None, upgrade_type=UpgradeType.FILE)` returns
`Result[Path, Exception]`. It sorts registered steps by priority and name, filters by
upgrade type and version eligibility, and stops on failure. Check the result
before parsing or reusing the directory.

The parser's [implementation](https://github.com/NatLabRockies/r2x-reeds/blob/ebb69534188c7b94933c36a534d84a651114e2f9/src/r2x_reeds/parser.py)
controls when upgrade hooks run. Inspect [the upgrader](https://github.com/NatLabRockies/r2x-reeds/blob/ebb69534188c7b94933c36a534d84a651114e2f9/src/r2x_reeds/upgrader/data_upgrader.py)
and [registered steps](https://github.com/NatLabRockies/r2x-reeds/blob/ebb69534188c7b94933c36a534d84a651114e2f9/src/r2x_reeds/upgrader/upgrade_steps.py)
for the exact input changes. Successful upgrades do not replace validation of
required datasets, solve years or weather years.
