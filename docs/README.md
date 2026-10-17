# r2x-reeds documentation

The Astro and Starlight site follows the R2X navigation: tutorials, how-to guides,
reference/API, explanation, troubleshooting, changelog, and contributors.
Starlight builds a Pagefind search index with the site.

## Build and preview

Use Node.js 22.12 or newer and npm. From the repository root:

```bash
cd docs
npm ci
npm run build
```

The output is `docs/_build/`. Run `npm run preview` from `docs/` and open the printed
URL under `/r2x-reeds/`. Use a free port, for example `npm run preview -- --port 4334`,
when another preview is running. Use `npm run dev` while editing.

## Authoring

Edit `src/content/docs/` and navigation in `astro.config.mjs`. Use `/r2x-reeds/`-prefixed
page links. Check the built pages, internal links and search after edits.
Current API pages link to the verified main revision; edit links target main.

There are no fabricated release archives or release metadata files.
The versions page links to Git tags so readers can inspect actual tagged source docs.
Keep `CHANGELOG.md` canonical and link to the unversioned PyPI project page.

Legacy Sphinx `.html` URLs are static redirect files in `public/`. The homepage
continues to serve `index.html`; its existing URL needs no redirect.

## Publication

The existing `.github/workflows/docs.yaml` builds pull requests, pushes to main,
and manual dispatches with Node.js 22.23.1 and `npm ci`. Astro writes `_build/`
relative to `docs/`, matching the existing `publish_dir: docs/_build/`.
Only pushes to main invoke the existing gh-pages publication step.
The workflow keeps its existing provider, triggers, publication branch and permissions.
