const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');

const shell = readFileSync(join(__dirname, '../components/AppShell.tsx'), 'utf8');
const nav = shell.split('<nav className="side-nav"')[1].split('<div className="side-section-label">Settings</div>')[0];
const start = nav.indexOf('<div className="side-section-label">Action Required</div>');
const end = nav.indexOf('<div className="side-section-label">Tables</div>');
const actionRequired = nav.slice(start, end);

test('one Action Required heading replaces the old Customer Service and Lab headings', () => {
  assert.ok(start >= 0 && end > start, 'Action Required must appear before Tables');
  assert.equal((nav.match(/side-section-label">Action Required<\/div>/g) || []).length, 1);
  assert.doesNotMatch(nav, /side-section-label">(?:Customer Service|Lab)<\/div>/);
});

test('all former Customer Service and Lab queue links are still in Action Required', () => {
  for (const url of [
    '/follow-up-required/tracking-not-sent',
    '/follow-up-required/customer-responded',
    '/follow-up-required/other',
    '/disposal/containers',
    '/disposal/samples',
    '/shipping/to-be-shipped',
    '/to-be-back-to-testing',
  ]) {
    assert.equal((actionRequired.match(new RegExp(`href="${url}"`, 'g')) || []).length, 1, `${url} must appear once`);
  }
  assert.match(actionRequired, /aria-expanded=\{disposalOpen\}/, 'Disposal must retain its collapsible subnavigation');
});

test('Send System Emails is inside Action Required, not a duplicate top-level link', () => {
  assert.match(actionRequired, /href="\/send-system-emails"/);
  assert.match(actionRequired, /side-label">Send System Emails<\/span>/);
  assert.equal((nav.match(/href="\/send-system-emails"/g) || []).length, 1);
  assert.ok(nav.indexOf('href="/send-system-emails"') > start);
});

test('Dashboard, Mentions, Tables and Admin retain their existing sidebar sections', () => {
  assert.ok(nav.indexOf('href="/dashboard"') < start);
  assert.ok(nav.indexOf('href="/mentions"') < start);
  assert.ok(nav.indexOf('<div className="side-section-label">Tables</div>') > start);
  assert.ok(nav.indexOf('<div className="side-section-label">Admin</div>') > end);
  assert.match(nav, /href=\{`\/problem-samples\?table=\$\{t\.id\}`\}/);
});
