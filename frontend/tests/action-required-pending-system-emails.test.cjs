const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const root = join(__dirname, '..');
const dashboardView = readFileSync(join(root, '../backend/problem_samples/dashboard_views.py'), 'utf8');
const dashboard = readFileSync(join(root, 'app/dashboard/page.tsx'), 'utf8');
const modal = readFileSync(join(root, 'components/ActionRequiredEmailModal.tsx'), 'utf8');

test('Action Required email includes pending system email count and queue URL', () => {
  assert.match(dashboardView, /\('Pending System Emails', 'pending_system_emails', '\/send-system-emails#pending-system-emails'\)/);
  assert.match(dashboardView, /counts\['pending_system_emails'\] = pending_emails\.count\(\)/);
  assert.match(dashboardView, /'counts': \{key: counts\[key\] for _, key, _ in rows\}/);
});

test('Pending system emails are filtered to pending status and current lab only', () => {
  assert.match(dashboardView, /SystemEmail\.objects\.filter\(status=SystemEmail\.STATUS_PENDING\)/);
  assert.match(dashboardView, /if lab is not None:\s+pending_emails = pending_emails\.filter\(lab=lab\)/);
});

test('Dashboard pending queue and email link point to the same page', () => {
  assert.match(dashboard, /aria-label="Pending System Emails"/);
  assert.match(dashboard, /href="\/send-system-emails#pending-system-emails"/);
});

test('Send Action Required dialog explains that pending system emails are included', () => {
  assert.match(modal, /pending system-email count/);
});
