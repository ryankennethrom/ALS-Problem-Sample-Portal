/* Creation flow regression tests using the compiled component and simulated hooks.
   Run: NODE_PATH=$(npm root -g) node --test tests/create-ticket-container-fit-table.test.cjs */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

const frontend = join(__dirname, '..');
function compile(filename) {
  const { outputText, diagnostics } = ts.transpileModule(readFileSync(join(frontend, filename), 'utf8'), {
    compilerOptions: { jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS }, reportDiagnostics: true,
  });
  assert.equal(diagnostics.filter(d => d.category === ts.DiagnosticCategory.Error).length, 0);
  return outputText;
}
const formSource = compile('components/ProblemForm.tsx');
const modalSource = compile('components/CreateTicketContainerFitModal.tsx');
const shellSource = readFileSync(join(frontend, 'components/AppShell.tsx'), 'utf8');
const jsx = (type, props) => ({ type, props: props || {} });
function descendants(node) {
  if (node == null || typeof node === 'boolean') return [];
  if (Array.isArray(node)) return node.flatMap(descendants);
  if (typeof node !== 'object') return [node];
  return [node, ...descendants(node.props?.children)];
}
const label = node => descendants(node).filter(n => typeof n === 'string').join('');
const tables = [
  { id: 'alpha', name: 'Lab Tickets', is_default: true, pt_days: 30, columns: [] },
  { id: 'beta', name: 'Customer Service', is_default: false, pt_days: 10, columns: [] },
];
const flush = async () => { for (let i = 0; i < 5; i++) await Promise.resolve(); };
function mount() {
  let hookIndex = 0;
  let selectedTable = null;
  const hooks = [];
  const effects = [];
  const sent = [];
  const redirects = [];
  const apiCalls = [];
  const modal = () => {};
  const r = {
    useState(initial) {
      const index = hookIndex++;
      if (!(index in hooks)) hooks[index] = initial;
      return [hooks[index], v => { hooks[index] = typeof v === 'function' ? v(hooks[index]) : v; }];
    },
    useEffect(fn, deps) {
      const index = hookIndex++;
      const old = effects[index];
      if (!old || !deps || deps.length !== old.length || deps.some((v, i) => v !== old[i])) {
        effects[index] = deps;
        scheduled.push(fn);
      }
    },
    useRef(initial) { const index = hookIndex++; if (!(index in hooks)) hooks[index] = {current:initial}; return hooks[index]; },
    useMemo(fn) { hookIndex++; return fn(); },
  };
  const api = async (url, opts = {}) => {
    apiCalls.push({ url, opts });
    if (url === '/problem-tables/') return tables;
    if (url === '/problem-containers/' && opts.method === 'POST') return { container_id: 'PC-200' };
    if (url === '/problem-containers/') return [{ container_id: 'PC-101' }];
    if (url === '/ticket-creation-timing/start/') return {id:'new-session'};
    if (url === '/problem-samples/prepare-new/') return { id: 'prepared', problem_number: 17, tracking_url: 'https://example.com/track' };
    if (url === '/problem-samples/create-prepared/') return {id:'created-ticket'};
    throw Error('Unexpected API ' + url);
  };
  const router = { replace(url) { redirects.push(url); selectedTable = new URL(url, 'http://localhost').searchParams.get('table'); }, push(url) { sent.push(url); } };
  let scheduled = [];
  const mocks = {
    react: r,
    'react/jsx-runtime': { jsx, jsxs: jsx, Fragment: 'fragment' },
    'next/navigation': { useRouter: () => router, useSearchParams: () => ({ get: key => key === 'table' ? selectedTable : null }) },
    '@/lib/api': { api },
    '@/lib/problemTables': { applyIntercolumnRules: (_table, values) => values, initialValue: () => '', resolveProblemTypeMask: () => ({}) },
    '@/lib/customerEmail': { findCustomerEmails: () => [], prepareCustomerEmail: async () => ({ content: null }) },
    '@/components/DynamicField': () => {},
    '@/components/CustomerEmailModal': () => {},
    '@/components/CameraCapture': () => {},
    '@/components/CreateTicketContainerFitModal': { default: modal },
  };
  const sandbox = { exports: {}, module: { exports: {} }, FormData, require(name) { assert.ok(mocks[name], 'Unexpected import: ' + name); return mocks[name]; } };
  vm.runInNewContext(formSource, sandbox);
  const Component = sandbox.exports.default;
  let tree;
  const render = () => { hookIndex = 0; scheduled = []; tree = Component(); for (const fn of scheduled) fn(); return tree; };
  const find = predicate => descendants(tree).find(n => n && typeof n === 'object' && predicate(n));
  const clickButton = text => {
    const node = find(n => n.type === 'button' && label(n) === text);
    assert.ok(node, 'Missing button: ' + text);
    return node.props.onClick();
  };
  const selectContainer = value => {
    const node = find(n => n.type === 'input' && n.props.id === 'container-id');
    assert.ok(node, 'Missing existing Container ID input');
    node.props.onChange({ target: { value } });
  };
  const submit = () => {
    const form = find(n => n.type === 'form');
    assert.ok(form);
    return form.props.onSubmit({ preventDefault() {} });
  };
  const fitModal = () => find(n => n.type === modal);
  render();
  return { render, find, clickButton, selectContainer, submit, fitModal, apiCalls, redirects, sent };
}

