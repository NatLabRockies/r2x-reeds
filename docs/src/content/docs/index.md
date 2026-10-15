---
title: r2x-reeds
---

Read a ReEDS run into an R2X system, then apply optional system modifiers before
translation to another model. The package provides a parser and transforms;
target translation and export are supplied by separate packages.

The [ReEDS model](https://github.com/ReEDS-Model/ReEDS) produces the capacity-expansion runs consumed here. `r2x-reeds` parses those results and applies optional system modifiers; it does not solve the ReEDS model.

Start with [parse a ReEDS run](/r2x-reeds/tutorials/parse-run/). You need an existing
ReEDS run with matching input and output data; this package does not run ReEDS.

| Task                    | Guide                                                                   |
| ----------------------- | ----------------------------------------------------------------------- |
| Learn the parser        | [Tutorial](/r2x-reeds/tutorials/parse-run/)                             |
| Use the CLI             | [Parser pipeline](/r2x-reeds/how-to/reeds-to-x-cli/)                    |
| Add purchaser demand    | [Purchaser load](/r2x-reeds/how-to/purchaser-load/)                     |
| Look up fields and APIs | [Reference](/r2x-reeds/reference/)                                      |
| Understand data flow    | [Explanation](/r2x-reeds/explanation/architecture/)                     |
| Diagnose a failure      | [Troubleshooting](/r2x-reeds/troubleshooting/)                          |
| Review changes          | [Changelog](/r2x-reeds/changelog/) and [versions](/r2x-reeds/versions/) |

See [PyPI](https://pypi.org/project/r2x-reeds/) for current package releases and
[contributors](/r2x-reeds/contributors/) for development checks.
