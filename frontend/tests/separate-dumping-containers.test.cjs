const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const root = join(__dirname, '..', '..');
const read = name => readFileSync(join(root, name), 'utf8');

test('DC and PC identifiers have different prefixes and resolve by type', () => {
  const src = read('backend/problem_samples/models.py');
  assert.match(src, /prefix = 'DC' if self\.is_dumping else 'PC'/);
  assert.match(src, /is_dumping=dumping, lab_number=number/);
  assert.match(src, /is_dumping=dumping\)\.first\(\)/);
});

test('DC and PC have independent per-lab counters protected by a lock', () => {
  const src = read('backend/problem_samples/labs.py');
  assert.match(src, /select_for_update\(\)/);
  assert.match(src, /next_dumping_container_number/);
  assert.match(src, /if fields\.get\('is_dumping'\)/);
  assert.match(read('backend/accounts/models.py'), /next_dumping_container_number = models\.PositiveBigIntegerField/);
});

test('existing records are migrated to type-scoped uniqueness and DC sequence', () => {
  const src = read('backend/problem_samples/migrations/0096_separate_dumping_container_numbers.py');
  assert.match(src, /'0095_rename_cs_follow_up_workflow'/);
  assert.match(src, /'0009_merge_lab_id_and_dumping_counter'/);
  assert.match(src, /RemoveConstraint/);
  assert.match(src, /RunPython\(renumber_dumping_containers\)/);
  assert.match(src, /AddConstraint/);
  assert.match(src, /'lab', 'is_dumping', 'lab_number'/);
  assert.match(src, /order_by\('created_at', 'pk'\)/);
  assert.match(src, /next_dumping_container_number = len\(dumps\) \+ 1/);
});

test('dumping list excludes PC containers and keeps restored dumps for audit', () => {
  const src = read('frontend/components/ContainersView.tsx');
  assert.match(src, /recentlyDisposed\s*\? containers\s*\.filter\(container => container\.is_dumping\)/);
  assert.match(src, /: containers\.filter\(container => !container\.is_dumping\)/);
  assert.match(src, /Problem Sample Containers/);
  assert.match(src, /Dumping Containers/);
});

test('migration preserves legacy references alongside renamed ticket histories', () => {
  const src = read('backend/problem_samples/migrations/0096_separate_dumping_container_numbers.py');
  assert.match(src, /dump\.dumped_sample_ids/);
  assert.match(src, /container_id_renames/);
  assert.match(src, /details\['dumping_container_id'\] = new_id/);
});
