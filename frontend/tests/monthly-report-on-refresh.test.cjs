'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.join(__dirname, '..');
const shell = fs.readFileSync(path.join(root, 'components/AppShell.tsx'), 'utf8');
const routes = fs.readFileSync(path.join(root, '../backend/config/urls.py'), 'utf8');
const views = fs.readFileSync(path.join(root, '../backend/problem_samples/system_email_views.py'), 'utf8');
const service = fs.readFileSync(path.join(root, '../backend/problem_samples/system_email_service.py'), 'utf8');
const dashboard = fs.readFileSync(path.join(root, 'app/dashboard/page.tsx'), 'utf8');
const queuePage = fs.readFileSync(path.join(root, 'app/send-system-emails/page.tsx'), 'utf8');

test('app reload queues report eligibility check once per authenticated session, not on public routes', () => {
  assert.match(shell, /const monthlyRefreshCheckStarted = useRef\(false\)/);
  assert.match(shell, /monthlyRefreshCheckStarted\.current = true/);
  assert.match(shell, /user\.needs_lab[\s\S]*user\.needs_email[\s\S]*user\.needs_role/);
  assert.match(shell, /pathname\.startsWith\('\/track\/'\)/);
  assert.match(shell, /api\('\/system-emails\/check-on-refresh\/', \{method:'POST'\}\)/);
});

test('refresh endpoint checks monthly rules without sending messages or disclosing counts', () => {
  assert.match(routes, /api\/system-emails\/check-on-refresh\//);
  const view = views.split('class QueueMonthlyReportsOnRefreshView(APIView):')[1].split('class QueueDueSystemEmailsView')[0];
  assert.match(view, /check_monthly_reports_on_app_refresh\(\)/);
  assert.match(view, /'monthly_reports_checked': monthly_ok/);
  assert.match(view, /'client_email_escalations_checked': escalation_ok/);
  assert.doesNotMatch(view, /is_admin\(/);
  assert.doesNotMatch(view, /to_emails|report_snapshot|recipient/);
});

test('backend deduplicates refresh checks but leaves the manual and idempotent queue intact', () => {
  assert.match(service, /cache\.add\(lock_key, True, timeout=120\)/);
  assert.match(service, /cache\.set\(cache_key, True, timeout=300\)/);
  assert.match(service, /cache\.delete\(lock_key\)/);
  assert.match(service, /queue_due_monthly_reports\(\)/);
  assert.match(views, /class QueueDueSystemEmailsView\(APIView\)/);
});

test('dashboard and system emails refresh their counts after an automatic report check', () => {
  assert.match(shell, /dispatchEvent\(new Event\('monthly-reports-checked'\)\)/);
  assert.match(dashboard, /addEventListener\('monthly-reports-checked', refreshPending\)/);
  assert.match(queuePage, /addEventListener\('monthly-reports-checked', refreshAfterCheck\)/);
});
