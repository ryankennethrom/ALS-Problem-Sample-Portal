const assert = require('node:assert/strict');
const { test } = require('node:test');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');

const root = join(__dirname, '..', '..');
const load = (file) => readFileSync(join(root, file), 'utf8');

for (const route of ['track', 'acknowledge']) {
  test(`${route}: message action is first and is the primary choice`, () => {
    const source = load(`frontend/app/${route}/[token]/page.tsx`);
    const options = source.match(/<div className="public-ack-action-buttons">([\s\S]*?)<\/div>/)?.[1];
    assert.ok(options, 'customer action group must exist');
    const message = options.indexOf('>Message us about this issue</button>');
    const disposal = options.indexOf('>Permit immediate disposal</button>');
    const returns = options.indexOf('>I want these sample(s) back</button>');
    assert.ok(message >= 0 && disposal > message && returns > disposal, 'message, disposal, return order');
    assert.match(options, /<button className="button"[\s\S]*?>Message us about this issue<\/button>/);
    assert.match(options, /<button className="button secondary"[\s\S]*?>Permit immediate disposal<\/button>/);
  });
  test(`${route}: action behavior and signature checks are unchanged`, () => {
    const source = load(`frontend/app/${route}/[token]/page.tsx`);
    const options = source.match(/<div className="public-ack-action-buttons">([\s\S]*?)<\/div>/)?.[1];
    assert.match(options, /disabled=\{busy \|\| !effectiveSignature\}[\s\S]*?setRequestedInfoOpen\(true\)/);
    assert.match(options, /disabled=\{busy \|\| !signature\.trim\(\)\} onClick=\{\(\) => chooseAction\('dispose'\)\}/);
    assert.match(options, /setReturnDialogOpen\(true\)/);
  });
}

test('customer-facing selected label is updated without altering stored action codes or audit records', () => {
  const models = load('backend/problem_samples/models.py');
  const views = load('backend/problem_samples/views.py');
  assert.match(models, /CUSTOMER_ACTION_REQUESTED_INFORMATION = 'requested_info'/);
  assert.match(views, /CUSTOMER_ACTION_REQUESTED_INFORMATION: 'Message us about the issue'/);
  for (const route of ['track', 'acknowledge']) {
    const source = load(`frontend/app/${route}/[token]/page.tsx`);
    assert.match(source, /requested_info: 'Message us about this issue'/);
    assert.equal((source.match(/data\.customer_action === 'requested_info' \? actionLabels\.requested_info/g) || []).length, 2);
  }
});
