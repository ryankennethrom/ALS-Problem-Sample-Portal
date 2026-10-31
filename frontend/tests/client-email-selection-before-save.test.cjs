const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const vm = require('node:vm');
const base = path.join(__dirname, '..');
const read = p => fs.readFileSync(path.join(base, p), 'utf8');
function compile(p) {
  const output = ts.transpileModule(read(p), {
    fileName: p, reportDiagnostics: true,
    compilerOptions: { jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS },
  });
  assert.deepEqual(output.diagnostics.filter(d => d.category === ts.DiagnosticCategory.Error).map(d => d.messageText), [], p);
  return output.outputText;
}
const runtime = {jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props})};
const helper = {};
vm.runInNewContext(compile('lib/clientEmailSelection.ts'), {exports:helper,require() {throw Error('Unexpected dependency')}});
const resolve = helper.resolveClientEmailSelection;

test('Keep Selected replaces list with checked emails, including previously uncommitted suggestions', () => {
  assert.deepEqual(Array.from(resolve(['old@example.com'], ['old@example.com','new@example.com'], new Set(['new@example.com']), 'keep')), ['new@example.com']);
});
test('Delete Selected removes checked emails while preserving unselected emails', () => {
  assert.deepEqual(Array.from(resolve(['one@example.com','two@example.com'], ['one@example.com','two@example.com'],new Set(['one@example.com']), 'delete')), ['two@example.com']);
});
test('Selections match addresses case-insensitively and are not duplicated', () => {
  assert.deepEqual(Array.from(resolve(['Old@Example.COM'], ['Old@Example.COM','old@example.com'], new Set(['old@example.com']), 'keep')), ['Old@Example.COM']);
  assert.deepEqual(Array.from(resolve(['Old@Example.COM'], [], new Set(['old@example.com']), 'delete')), []);
});
test('No selected emails is a no-op for either action', () => {
  const emails = ['one@example.com'];
  assert.deepEqual(Array.from(resolve(emails, [], new Set(), 'keep')), emails);
  assert.deepEqual(Array.from(resolve(emails, [], new Set(), 'delete')), emails);
});
test('The prompt gives three explicit decisions, and Cancel does not mutate selections', () => {
  const mocks = {
    react: { useEffect() {}, useRef: value => ({current:value}) },
    'react/jsx-runtime': {...runtime,Fragment:'fragment'},
  };
  const exports = {};
  vm.runInNewContext(compile('components/ClientEmailSelectionPrompt.tsx'), {exports,require(name) {assert.ok(mocks[name], name);return mocks[name];}});
  const actions = [];
  const tree = exports.default({selectedCount:2,fieldCount:1,onKeep:()=>actions.push('keep'),onDelete:()=>actions.push('delete'),onCancel:()=>actions.push('cancel')});
  const flattened = node => (!node || typeof node !== 'object') ? [] : [node, ...([node.props?.children].flat().flatMap(flattened))];
  const buttons = flattened(tree).filter(item=>item.type==='button');
  assert.deepEqual(buttons.map(item => item.props.children), ['Keep Selected & Continue','Delete Selected & Continue','Cancel']);
  buttons[2].props.onClick();
  assert.deepEqual(actions, ['cancel']);
  buttons[0].props.onClick(); buttons[1].props.onClick();
  assert.deepEqual(actions, ['cancel','keep','delete']);
});
test('Client Email editor exposes the selection count and resolution actions to ticket forms', () => {
  const source = read('components/ClientEmailAutocomplete.tsx');
  const dynamic = read('components/DynamicField.tsx');
  assert.match(source, /forwardRef<ClientEmailSelectionHandle, ClientEmailAutocompleteProps>/);
  assert.match(source, /pendingCount: \(\) => selected\.size/);
  assert.match(source, /resolve: resolveSelected/);
  assert.match(source, /setSelected\(new Set\(\)\)/);
  assert.match(dynamic, /ref=\{clientEmailRef\}/);
});
test('Create Ticket blocks the prepare-new endpoint until client emails are resolved', () => {
  const source = read('components/ProblemForm.tsx');
  assert.match(source, /const pending = unresolvedClientEmails\(\);\s*if \(pending\.selectedCount\) \{\s*setClientEmailPrompt\(pending\);\s*return;/);
  assert.match(source, /onKeep=\{\(\) => applyEmailDecision\('keep'\)\}/);
  assert.match(source, /onDelete=\{\(\) => applyEmailDecision\('delete'\)\}/);
  assert.match(source, /onCancel=\{\(\) => setClientEmailPrompt\(null\)\}/);
  assert.match(source, /void continueSubmit\(resolvedValues\)/);
  assert.match(source, /custom_values: values, image_count:/);
  assert.match(source, /findCustomerEmails\(table, values\)/);
});
test('Save Changes gates existing-ticket PATCH and resumes with the resolved email values', () => {
  const source = read('app/problems/[id]/page.tsx');
  assert.match(source, /if \(!clientEmailsResolved\) \{\s*const pending = unresolvedClientEmails\(\);\s*if \(pending\.selectedCount\) \{\s*setClientEmailPrompt\(pending\);\s*return;/);
  assert.match(source, /void saveCustom\(resolvedValues, true\)/);
  assert.match(source, /body:JSON\.stringify\(\{custom_values:values, \.\.\.containerSelection\}\)/);
  assert.match(source, /onClick=\{\(\) => void saveCustom\(\)\}>Save Changes/);
  assert.match(source, /onCancel=\{\(\) => setClientEmailPrompt\(null\)\}/);
});
test('All modified frontend TSX and TS modules transpile without syntax errors', () => {
  for (const file of ['lib/clientEmailSelection.ts','components/ClientEmailAutocomplete.tsx','components/ClientEmailSelectionPrompt.tsx','components/DynamicField.tsx','components/ProblemForm.tsx','app/problems/[id]/page.tsx']) {
    assert.ok(compile(file).length > 0);
  }
});
