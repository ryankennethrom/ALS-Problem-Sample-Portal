const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const root = path.join(__dirname, '..');
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');

test('ticket editing submits Back to testing directly without email modal', () => {
  const src = read('app/problems/[id]/page.tsx');
  assert.match(src, /values\['current-workflow'\] === 'Back to testing'/);
  assert.match(src, /Before moving this ticket Back to testing:/);
  assert.match(src, /method:'PATCH',\s*headers: changeReasonHeaders\(reason\)/);
  assert.doesNotMatch(src, /BackToTestingEmailModal|testingEmailDraft|finishTestingEmail/);
  assert.doesNotMatch(src, /NA\.EDM needs to be notified/);
});

test('bulk Move Selected performs only one request without email confirmation', () => {
  const src = read('app/to-be-back-to-testing/page.tsx');
  assert.match(src, /body: JSON\.stringify\(\{ problem_ids: ids \}\)/);
  assert.match(src, /headers: changeReasonHeaders\(reason\)/);
  assert.doesNotMatch(src, /BackToTestingEmailModal|pendingSelection|back_to_testing_email/);
});

test('Back to Testing page no longer shows Needs email or Notify actions', () => {
  const src = read('app/back-to-testing/page.tsx');
  assert.match(src, /No notification email is required/);
  assert.doesNotMatch(src, /Needs email|notify NA\.EDM|NA\.EDM notification|back_to_testing_notified_at/);
});

test('no obsolete Back to Testing email component is imported', () => {
  const page = read('app/problems/[id]/page.tsx');
  const queue = read('app/to-be-back-to-testing/page.tsx');
  assert.doesNotMatch(page+queue, /BackToTestingEmailModal/);
  assert.equal(fs.existsSync(path.join(root, 'components/BackToTestingEmailModal.tsx')), false);
});

test('modified TSX files transpile without syntax errors', () => {
  for (const file of ['app/problems/[id]/page.tsx', 'app/to-be-back-to-testing/page.tsx', 'app/back-to-testing/page.tsx']) {
    const result = ts.transpileModule(read(file), {fileName:file,reportDiagnostics:true,compilerOptions:{jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS}});
    assert.deepEqual(result.diagnostics.filter(d=>d.category===ts.DiagnosticCategory.Error).map(d=>d.messageText), [], file);
  }
});
