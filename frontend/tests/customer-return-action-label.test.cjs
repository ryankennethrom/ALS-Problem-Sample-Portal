const assert = require('node:assert/strict');
const { test } = require('node:test');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');

const root = join(__dirname, '..', '..');
const load = file => readFileSync(join(root, file), 'utf8');
const newLabel = 'I want these sample(s) back';

for (const route of ['track', 'acknowledge']) {
  test(`public ${route} page uses the updated customer return label everywhere`, () => {
    const source = load(`frontend/app/${route}/[token]/page.tsx`);
    assert.match(source, /ship_back: 'I want these sample\(s\) back'/);
    assert.match(source, /\}>I want these sample\(s\) back<\/button>/);
    assert.match(source, /<h2 id="return-samples-title">I want these sample\(s\) back<\/h2>/);
    assert.doesNotMatch(source, /Take back sample\(s\)/i);
  });
}

test('backend model and API responses use the new label without changing the ship_back action', () => {
  const models = load('backend/problem_samples/models.py');
  const views = load('backend/problem_samples/views.py');
  assert.ok(models.includes(`(CUSTOMER_ACTION_SHIP_BACK, '${newLabel}')`));
  assert.ok(views.includes(`CUSTOMER_ACTION_SHIP_BACK: '${newLabel}'`));
  assert.ok(views.includes(`f'${newLabel} — {shipping_method_labels[shipping_method]}'`));
  assert.doesNotMatch(views, /Take back sample\(s\)/i);
  assert.match(models, /CUSTOMER_ACTION_SHIP_BACK = 'ship_back'/);
});

test('label-only Django migration retains ship_back database value', () => {
  const migration = load('backend/problem_samples/migrations/0093_customer_return_label.py');
  assert.match(migration, /\('ship_back', 'I want these sample\(s\) back'\)/);
  assert.match(migration, /migrations\.AlterField/);
  assert.doesNotMatch(migration, /RunPython|RunSQL/);
});
