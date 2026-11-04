const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync, existsSync } = require('node:fs');
const { join } = require('node:path');
const root = join(__dirname, '..');
const backend = readFileSync(join(root, '../backend/problem_samples/dashboard_views.py'), 'utf8');
const urls = readFileSync(join(root, '../backend/config/urls.py'), 'utf8');
const sidebar = readFileSync(join(root, 'components/AppShell.tsx'), 'utf8');
const dashboard = readFileSync(join(root, 'app/dashboard/page.tsx'), 'utf8');
const path = join(root, 'app/resend-tracking-links/page.tsx');
const queue = readFileSync(path, 'utf8');

test('Sidebar shows the Resend Tracking Links tab only when a table has escalation enabled', () => {
  assert.match(sidebar, /resendQueueEnabled && <Link href="\/resend-tracking-links"/);
  assert.match(sidebar, /className="side-section-label">Action Required/);
  assert.match(sidebar, /api\('\/dashboard\/resend-tracking-links\/\?page=1'\)/);
  assert.match(sidebar, /selectedLabCode, pathname/);
});
test('Dashboard adds a conditional Resend Tracking Links card with live count and a queue link', () => {
  assert.match(dashboard, /data\?\.resend_tracking_links_enabled && <section/);
  assert.match(dashboard, /counts\.resend_tracking_links/);
  assert.match(dashboard, /href="\/resend-tracking-links"/);
  assert.match(backend, /counts\['resend_tracking_links'\] = resend_tracking_link_tickets\(base_tickets\)\.count\(\)/);
});
test('Queue backend enforces Follow Up Required and last history event is automatic priority escalation', () => {
  assert.match(backend, /current_workflow=CURRENT_WORKFLOW_DEFAULT, table_id__in=configured_tables/);
  assert.match(backend, /ProblemHistory\.objects\.filter\(problem_id=OuterRef\('pk'\)\)\.order_by\('-created_at', '-pk'\)/);
  assert.match(backend, /last_history_id__in=qualifying_ids/);
  assert.match(backend, /summary=ESCALATION_HISTORY_SUMMARY/);
  assert.match(backend, /details__from_priority__isnull=False/);
  assert.match(backend, /details__to_priority__isnull=False/);
  assert.match(backend, /details__reason__endswith=ESCALATION_REASON_END/);
});
test('Queue API is lab scoped, searchable, paginated, and returns the escalation reason', () => {
  assert.match(urls, /api\/dashboard\/resend-tracking-links\//);
  assert.match(backend, /scoped = scope_tickets\(request, ProblemSample\.objects\.all\(\)\)/);
  assert.match(backend, /PAGE_SIZE = 50/);
  assert.match(backend, /'reason': display_escalation_reason\(/);
  assert.match(queue, /data\?\.results\.map\(ticket =>/);
  assert.match(queue, /href=\{`\/problems\/\$\{ticket.id\}`\}/);
});
test('Action Required email includes queue only if escalation is configured', () => {
  assert.match(backend, /if resend_tracking_links_enabled\(\):\s+rows\.insert\(2, \('Resend Tracking Links', 'resend_tracking_links'/);
});
test('New Resend Tracking Links page exists with direct ticket navigation', () => {
  assert.ok(existsSync(path));
  assert.match(queue, /No tracking links currently need resending/);
  assert.match(queue, /Escalation reason/);
  assert.match(queue, /Enable <strong>Make next priority email list/);
});
