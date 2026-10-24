const test = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const root = join(__dirname, '..');
const page = readFileSync(join(root, 'app/accounts/page.tsx'), 'utf8');
const styles = readFileSync(join(root, 'app/globals.css'), 'utf8');

test('account editing is a modal dialog rather than an inline panel', () => {
  assert.match(page, /editingAccount && <div className="account-edit-overlay"/);
  assert.match(page, /className="account-edit-dialog" role="dialog" aria-modal="true"/);
  assert.doesNotMatch(page, /editingAccount && <section className="panel panel-blue"/);
});

test('modal retains email, role, lab and existing PATCH save route', () => {
  assert.match(page, /id="edit-email"[^>]*type="email"[^>]*required/);
  assert.match(page, /id="edit-role"[^>]*required/);
  assert.match(page, /id="edit-lab"[^>]*required/);
  assert.match(page, /method: 'PATCH'/);
  assert.match(page, /\$\{editingAccount\.id\}\/profile\//);
});

test('modal closes on cancel, close button, backdrop click, and Escape', () => {
  assert.match(page, /if \(event\.target === event\.currentTarget && !busyAction\) setEditingAccount\(null\)/);
  assert.match(page, /event\.key === 'Escape'/);
  assert.match(page, /aria-label="Close edit account popup"/);
  assert.match(page, />Cancel<\/button>/);
});

test('errors remain in edit dialog and the modal has keyboard focus management', () => {
  assert.match(page, /editDialogRef\.current/);
  assert.match(page, /event\.key !== 'Tab'/);
  assert.match(page, /\{editError && <div className="error" role="alert">\{editError\}<\/div>\}/);
  assert.match(page, /setEditError\(e instanceof Error/);
});

test('modal supports small screens and has a scrollable maximum height', () => {
  assert.match(styles, /\.account-edit-overlay\{position:fixed/);
  assert.match(styles, /\.account-edit-dialog\{[^}]*max-height:calc\(100dvh - 40px\)/);
  assert.match(styles, /@media\(max-width:540px\)\{\.account-edit-overlay/);
});
