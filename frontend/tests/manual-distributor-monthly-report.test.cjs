const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const columnPage = fs.readFileSync(path.join(__dirname, '../app/tables/[id]/page.tsx'),'utf8');
const emailPage = fs.readFileSync(path.join(__dirname, '../app/send-system-emails/page.tsx'),'utf8');

test('each enabled Brand CC rule offers manual report after saving', () => {
  assert.match(columnPage, /rule\.send_monthly_reports\s*&&\s*<div/);
  assert.match(columnPage, /Send Monthly Email Now/);
  assert.match(columnPage, /disabled=\{!isSaved\(rule\) \|\| Boolean\(sendingRule\)\}/);
});
test('button queues a report for the persisted rule with a request identifier', () => {
  assert.match(columnPage, /api\('\/system-emails\/queue-now\/'/);
  assert.match(columnPage, /request_id: crypto\.randomUUID\(\)/);
  assert.match(columnPage, /savedRules=\{column\.brand_cc_rules/);
});
test('manual request navigates directly to system email preview', () => {
  assert.match(columnPage, /router\.push\(`\/send-system-emails\?email=/);
  assert.match(emailPage, /URLSearchParams\(window\.location\.search\)\.get\('email'\)/);
  assert.match(emailPage, /void preview\(emailId\)/);
});
test('on-demand reports are identified as month-to-date and never auto-sent', () => {
  assert.match(columnPage, /month-to-date report/);
  assert.match(emailPage, /manual' \? 'Manual month-to-date'/);
  assert.match(emailPage, /I sent the email/);
});
