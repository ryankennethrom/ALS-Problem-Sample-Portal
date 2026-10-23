const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../..');
const read = rel => fs.readFileSync(path.join(root, rel), 'utf8');
test('admin Lab All mention summary is a read operation', () => {
  const source = read('backend/problem_samples/views.py');
  const start = source.indexOf('def mention_inbox(self, request):');
  const end = source.indexOf('@action(', start + 10);
  const code = source.slice(start, end);
  assert.match(code, /selected_lab = active_lab\(request\)/);
  assert.doesNotMatch(code, /active_lab\(request, require_specific=True\)/);
  assert.match(code, /'unread_count': unread_count/);
});
test('backup restore failures expose the concrete reason in backend logs', () => {
  const source = read('backend/problem_samples/backup_restore_views.py');
  assert.match(source, /logger\.warning\('Backup restore rejected/);
  assert.match(source, /'detail': str\(exc\)/);
});
test('compatibility checked separately from destructive restore', () => {
  const page = read('frontend/app/backup-restore/page.tsx');
  assert.match(page, /inspect-upgrade/);
  assert.match(page, /body\.append\('kind', kind\)/);
  assert.match(page, /Backup restore rejected/);
});
