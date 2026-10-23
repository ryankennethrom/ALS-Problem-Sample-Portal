const test = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');

const root = join(__dirname, '..');
const accounts = readFileSync(join(root, 'app/accounts/page.tsx'), 'utf8');
const myAccount = readFileSync(join(root, 'app/account/page.tsx'), 'utf8');
const appShell = readFileSync(join(root, 'components/AppShell.tsx'), 'utf8');
const api = readFileSync(join(root, '../backend/accounts/views.py'), 'utf8');
const urls = readFileSync(join(root, '../backend/accounts/urls.py'), 'utf8');

test('new account form sends email and role with the name', () => {
  assert.match(accounts, /first_name: firstName, last_name: lastName, email: newEmail\.trim\(\)\.toLowerCase\(\), role: newRole/);
  assert.match(accounts, /id="new-email"[^>]*required/);
  assert.match(accounts, /id="new-role"[^>]*required/);
});

test('admin can edit existing account email and role', () => {
  assert.match(accounts, /\/auth\/accounts\/\$\{editingAccount\.id\}\/profile\//);
  assert.match(urls, /accounts\/<int:user_id>\/profile\//);
});

test('my account displays role and email read-only without a self-service save form', () => {
  assert.match(myAccount, /value=\{user\?\.email \|\| 'Not assigned'\} readOnly/);
  assert.match(myAccount, /value=\{user\?\.role_label \|\| 'Not assigned'\} readOnly/);
  assert.doesNotMatch(myAccount, /method: 'PATCH'/);
});

test('backend rejects self-service changes and enforces admin role and email validation', () => {
  assert.match(api, /def me\(request\):[\s\S]*?if request\.method == 'PATCH':[\s\S]*?HTTP_403_FORBIDDEN/);
  assert.match(api, /def account_profile\(request, user_id\):[\s\S]*?is_tracker_admin\(request\.user\)/);
  assert.match(api, /def accounts\(request\):[\s\S]*?email = normalize_als_email\(request\.data\.get\('email'\)\)/);
});

test('missing account details no longer force self-edit dialogs', () => {
  assert.doesNotMatch(appShell, /<RequiredEmailModal/);
  assert.doesNotMatch(appShell, /<RequiredRoleModal/);
  assert.match(appShell, /Ask an administrator to assign/);
});
