const test = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const source = (path) => readFileSync(join(__dirname, '..', path), 'utf8');

test('table policy exposes an explicit never-expire option', () => {
  const page = source('app/tables/[id]/page.tsx');
  assert.match(page, /Tracking Link Expiration After Terminal Workflow/);
  assert.match(page, /<option value="never">Never expire<\/option>/);
  assert.match(page, /<option value="days">Expire after a specified number of days<\/option>/);
});

test('admin can choose 0 through 3650 days, or null for never', () => {
  const page = source('app/tables/[id]/page.tsx');
  assert.match(page, /terminalTrackingDays === null \? 'never' : 'days'/);
  assert.match(page, /min=\{0\} max=\{3650\}/);
  assert.match(page, /e\.target\.value === 'never' \? null : 30/);
});

test('table details save includes the tracking link expiry setting', () => {
  const page = source('app/tables/[id]/page.tsx');
  assert.match(page, /terminal_tracking_link_days: terminalTrackingDays/);
  assert.match(page, /d\.terminal_tracking_link_days === undefined \? 30 : d\.terminal_tracking_link_days/);
});

test('table model includes nullable terminal expiry duration', () => {
  const lib = source('lib/problemTables.ts');
  assert.match(lib, /terminal_tracking_link_days: number \| null/);
  const model = source('../backend/problem_samples/models.py');
  assert.match(model, /terminal_tracking_link_days = models\.PositiveIntegerField\([\s\S]*?null=True,[\s\S]*?default=30/);
});

test('terminal expiration logic and API are distinct from automatic disposal and pending routed workflows', () => {
  const model = source('../backend/problem_samples/models.py');
  assert.match(model, /if self\.workflow_status in TERMINAL_PROBLEM_STATUSES:/);
  assert.match(model, /return None if days is None else anchor \+ timedelta\(days=days\)/);
  assert.match(model, /return anchor \+ timedelta\(days=TRACKING_LINK_DAYS\)/);
  const serializer = source('../backend/problem_samples/serializers.py');
  assert.match(serializer, /'terminal_tracking_link_days'/);
});
