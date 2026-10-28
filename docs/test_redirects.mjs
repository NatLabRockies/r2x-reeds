import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { runInNewContext } from 'node:vm';

const script = readFileSync(new URL('./public/legacy-redirect.js', import.meta.url), 'utf8');
const members = JSON.parse(readFileSync(new URL('./public/api-fragments.json', import.meta.url), 'utf8'));

function redirected(pathname, hash, canonical) {
  return new Promise((resolve) => {
    runInNewContext(script, {
      document: { querySelector: () => ({ getAttribute: () => canonical }) },
      window: { location: { pathname, hash, replace: resolve } },
      fetch: async () => ({ ok: true, json: async () => members }),
      console,
    });
  });
}

test('legacy API bookmarks reach public objects and exact members', async () => {
  for (const [fragment, destination] of Object.entries(members)) {
    assert.equal(await redirected('/r2x-reeds/references/api.html', `#${fragment}`, '/r2x-reeds/reference/python-api/'), destination);
  }
  assert.equal(members['r2x_reeds.parser.ReEDSParser'], '/r2x-reeds/reference/api/reedsparser/');
  assert.equal(members['r2x_reeds.plugin_config.ReEDSConfig.solve_year'], '/r2x-reeds/reference/api/reedsconfig/#solve_year');
});

test('other old guide URLs retain their section bookmark', async () => {
  assert.equal(await redirected('/r2x-reeds/references/transforms.html', '#configuration-summary', '/r2x-reeds/reference/transforms/'), '/r2x-reeds/reference/transforms/#configuration-summary');
});
