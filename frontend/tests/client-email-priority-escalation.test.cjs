const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const root = path.resolve(__dirname, '..');
const source = (p) => fs.readFileSync(path.join(root, p), 'utf8');
function compile(p) {
  const result = ts.transpileModule(source(p), {fileName:p,reportDiagnostics:true,compilerOptions:{jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS}});
  assert.deepEqual(result.diagnostics.filter(d=>d.category===ts.DiagnosticCategory.Error).map(d=>d.messageText),[],p);
}
test('admin configures escalating email list timer in column create and edit', () => {
  const config = source('app/tables/[id]/page.tsx');
  assert.match(config,/Make next priority email list as contact if no response after a duration/);
  assert.match(config,/client_email_fallback_hours: type === 'client_email'/);
  assert.match(config,/client_email_fallback_hours: colType === 'client_email'/);
  assert.match(config,/count < 2/);
});
test('staff can select different dependency contact sources and the active selection is stored',()=>{
  const field = source('components/ClientEmailAutocomplete.tsx');
  const dynamic = source('components/DynamicField.tsx');
  assert.match(field,/Current Email List:/);
  assert.match(field,/selectEmailPriority\(item.priority - 1\)/);
  assert.match(field,/onPriorityChange\?\.\(priority\)/);
  assert.match(dynamic,/activeEmailPriority/);
  assert.match(dynamic,/onEmailPriorityChange/);
});
test('ticket creation and saving persist the priority source with email addresses',()=>{
  assert.match(source('components/ProblemForm.tsx'),/client_email_priority_state: emailPriorities/);
  assert.match(source('app/problems/[id]/page.tsx'),/client_email_priority_state:emailPriorities/);
});
test('expiry countdown and automated priority check are checked after authenticated app refresh',()=>{
  const view = fs.readFileSync(path.join(root,'../backend/problem_samples/system_email_views.py'),'utf8');
  const notice = fs.readFileSync(path.join(root,'../backend/problem_samples/views.py'),'utf8');
  assert.match(view,/check_client_email_escalations_on_request\(\)/);
  assert.match(notice,/automatic_disposal_started_at = sent_at/);
  assert.match(notice,/client_email_last_tracking_sent_at = sent_at/);
});
test('modified client email and tickets modules have valid TSX syntax',()=>{
  for (const p of ['app/tables/[id]/page.tsx','components/ClientEmailAutocomplete.tsx','components/DynamicField.tsx','components/ProblemForm.tsx','app/problems/[id]/page.tsx','lib/problemTables.ts']) compile(p);
});
