/* Regression tests for the ticket-page container selection dialog.
   Run: cd frontend && npm install && node --test tests/container-fit-confirmation.test.cjs */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

const source = readFileSync(join(__dirname, '..', 'components', 'ReopenContainerModal.tsx'), 'utf8');
const { outputText, diagnostics } = ts.transpileModule(source, {
  compilerOptions: { jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS },
  reportDiagnostics: true,
});
assert.equal((diagnostics || []).filter(item => item.category === ts.DiagnosticCategory.Error).length, 0);

function element(type, props) { return { type, props: props || {} }; }
function descendants(node) {
  if (node === undefined || node === null || typeof node === 'boolean') return [];
  if (Array.isArray(node)) return node.flatMap(descendants);
  if (typeof node !== 'object') return [node];
  return [node, ...descendants(node.props?.children)];
}
function labelFor(node) { return descendants(node).filter(piece => typeof piece === 'string').join(''); }

function mount(overrides = {}) {
  let hookIndex = 0;
  const hooks = [];
  const confirmations = [];
  const cancellations = [];
  const react = {
    useState(initial) {
      const index = hookIndex++;
      if (!(index in hooks)) hooks[index] = initial;
      return [hooks[index], next => { hooks[index] = typeof next === 'function' ? next(hooks[index]) : next; }];
    },
    useRef(initial) {
      const index = hookIndex++;
      if (!(index in hooks)) hooks[index] = { current: initial };
      return hooks[index];
    },
    // The tested transitions are driven directly by event handlers; no effects are required.
    useEffect() {},
  };
  const sandbox = {
    exports: {}, module: { exports: {} },
    require(name) {
      if (name === 'react') return react;
      if (name === 'react/jsx-runtime') return { jsx: element, jsxs: element, Fragment: 'fragment' };
      throw new Error(`Unexpected module: ${name}`);
    },
  };
  vm.runInNewContext(outputText, sandbox, { filename: 'ReopenContainerModal.js' });
  const Modal = sandbox.exports.default;
  const props = {
    purpose: 'change', ticketNumber: 17, previousWorkflow: 'CS Follow-Up',
    nextWorkflow: 'Waiting for Customer Response', isInDumpingContainer: false,
    onConfirm: value => confirmations.push({ ...value }),
    onCancel: () => cancellations.push(true), ...overrides,
  };
  let tree;
  const render = () => { hookIndex = 0; tree = Modal(props); return tree; };
  const find = predicate => descendants(tree).find(node => node && typeof node === 'object' && predicate(node));
  const click = text => {
    const button = find(node => node.type === 'button' && labelFor(node) === text);
    assert.ok(button, `Button not found: ${text}`);
    button.props.onClick();
  };
  const typeId = value => {
    const input = find(node => node.type === 'input' && node.props.id === 'reopen-existing-container');
    assert.ok(input, 'Container field missing');
    input.props.onChange({ target: { value } });
  };
  const continueForm = () => {
    const form = find(node => node.type === 'form');
    form.props.onSubmit({ preventDefault() {} });
  };
  render();
  return { render, find, click, typeId, continueForm, confirmations, cancellations };
}

test('Existing container requires an explicit physical fit confirmation', () => {
  const app = mount();
  app.typeId('  PC-000123  ');
  app.render();
  app.continueForm();
  assert.equal(app.confirmations.length, 0, 'Continue must not assign an unchecked container');
  app.render();
  assert.match(labelFor(app.find(node => node.type === 'p' && node.props.id === 'reopen-container-description')), /Please check container PC-000123 first/);
  assert.equal(descendants(app.find(node => node.type === 'form')).filter(node => node && node.type === 'button').length, 3, 'The fit prompt must offer exactly three choices');
  app.click('Fits in container PC-000123');
  assert.deepEqual(app.confirmations, [{ mode: 'existing', containerId: 'PC-000123' }]);
});

test('Different existing container clears ID and requires another fit check', () => {
  const app = mount();
  app.typeId('PC-000123'); app.render(); app.continueForm(); app.render();
  app.click('Use a different existing container'); app.render();
  assert.equal(app.find(node => node.type === 'input' && node.props.id === 'reopen-existing-container').props.value, '');
  app.typeId('PC-000124'); app.render(); app.continueForm(); app.render();
  assert.equal(app.confirmations.length, 0);
  app.click('Fits in container PC-000124');
  assert.deepEqual(app.confirmations, [{ mode: 'existing', containerId: 'PC-000124' }]);
});

test('Can switch directly from fit prompt to creating a new container', () => {
  const app = mount();
  app.typeId('PC-000123'); app.render(); app.continueForm(); app.render();
  app.click('Create a new container');
  assert.deepEqual(app.confirmations, [{ mode: 'new', containerId: '' }]);
});

test('Selecting new container directly does not require fit confirmation', () => {
  const app = mount();
  const radio = app.find(node => node.type === 'input' && node.props.type === 'radio' && node.props.checked === false);
  assert.ok(radio);
  radio.props.onChange(); app.render(); app.continueForm();
  assert.deepEqual(app.confirmations, [{ mode: 'new', containerId: '' }]);
});

test('Blank existing Container ID cannot advance or assign', () => {
  const app = mount(); app.continueForm(); app.render();
  assert.equal(app.confirmations.length, 0);
  assert.equal(app.find(node => node.type === 'input' && node.props.id === 'reopen-existing-container').props['aria-invalid'], true);
  assert.equal(app.find(node => node.type === 'h2').props.children, 'Change container for ticket #17');
});

test('Reopening a terminal workflow uses the same fit-confirmation step', () => {
  const app = mount({ purpose: 'reopen', previousWorkflow: 'Disposed', nextWorkflow: 'CS Follow-Up' });
  app.typeId('PC-000777'); app.render(); app.continueForm(); app.render();
  assert.equal(app.confirmations.length, 0);
  app.click('Fits in container PC-000777');
  assert.deepEqual(app.confirmations, [{ mode: 'existing', containerId: 'PC-000777' }]);
});

test('Dumping-container safeguard blocks container reassignment', () => {
  const app = mount({ isInDumpingContainer: true });
  app.typeId('PC-000123'); app.render(); app.continueForm(); app.render();
  assert.equal(app.confirmations.length, 0);
  assert.equal(app.find(node => node.type === 'fieldset').props.disabled, true);
});
