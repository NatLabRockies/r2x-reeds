# Changelog

## [0.9.0](https://github.com/NatLabRockies/r2x-reeds/compare/v0.8.0...v0.9.0) (2026-09-15)


### 🚀 Features

* add flag to enable can-imports and update file handling logic ([#98](https://github.com/NatLabRockies/r2x-reeds/issues/98)) ([2f05bef](https://github.com/NatLabRockies/r2x-reeds/commit/2f05bef0a196c86fb98d19b0158e57d5866705ef))
* implement flag to use degraded capacity on reeds target ([#102](https://github.com/NatLabRockies/r2x-reeds/issues/102)) ([1d42fc1](https://github.com/NatLabRockies/r2x-reeds/commit/1d42fc1ae424d6c6fc32ce835d3c886c0ba08927))


### 📦 Build

* **deps-dev:** bump prek from 0.4.14 to 0.5.2 ([#104](https://github.com/NatLabRockies/r2x-reeds/issues/104)) ([17b84de](https://github.com/NatLabRockies/r2x-reeds/commit/17b84de9199599df15980d4c256da3ea77d834f3))
* **deps-dev:** bump ruff from 0.16.4 to 0.16.6 ([#103](https://github.com/NatLabRockies/r2x-reeds/issues/103)) ([26c1084](https://github.com/NatLabRockies/r2x-reeds/commit/26c1084422d180aa952e9d4858e699c9c0835b6b))

## [0.8.0](https://github.com/NatLabRockies/r2x-reeds/compare/v0.7.0...v0.8.0) (2026-08-21)


### 🚀 Features

* get startcost correctly from original reeds run ([#97](https://github.com/NatLabRockies/r2x-reeds/issues/97)) ([a24fe29](https://github.com/NatLabRockies/r2x-reeds/commit/a24fe2960de1d0caeae354488bcf8b2fc38b525a))
* represent reV supply-curve sites as ReEDS components ([#82](https://github.com/NatLabRockies/r2x-reeds/issues/82)) ([f032456](https://github.com/NatLabRockies/r2x-reeds/commit/f032456ed0b2047b958caf25d1eb40c11b806853))


### 🐛 Bug Fixes

* avoid duplicate solve year in load profiles ([#99](https://github.com/NatLabRockies/r2x-reeds/issues/99)) ([826a1ec](https://github.com/NatLabRockies/r2x-reeds/commit/826a1ec519b85c04572dbf2ec33705fcea1812fd))

## [0.7.0](https://github.com/NatLabRockies/r2x-reeds/compare/v0.6.0...v0.7.0) (2026-08-13)


### 🚀 Features

* attach missing hurdle rate to line dataframe ([#94](https://github.com/NatLabRockies/r2x-reeds/issues/94)) ([5c830e9](https://github.com/NatLabRockies/r2x-reeds/commit/5c830e9c262a50f47a60015277d048bba710e476))


### 🐛 Bug Fixes

* h2_cc and h2_ct mapping ([#91](https://github.com/NatLabRockies/r2x-reeds/issues/91)) ([6c9d4aa](https://github.com/NatLabRockies/r2x-reeds/commit/6c9d4aabd9bd69586fc9c1529c6144ef88f073fc))
* Model ReEDS smr and smr_ccs technologies as purchaser demand ([#90](https://github.com/NatLabRockies/r2x-reeds/issues/90)) ([7ddbbef](https://github.com/NatLabRockies/r2x-reeds/commit/7ddbbefc127a9c66ac9964448707594956e1307a))
* Represent ReEDS hydro operating modes and profiles ([#93](https://github.com/NatLabRockies/r2x-reeds/issues/93)) ([4a3d578](https://github.com/NatLabRockies/r2x-reeds/commit/4a3d57865d1370d45a6f96130364ed0c06b2ecb9))


### 📦 Build

* **deps:** bump actions/checkout from 6.0.2 to 7.0.0 ([#79](https://github.com/NatLabRockies/r2x-reeds/issues/79)) ([f78e33f](https://github.com/NatLabRockies/r2x-reeds/commit/f78e33fc0708829fc837cbfab3476f87651d5421))
* **deps:** bump actions/checkout from 7.0.0 to 7.0.1 ([#86](https://github.com/NatLabRockies/r2x-reeds/issues/86)) ([2cb3807](https://github.com/NatLabRockies/r2x-reeds/commit/2cb38074cf2f88e207be9c4b6b15c49caa742932))
* **deps:** bump actions/labeler from 6.1.0 to 7.0.0 ([#87](https://github.com/NatLabRockies/r2x-reeds/issues/87)) ([a12110e](https://github.com/NatLabRockies/r2x-reeds/commit/a12110eb4f3f8268824a72d8b570e3ff924bd057))
* **deps:** bump actions/setup-python from 6.2.0 to 6.3.0 ([#80](https://github.com/NatLabRockies/r2x-reeds/issues/80)) ([303bacf](https://github.com/NatLabRockies/r2x-reeds/commit/303bacf483b3b04ccc96325abc7a3e2be33f9cec))
* **deps:** bump actions/setup-python from 6.3.0 to 7.0.0 ([#88](https://github.com/NatLabRockies/r2x-reeds/issues/88)) ([0b97163](https://github.com/NatLabRockies/r2x-reeds/commit/0b971632e0535df6b9da50d02709b32e305273c2))
* **deps:** bump codecov/codecov-action from 6.0.1 to 7.0.0 ([#78](https://github.com/NatLabRockies/r2x-reeds/issues/78)) ([f00011a](https://github.com/NatLabRockies/r2x-reeds/commit/f00011aaa25c7a6fea03afabdb7243b7c7212f5f))
* **deps:** bump googleapis/release-please-action from 4.4.0 to 5.0.0 ([#77](https://github.com/NatLabRockies/r2x-reeds/issues/77)) ([8c3d6c8](https://github.com/NatLabRockies/r2x-reeds/commit/8c3d6c8965274709aa1c4e92977398874129d262))
* **deps:** bump pypa/gh-action-pypi-publish from 1.14.0 to 1.14.2 ([#92](https://github.com/NatLabRockies/r2x-reeds/issues/92)) ([91685c7](https://github.com/NatLabRockies/r2x-reeds/commit/91685c77fd33cd3b85c969c382af0fd8a96dfa11))

## [0.6.0](https://github.com/NatLabRockies/r2x-reeds/compare/v0.5.0...v0.6.0) (2026-06-24)


### 🚀 Features

* add compatibility with old missing hmap all hours reeds runs ([#72](https://github.com/NatLabRockies/r2x-reeds/issues/72)) ([a0f4176](https://github.com/NatLabRockies/r2x-reeds/commit/a0f4176089c007276a0899231322f3b76c388d83))
* add new system modifier for Purchaser loads (Electrolyzers and DataCenter loads) ([#68](https://github.com/NatLabRockies/r2x-reeds/issues/68)) ([a85589b](https://github.com/NatLabRockies/r2x-reeds/commit/a85589b35d72a28418e2406c72ee699688a33640))


### 🐛 Bug Fixes

* make deprecated agglevels optional ([#76](https://github.com/NatLabRockies/r2x-reeds/issues/76)) ([218cfaf](https://github.com/NatLabRockies/r2x-reeds/commit/218cfaf6781446aa7263e439f5ff7a5a6364243b))
* Update ramp_limits to ramp_rate ([#70](https://github.com/NatLabRockies/r2x-reeds/issues/70)) ([da782c7](https://github.com/NatLabRockies/r2x-reeds/commit/da782c71bd6896da08d09c9d9ad460e89f6274ac))


### 📦 Build

* **deps:** bump actions/labeler from 6.0.1 to 6.1.0 ([#69](https://github.com/NatLabRockies/r2x-reeds/issues/69)) ([117f066](https://github.com/NatLabRockies/r2x-reeds/commit/117f066ca845d68b7d1ea03ba588b7819f637dac))
* **deps:** bump actions/upload-artifact from 7.0.0 to 7.0.1 ([#67](https://github.com/NatLabRockies/r2x-reeds/issues/67)) ([5560f01](https://github.com/NatLabRockies/r2x-reeds/commit/5560f01355c9d2e592c822b154d5dd929a6e22d4))
* **deps:** bump codecov/codecov-action from 5.5.3 to 6.0.1 ([#74](https://github.com/NatLabRockies/r2x-reeds/issues/74)) ([401d9a2](https://github.com/NatLabRockies/r2x-reeds/commit/401d9a2ec277ccfd13f007019b3a6743cf57bb23))
* **deps:** bump googleapis/release-please-action ([#62](https://github.com/NatLabRockies/r2x-reeds/issues/62)) ([68365a4](https://github.com/NatLabRockies/r2x-reeds/commit/68365a4da9428f166ee04ae372b8243b2e9ff190))
* **deps:** bump peaceiris/actions-gh-pages from 4.0.0 to 4.1.0 ([#73](https://github.com/NatLabRockies/r2x-reeds/issues/73)) ([bd28120](https://github.com/NatLabRockies/r2x-reeds/commit/bd28120fd7078f8a686624ba80116947187b3997))
* **deps:** bump pypa/gh-action-pypi-publish from 1.13.0 to 1.14.0 ([#66](https://github.com/NatLabRockies/r2x-reeds/issues/66)) ([bc443e2](https://github.com/NatLabRockies/r2x-reeds/commit/bc443e249af95d8ff730c58fc6c734ec1c1a808b))

## [0.5.0](https://github.com/NatLabRockies/r2x-reeds/compare/v0.4.0...v0.5.0) (2026-04-06)


### 🚀 Features

* add optimal load siting capability to be included on load parser as an Upgrader feature ([#57](https://github.com/NatLabRockies/r2x-reeds/issues/57)) ([284d05a](https://github.com/NatLabRockies/r2x-reeds/commit/284d05ae85c6c2b7674a2cb80e3d2c11cb0b9920))


### 🐛 Bug Fixes

* allow double format for pcm default values ([#54](https://github.com/NatLabRockies/r2x-reeds/issues/54)) ([d7b65ce](https://github.com/NatLabRockies/r2x-reeds/commit/d7b65ce53672d769e3121fcfbbc7b7634f0707ff))
* pcm defaults and split generators ([#58](https://github.com/NatLabRockies/r2x-reeds/issues/58)) ([45df350](https://github.com/NatLabRockies/r2x-reeds/commit/45df350d5897af9380c6d5600df81af39d243170))


### 📦 Build

* **deps:** bump codecov/codecov-action from 5 to 6 ([#59](https://github.com/NatLabRockies/r2x-reeds/issues/59)) ([b83b85b](https://github.com/NatLabRockies/r2x-reeds/commit/b83b85b924b6c7c8515da99b438d64ea1b5240fb))

## [0.4.0](https://github.com/NatLabRockies/r2x-reeds/compare/v0.3.6...v0.4.0) (2026-03-18)


### 🚀 Features

* migrate transmission capacity init to trancap_init_energy.csv ([#53](https://github.com/NatLabRockies/r2x-reeds/issues/53)) ([17d2251](https://github.com/NatLabRockies/r2x-reeds/commit/17d22515efbf45752931065c6ef539abbb9bc7ac))


### 🐛 Bug Fixes

* add missing properties for consuming technology ([#52](https://github.com/NatLabRockies/r2x-reeds/issues/52)) ([a285ec3](https://github.com/NatLabRockies/r2x-reeds/commit/a285ec377212ae5542d68ead9ced65c20fd39fab))
* include line losses to parsing workflow ([#50](https://github.com/NatLabRockies/r2x-reeds/issues/50)) ([bff3f6e](https://github.com/NatLabRockies/r2x-reeds/commit/bff3f6e8fcdf262a6b2f4a9299a5020ffb0ad5ea))

## [0.3.6](https://github.com/NatLabRockies/r2x-reeds/compare/v0.3.5...v0.3.6) (2026-03-03)


### 🐛 Bug Fixes

* filter duplicated line names and update capacity field handling (approach to be changed) ([#46](https://github.com/NatLabRockies/r2x-reeds/issues/46)) ([e768205](https://github.com/NatLabRockies/r2x-reeds/commit/e768205f5d73fced70e3b97d166920c41053c7b9))


### 📦 Build

* **deps:** bump actions/download-artifact from 7 to 8 ([#48](https://github.com/NatLabRockies/r2x-reeds/issues/48)) ([824a4bd](https://github.com/NatLabRockies/r2x-reeds/commit/824a4bd191f3253b1fc91a78f11da26c10304cc3))
* **deps:** bump actions/upload-artifact from 6 to 7 ([#49](https://github.com/NatLabRockies/r2x-reeds/issues/49)) ([f84f280](https://github.com/NatLabRockies/r2x-reeds/commit/f84f280430a94a88d088102393939bf982146442))

## [0.3.5](https://github.com/NatLabRockies/r2x-reeds/compare/v0.3.4...v0.3.5) (2026-02-04)


### 🐛 Bug Fixes

* **ci:** removing stale reference to pre-commit ([#44](https://github.com/NatLabRockies/r2x-reeds/issues/44)) ([128116e](https://github.com/NatLabRockies/r2x-reeds/commit/128116e60d62d36be4a5907acc7e01d6b1eeeeb1))
* **parser:** Deduping generators on the source data ([#45](https://github.com/NatLabRockies/r2x-reeds/issues/45)) ([0edac97](https://github.com/NatLabRockies/r2x-reeds/commit/0edac977dc9f9abf7a68a5b7988c87b497c3996d))


### 📚 Documentation

* **README.md:** matching latest API on the readme ([#31](https://github.com/NatLabRockies/r2x-reeds/issues/31)) ([315b68b](https://github.com/NatLabRockies/r2x-reeds/commit/315b68b3dae464043af0605dc5f46d312e7c8679))

## [0.3.4](https://github.com/NatLabRockies/r2x-reeds/compare/v0.3.3...v0.3.4) (2026-01-23)


### 🧹 Refactoring

* **r2x-core:** Updating the codebase too match latest plugin discovery. ([#41](https://github.com/NatLabRockies/r2x-reeds/issues/41)) ([1ca11ab](https://github.com/NatLabRockies/r2x-reeds/commit/1ca11abc2b529afabd1483b48236b79cb699a559))

## [0.3.3](https://github.com/NREL/r2x-reeds/compare/v0.3.2...v0.3.3) (2026-01-14)


### 🐛 Bug Fixes

* `break_gens` plugin default technologies and logging ([#39](https://github.com/NREL/r2x-reeds/issues/39)) ([9dd0304](https://github.com/NREL/r2x-reeds/commit/9dd0304fa5aecfd3b12985bcddd7b9610d65d836))

## [0.3.2](https://github.com/NREL/r2x-reeds/compare/v0.3.1...v0.3.2) (2026-01-12)


### Bug Fixes

* Adding correct function call for the plugin `break_gens` ([#35](https://github.com/NREL/r2x-reeds/issues/35)) ([ee06e88](https://github.com/NREL/r2x-reeds/commit/ee06e888a777cca784ab5ec3e62305d1ae682b5d))

## [0.3.1](https://github.com/NREL/r2x-reeds/compare/v0.3.0...v0.3.1) (2026-01-07)


### Bug Fixes

* truncate time series to be equally for all ([#32](https://github.com/NREL/r2x-reeds/issues/32)) ([0824b21](https://github.com/NREL/r2x-reeds/commit/0824b21e1a1bc8916eb16d36b8d773cc9f6638b9))

## [0.3.0](https://github.com/NREL/r2x-reeds/compare/v0.2.1...v0.3.0) (2025-12-11)


### Features

* Updating transmission cost and distance file and adding upgrader ([#26](https://github.com/NREL/r2x-reeds/issues/26)) ([f5b6278](https://github.com/NREL/r2x-reeds/commit/f5b6278dd166b6d33e558a8c57b32adaada4fd43))


### Bug Fixes

* add new rtes tech in reeds default .json file ([#21](https://github.com/NREL/r2x-reeds/issues/21)) ([ab63b0d](https://github.com/NREL/r2x-reeds/commit/ab63b0db44c7484fa19698acdc0b3abcf43bfe9f))

## [0.2.1](https://github.com/NREL/r2x-reeds/compare/v0.2.0...v0.2.1) (2025-12-01)


### Bug Fixes

* Improving mapping for latest runs ([#16](https://github.com/NREL/r2x-reeds/issues/16)) ([789022b](https://github.com/NREL/r2x-reeds/commit/789022b8d2bc27ac8a7bbe64ffd08f52b369cb16))

## [0.2.0](https://github.com/NREL/r2x-reeds/compare/v0.1.0...v0.2.0) (2025-11-29)


### Features

* Simplifying parser and make it clean ([#12](https://github.com/NREL/r2x-reeds/issues/12)) ([a8c75ba](https://github.com/NREL/r2x-reeds/commit/a8c75ba27618326d996f7bacb2b3183f3df2fa4c))
