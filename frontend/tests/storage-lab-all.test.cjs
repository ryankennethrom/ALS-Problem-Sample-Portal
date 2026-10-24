const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const ui = readFileSync(join(__dirname, '../app/dashboard/page.tsx'), 'utf8');
const backend = readFileSync(join(__dirname, '../../backend/problem_samples/dashboard_views.py'), 'utf8');

test('storage dashboard section is shown only for admins who selected Lab: All', () => {
  assert.match(ui, /showStorageAnalytics = Boolean\(currentUser\?\.is_admin && activeLabCode\(\) === 'ALL'\)/);
  assert.match(ui, /\{showStorageAnalytics && \([\s\S]*?<h3 className=\{styles\.subsectionHeading\}>Storage<\/h3>/);
});

test('storage API is only requested when Lab: All is authorized', () => {
  const effect = ui.slice(ui.indexOf('// Storage data is server-wide'), ui.indexOf('},[showStorageAnalytics]);'));
  assert.match(effect, /if \(!showStorageAnalytics\)\s*\{/);
  assert.ok(effect.indexOf('if (!showStorageAnalytics)') < effect.indexOf("api('/dashboard/storage/')"));
});

test('backend denies specific-lab storage requests instead of returning server-wide telemetry', () => {
  const endpoint = backend.slice(backend.indexOf('class DashboardStorageView'), backend.indexOf('class DashboardOpenedTicketsView'));
  assert.match(endpoint, /if active_lab\(request\) is not None:/);
  assert.match(endpoint, /raise PermissionDenied\('Storage analytics are available only in Lab: All\.'\)/);
});
