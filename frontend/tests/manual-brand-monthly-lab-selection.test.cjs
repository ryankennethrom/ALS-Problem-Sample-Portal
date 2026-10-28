const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const file = relative => fs.readFileSync(path.join(__dirname, '..', relative), 'utf8');
const editor = file('app/tables/[id]/page.tsx');
const api = file('../backend/problem_samples/system_email_views.py');
const service = file('../backend/problem_samples/system_email_service.py');

test('Send Monthly Email Now opens lab chooser only when Lab: All is active', () => {
  assert.match(editor, /Send Monthly Email Now/);
  assert.match(editor, /activeLabCode\(\) !== 'ALL'/);
  assert.match(editor, /setLabSelectionRule\(rule\)/);
  assert.match(editor, /api\('\/auth\/labs\/'\)/);
});

test('chooser requires deliberate selection and supports All Labs', () => {
  assert.match(editor, /Send Monthly Email Now — Choose Labs/);
  assert.match(editor, /All Labs \(\{labs\.length\}\)/);
  assert.match(editor, /setSelectedLabIds/);
  assert.match(editor, /!allLabs && !selectedLabIds\.length/);
  assert.match(editor, /allLabs \? \{all_labs:true\} : \{all_labs:false, lab_ids:selectedLabIds\}/);
});

test('selected labs are sent to the queuing API, which validates them', () => {
  assert.match(editor, /\.\.\.\(selection \|\| \{\}\)/);
  assert.match(api, /len\(set\(lab_ids\)\) != len\(lab_ids\)/);
  assert.match(api, /selected_lab = active_lab\(request\)/);
  assert.match(api, /len\(available\) != len\(lab_ids\)/);
});

test('server creates distinct idempotent drafts and does not send mail automatically', () => {
  assert.match(api, /uuid\.uuid5\(request_id, f'monthly-brand-report-lab:/);
  assert.match(api, /with transaction\.atomic\(\)/);
  assert.match(api, /queue_manual_monthly_report\(/);
  assert.match(api, /'email_ids': \[r\['email_id'\] for r in reports\]/);
  assert.match(service, /SystemEmail\.objects\.get_or_create\(/);
});

test('multi-lab reports open the pending queue instead of the first email', () => {
  assert.match(editor, /\(result\.email_ids \|\| \[\]\)\.length > 1/);
  assert.match(editor, /router\.push\('\/send-system-emails'\)/);
  assert.match(editor, /router\.push\(`\/send-system-emails\?email=/);
});
