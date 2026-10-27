const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');

const load = relative => readFileSync(join(__dirname, '..', relative), 'utf8');
const shell = load('components/AppShell.tsx');
const nav = shell.split('<nav className="side-nav"')[1].split('<div className="side-section-label">Settings</div>')[0];
const actionStart = nav.indexOf('<div className="side-section-label">Action Required</div>');
const actionEnd = nav.indexOf('<div className="side-section-label">Tables</div>');
const action = nav.slice(actionStart, actionEnd);

test('Create Ticket is a top-level link directly after Dashboard, before Mentions and Action Required', () => {
  const dashboard = nav.indexOf('href="/dashboard"');
  const create = nav.indexOf('href="/problems/new"');
  const mentions = nav.indexOf('href="/mentions"');
  assert.ok(dashboard >= 0 && create > dashboard && mentions > create && actionStart > mentions);
  const between = nav.slice(nav.indexOf('</Link>', dashboard) + '</Link>'.length, nav.lastIndexOf('<Link', create));
  assert.doesNotMatch(between, /href=|side-section-label/);
  assert.match(nav.slice(create, mentions), /side-label">Create Ticket<\/span>/);
});

test('Create Ticket appears only once and is not under Action Required', () => {
  assert.equal((nav.match(/href="\/problems\/new"/g) || []).length, 1);
  assert.doesNotMatch(action, /href="\/problems\/new"|side-label">Create Ticket<\/span>/);
  assert.match(nav, /pathname === '\/create-problem-sample' \|\| pathname === '\/problems\/new'/);
});

test('Others is consistently labelled in sidebar and Dashboard, with existing queue route and count key', () => {
  const dashboard = load('app/dashboard/page.tsx');
  assert.match(action, /href="\/follow-up-required\/other"[^]*?side-label">Others<\/span>/);
  assert.match(dashboard, /aria-label="Others: Follow Up Required tickets"/);
  assert.match(dashboard, /<div className=\{styles.label\}>Others<\/div>/);
  assert.match(dashboard, /counts\.customer_service_other/);
  assert.match(dashboard, /href="\/follow-up-required\/other"/);
});

test('Others heading and tabs match the renamed queue while its path stays /other', () => {
  const followUp = load('app/follow-up-required/page.tsx');
  const responded = load('app/follow-up-required/customer-responded/page.tsx');
  assert.match(followUp, /other \? 'Others' : 'Follow Up Required'/);
  for (const page of [followUp, responded]) {
    assert.match(page, /href="\/follow-up-required\/other">Others<\/Link>/);
  }
});

test('Action Required email uses Others label with the existing report field and route', () => {
  const views = readFileSync(join(__dirname, '../../backend/problem_samples/dashboard_views.py'), 'utf8');
  assert.match(views, /\('Others \(Follow Up Required\)', 'customer_service_other', '\/follow-up-required\/other'\)/);
});
