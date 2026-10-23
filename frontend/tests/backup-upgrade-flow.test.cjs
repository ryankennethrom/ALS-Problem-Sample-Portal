const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');

const page = fs.readFileSync(path.join(__dirname, '../app/backup-restore/page.tsx'), 'utf8');

test('old Full Backup compatibility preview uses its dedicated endpoint', () => {
  assert.match(page, /\/admin\/backup-restore\/inspect-upgrade\//);
  assert.match(page, /Check backup compatibility/);
});
test('upgrade confirmation is distinct from a regular restore', () => {
  assert.match(page, /UPGRADE AND RESTORE FULL BACKUP/);
  assert.match(page, /kind === 'upgrade'/);
});
test('restore is gated on staging isolation and acknowledgment', () => {
  assert.match(page, /upgradePreview\?\.can_create_staging_database/);
  assert.match(page, /safetyAcknowledged/);
});
test('regular Full Restore continues to exist', () => {
  assert.match(page, /kind="full" title="Restore Full Backup"/);
});
