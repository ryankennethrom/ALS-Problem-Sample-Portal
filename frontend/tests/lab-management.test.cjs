const assert = require('node:assert/strict');
const {test} = require('node:test');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const root = join(__dirname, '..');
const management = readFileSync(join(root, 'app/lab-settings/page.tsx'), 'utf8');
const shell = readFileSync(join(root, 'components/AppShell.tsx'), 'utf8');
const css = readFileSync(join(root, 'app/globals.css'), 'utf8');

test('labs have add, rename, delete controls with API methods', () => {
  assert.match(management, /method: 'POST'/);
  assert.match(management, /method: 'PATCH'/);
  assert.match(management, /method: 'DELETE'/);
  assert.match(management, /editingName/);
});

test('delete UI warns about data and requires confirmation', () => {
  assert.match(management, /window\.confirm/);
  assert.match(management, /can_delete/);
  assert.match(management, /references/);
});

test('lab code immutable when renaming', () => {
  assert.match(management, /stays unchanged/);
  assert.match(management, /JSON\.stringify\(\{ name: editingName\.trim\(\) \}\)/);
});

test('sidebar selector is styled and accessible', () => {
  assert.match(shell, /sidebar-lab-dropdown/);
  assert.match(shell, /aria-label="Select active lab"/);
  assert.match(css, /\.sidebar-lab-control:focus-within/);
});

test('sidebar scrolls without clipping Logout even on mobile', () => {
  assert.match(shell, /<span className="side-label">Logout<\/span>/);
  assert.match(css, /\.admin-shell \.side-nav\{[\s\S]*?flex:1 1 auto;min-height:0;max-height:none;overflow-y:auto/);
  assert.match(css, /\.admin-shell \.sidebar \.side-nav\{flex:1 1 auto;min-height:0;overflow-y:auto/);
});
