const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');

const root = join(__dirname, '..', '..');
const read = file => readFileSync(join(root, file), 'utf8');

const activeFiles = [
  'backend/problem_samples/models.py',
  'backend/problem_samples/views.py',
  'backend/problem_samples/dashboard_views.py',
  'frontend/app/follow-up-required/page.tsx',
  'frontend/app/follow-up-required/customer-responded/page.tsx',
  'frontend/app/dashboard/page.tsx',
  'frontend/app/tables/[id]/page.tsx',
  'frontend/lib/problemTables.ts',
  'frontend/components/ContainersView.tsx',
];

test('all active workflow labels use Follow Up Required, not CS Follow-Up', () => {
  for (const file of activeFiles) {
    const source = read(file);
    assert.ok(source.includes('Follow Up Required'), `${file} must show the renamed workflow`);
    assert.doesNotMatch(source, /CS Follow[- ]Up/i, `${file} still contains a retired label`);
  }
});

test('routing constant uses the updated database workflow value', () => {
  const models = read('backend/problem_samples/models.py');
  assert.match(models, /CURRENT_WORKFLOW_DEFAULT = 'Follow Up Required'/);
  assert.match(models, /CURRENT_WORKFLOW_CHOICES = \[CURRENT_WORKFLOW_DEFAULT, CURRENT_WORKFLOW_WAITING_FOR_CUSTOMER/);
  const dashboard = read('backend/problem_samples/dashboard_views.py');
  assert.match(dashboard, /current_workflow=CURRENT_WORKFLOW_DEFAULT/);
  const tables = read('frontend/app/tables/[id]/page.tsx');
  assert.match(tables, /'Follow Up Required'/);
});

test('new migration preserves the old migration history and renames existing workflow data', () => {
  const migration = read('backend/problem_samples/migrations/0095_rename_cs_follow_up_workflow.py');
  assert.match(migration, /'0094_merge_customer_return_label'/);
  assert.match(migration, /OLD_WORKFLOW = 'CS Follow-Up'/);
  assert.match(migration, /NEW_WORKFLOW = 'Follow Up Required'/);
  assert.match(migration, /migrations\.AlterField\(/);
  assert.match(migration, /migrations\.RunPython\(forwards, backwards\)/);
  assert.match(migration, /disposal_snapshot/);
  assert.match(migration, /intercolumn_rules/);
});

test('historical workflow changes show the new name without rewriting audit records', () => {
  const historyPage = read('frontend/app/problems/[id]/page.tsx');
  assert.match(historyPage, /value === 'CS Follow-Up'\) return 'Follow Up Required'/);
  const migration = read('backend/problem_samples/migrations/0095_rename_cs_follow_up_workflow.py');
  assert.doesNotMatch(migration, /ProblemHistory\.objects/);
});
