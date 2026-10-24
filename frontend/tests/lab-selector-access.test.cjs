const assert = require('node:assert/strict');
const { test } = require('node:test');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');

const root = join(__dirname, '..');
const shell = readFileSync(join(root, 'components/AppShell.tsx'), 'utf8');
const css = readFileSync(join(root, 'app/globals.css'), 'utf8');
const api = readFileSync(join(root, 'lib/api.ts'), 'utf8');
const backend = readFileSync(join(root, '../backend/problem_samples/labs.py'), 'utf8');
const labApi = readFileSync(join(root, '../backend/accounts/lab_views.py'), 'utf8');

test('administrators get styled menu items, lab names and codes', () => {
  assert.match(shell, /user\?\.is_admin \? \(/);
  assert.match(shell, /role="listbox"/);
  assert.match(shell, /role="option" aria-selected=/);
  assert.match(shell, /sidebar-lab-option-badge/);
  assert.match(shell, /Lab code: \$\{option\.code\}/);
  assert.match(css, /\.sidebar-lab-menu\{/);
  assert.match(css, /\.sidebar-lab-option\.selected\{/);
});

test('staff see a locked assignment, not a change control', () => {
  assert.match(shell, /sidebar-lab-locked/);
  assert.match(shell, /Lab switching is restricted to administrators/);
  assert.match(shell, /if \(!user\?\.is_admin\) return;/);
  assert.match(shell, /const code = u\.is_admin \? \(storedCode \|\| u\.lab_code\) : u\.lab_code;/);
  assert.match(shell, /if \(storedCode !== code\) setActiveLabCode\(code\)/);
});

test('backend independently blocks changing a nonadmin active lab', () => {
  assert.match(backend, /if not admin_user\(request\.user\):/);
  assert.match(backend, /choice not in \{profile\.lab\.code, str\(profile\.lab_id\)\}/);
  assert.match(backend, /raise PermissionDenied\('You cannot access another lab\.'\)/);
  assert.match(api, /headers\.set\('X-Active-Lab', activeLabCode\(\)\)/);
  assert.match(labApi, /return Response\(\[_payload\(profile\.lab\)\] if profile and profile\.lab_id else \[\]\)/);
});

test('selector is keyboard operable and closes when clicked outside', () => {
  assert.match(shell, /event\.key === 'Escape'/);
  assert.match(shell, /event\.key === 'ArrowDown'/);
  assert.match(shell, /event\.key === 'ArrowUp'/);
  assert.match(shell, /event\.key === 'Home'/);
  assert.match(shell, /event\.key === 'End'/);
  assert.match(shell, /document\.addEventListener\('pointerdown', onOutsideClick\)/);
  assert.match(shell, /aria-expanded=\{open\}/);
});

test('collapsed sidebar expands before opening the menu', () => {
  assert.match(shell, /if \(collapsed\) \{ onExpand\(\); setOpen\(true\); \}/);
  assert.match(shell, /collapsed=\{collapsed\} onExpand=\{\(\) => setCollapsed\(false\)\}/);
});
