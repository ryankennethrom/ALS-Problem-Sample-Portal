const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const source = relative => readFileSync(path.resolve(root, relative), 'utf8');

test('browser metadata uses Problem Samples Tracker', () => {
  const layout = source('app/layout.tsx');
  assert.match(layout, /title:\s*'Problem Samples Tracker'/);
  assert.match(layout, /description:\s*'Problem sample management and tracking'/);
});

test('sidebar and topbar display Problem Samples Tracker', () => {
  const shell = source('components/AppShell.tsx');
  assert.match(shell, /brand-label">Problem Samples Tracker</);
  assert.match(shell, /topbar-title">Problem Samples Tracker</);
});

test('both sign-in screens show the new name', () => {
  for (const page of ['app/login/page.tsx', 'app/login/verify/page.tsx']) {
    assert.match(source(page), /Problem Samples<br\s*\/>Tracker/);
    assert.doesNotMatch(source(page), /ALS Ticket<br\s*\/>Tracker/);
  }
});

test('account guidance uses the new application name', () => {
  assert.match(source('components/RequiredRoleModal.tsx'), /use the Problem Samples Tracker/);
});

test('outbound email and Excel report labels use the new application name', () => {
  const backend = ['problem_samples/views.py', 'problem_samples/dashboard_views.py', 'problem_samples/monthly_report_portal.py'];
  for (const relative of backend) {
    const content = source('../backend/' + relative);
    assert.ok(/Problem Samples Tracker|PROBLEM SAMPLES TRACKER/.test(content), `${relative} should include new branding`);
    assert.doesNotMatch(content, /ALS Ticket Tracker|ALS TICKET TRACKER/);
  }
});
