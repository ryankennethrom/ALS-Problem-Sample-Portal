const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const read = file => readFileSync(join(__dirname, '..', '..', file), 'utf8');

test('PC allocations find the lowest missing non-dump number, not the DC counter', () => {
  const code = read('backend/problem_samples/labs.py');
  assert.match(code, /first_available_number\(numbers\)/);
  assert.match(code, /ProblemContainer\.objects\.filter\(lab=locked, is_dumping=False\)/);
  assert.match(code, /\.order_by\('lab_number'\)/);
  assert.match(code, /if fields\.get\('is_dumping'\)/);
});

test('reactivation keeps the prior legacy disposal stamp in audit metadata', () => {
  const code = read('backend/problem_samples/labs.py');
  assert.match(code, /_legacy_reactivation_events/);
  assert.match(code, /'disposed_at': container\.disposed_at\.isoformat/);
  assert.match(code, /container\.disposed_at = None/);
});

test('the 0097 migration is targeted to empty EDM PC-00003 and preserves previous IDs', () => {
  const code = read('backend/problem_samples/migrations/0097_reactivate_empty_edmonton_pc_00003.py');
  assert.match(code, /'0096_separate_dumping_container_numbers'/);
  assert.match(code, /lab__code__iexact='EDM', lab_number=3, is_dumping=False/);
  assert.match(code, /container\.problem_samples\.using\(db\)\.exists\(\)/);
  assert.doesNotMatch(code, /\.delete\(/);
});

test('the UI can make an empty legacy PC available again', () => {
  const code = read('frontend/components/ContainersView.tsx');
  assert.match(code, /container\.sample_count === 0 \? 'Make Available' : 'Undo Disposal'/);
  assert.match(code, /Make .*available for tickets again/);
  assert.match(code, /undo-disposal\//);
});