test('Create Ticket offers a dropdown listing the current ticket tables', async () => {
  const app = mount(); await flush(); app.render();
  const select = app.find(n => n.type === 'select' && n.props.id === 'create-ticket-table');
  assert.ok(select);
  assert.equal(select.props.value, 'alpha');
  assert.deepEqual(descendants(select).filter(n => n.type === 'option').map(n => n.props.value), ['alpha', 'beta']);
  select.props.onChange({ target: { value: 'beta' } });
  assert.equal(app.redirects.at(-1), '/problems/new?table=beta');
  app.render();
  assert.equal(app.find(n => n.type === 'select' && n.props.id === 'create-ticket-table').props.value, 'beta');
});

test('Existing container cannot prepare a ticket until fit confirmation', async () => {
  const app = mount(); await flush(); app.render();
  app.selectContainer('PC-101'); app.render();
  await app.submit(); app.render();
  assert.ok(app.fitModal(), 'Physical fit popup should open');
  assert.equal(app.apiCalls.filter(c => c.url === '/problem-samples/prepare-new/').length, 0);
  app.fitModal().props.onFits(); await flush(); app.render();
  const preparations = app.apiCalls.filter(c => c.url === '/problem-samples/prepare-new/');
  assert.equal(preparations.length, 1);
  assert.equal(JSON.parse(preparations[0].opts.body).container_code, 'PC-101');
});

test('Other container and new container options preserve valid choices', async () => {
  const app = mount(); await flush(); app.render();
  app.selectContainer('PC-101'); app.render(); await app.submit(); app.render();
  app.fitModal().props.onDifferent(); app.render();
  assert.equal(app.find(n => n.type === 'input' && n.props.id === 'container-id').props.value, '');
  app.selectContainer('PC-102'); app.render(); await app.submit(); app.render();
  assert.equal(app.fitModal().props.containerId, 'PC-102');
  app.fitModal().props.onCreateNew(); app.render();
  assert.equal(app.fitModal(), undefined);
  assert.ok(app.find(n => n.type === 'button' && label(n) === 'Create New Container'));
  assert.equal(app.apiCalls.filter(c => c.url === '/problem-samples/prepare-new/').length, 0);
});

test('Physical fit confirmation provides exactly three visible actions', () => {
  const mocks = { react: { useEffect() {}, useRef: v => ({ current: v }) }, 'react/jsx-runtime': { jsx, jsxs: jsx, Fragment: 'fragment' } };
  const sandbox = { exports: {}, module: { exports: {} }, require(name) { return mocks[name]; } };
  vm.runInNewContext(modalSource, sandbox);
  const tree = sandbox.exports.default({ containerId: 'PC-104', onFits() {}, onDifferent() {}, onCreateNew() {}, onDismiss() {} });
  const buttons = descendants(tree).filter(n => n.type === 'button');
  assert.deepEqual(buttons.map(label), [ 'Fits in container PC-104', 'Use a different existing container', 'Create a new container' ]);
  assert.match(label(descendants(tree).find(n => n.type === 'p' && n.props.id === 'create-container-fit-description')), /Please check container PC-104 first/);
});

test('Sidebar Create Ticket opens the form with the dropdown directly', () => {
  assert.match(shellSource, /<Link href="\/problems\/new" className=\{`side-link/);
});


test('Creation timing starts once on Create Ticket click and completes with email confirmation', async () => {
  const app = mount(); await flush(); app.render();
  app.selectContainer('PC-101'); app.render();
  app.clickButton('Create Ticket'); await flush();
  assert.equal(app.apiCalls.filter(call => call.url === '/ticket-creation-timing/start/').length, 1);
  await app.submit(); app.render();
  app.fitModal().props.onFits(); await flush(); app.render();
  const customerModal = app.find(n => n && typeof n.props?.onDidNotSend === 'function');
  assert.ok(customerModal, 'Prepared ticket must require final email confirmation');
  assert.equal(customerModal.props.autoStart, true, 'The fit-check confirmation must open webmail without a second Send Email step');
  await customerModal.props.onDidNotSend('Email address unavailable');
  const completion = app.apiCalls.find(call => call.url === '/problem-samples/create-prepared/');
  assert.ok(completion, 'Only confirmation should create a real ticket');
  assert.equal(completion.opts.body.get('creation_timing_id'), 'new-session');
  assert.equal(completion.opts.body.get('sent'), 'false');
  assert.equal(app.apiCalls.filter(call => call.url === '/ticket-creation-timing/start/').length, 1);
});


test('new-container ticket creation also starts the tracking email immediately after preparation', async () => {
  const app = mount(); await flush(); app.render();
  const radio = app.find(n => n.type === 'input' && n.props.type === 'radio' && n.props.name === 'container-mode' && !n.props.checked);
  assert.ok(radio);
  radio.props.onChange(); app.render();
  app.clickButton('Create New Container'); await flush(); app.render();
  await app.submit(); await flush(); app.render();
  assert.equal(app.fitModal(), undefined, 'new containers do not need a fit-check prompt');
  const customerModal = app.find(n => n && typeof n.props?.onDidNotSend === 'function');
  assert.ok(customerModal);
  assert.equal(customerModal.props.autoStart, true);
});
