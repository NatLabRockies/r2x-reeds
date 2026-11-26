# r2x-reeds documentation

The Astro and Starlight site follows the R2X navigation: tutorials, how-to guides,
reference/API, explanation, troubleshooting, changelog, and contributors.
Starlight builds a Pagefind search index with the site.

## Build and preview

Use Node.js 22.12 or newer, npm and Python 3.11 or newer. From the repository root:

```bash
cd docs && npm ci && npm run build
```

The prebuild step runs `generate_api.py` using only the Python standard library.
It reads public exports and transform registrations, then writes ignored API pages
and a member sidebar from source. Edit the generator or Python source, not those
generated pages. The output is `docs/_build/`. Run `npm run preview` from `docs/` and open the printed
URL under `/r2x-reeds/`. Use a free port, for example `npm run preview -- --port 4334`,
when another preview is running. Use `npm run dev` while editing.

## Authoring

Edit `src/content/docs/` and navigation in `astro.config.mjs`. Use `/r2x-reeds/`-prefixed
page links. Check the built pages, internal links and search after edits.
Current API pages link to the verified main revision; edit links target main.

The old `/versions/` URL redirects to the single changelog. Legacy HTML guide
redirects retain section hashes, and generated mappings route qualified API
bookmarks to current object/member pages. Source tags remain
available from the homepage. No release-specific site archives are generated.
Keep `CHANGELOG.md` canonical and link to the unversioned PyPI project page.

Legacy Sphinx `.html` URLs are static redirect files in `public/`. The homepage
continues to serve `index.html`; its existing URL needs no redirect.

## Publication

The existing `.github/workflows/docs.yaml` builds pull requests, pushes to main,
and manual dispatches with Node.js 22.23.1 and `npm ci`. Astro writes `_build/`
relative to `docs/`, matching the existing `publish_dir: docs/_build/`.
Only pushes to main invoke the existing gh-pages publication step.
The workflow keeps its existing provider, triggers, publication branch and permissions.

## Execute Python examples

From the repository root with the development dependencies and a compatible
`r2x-core` providing table assembly installed:

```bash
uv run pytest tests/test_docs_examples.py tests/test_docs_api.py --no-cov
```

The console runner collects `python doctest` fences, keeps sequential blocks in
one page namespace, checks expected output and assertions, and rejects empty
collection or skipped examples. It runs the Pacific tutorial once in a temporary
workspace with the same seven supplemental operating-cost inputs and reads the
technology-upgrade set from the archive's HDF5 dataset. Other pages reload the
checked tutorial snapshot. The PCM inspection
script uses the guide's explicit 50 $/MW baseline policy. External production-only
policy profiles still require the user's reviewed data.

Use `--collect-only` to confirm discovery. The API test verifies all root exports
and registered modifier/config pages have member navigation and source links.
Both tests are under the normal `tests/` directory and run in existing CI.

`npm run build` also runs Node redirect tests and `validate_build.py`. They check
legacy API bookmark mappings, all built local page/anchor links, the single
changelog redirect and the native Starlight sidebar popover used on small screens.
Use a browser for final desktop/mobile appearance checks. Structural checks do
not establish visual appearance or replace a screenshot review.
