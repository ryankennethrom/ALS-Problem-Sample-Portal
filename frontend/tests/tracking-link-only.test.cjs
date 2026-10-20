const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

const file = path.join(__dirname, '../lib/customerEmail.ts');
const source = fs.readFileSync(file, 'utf8');
const js = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS }}).outputText;
const exportsObj = {};
const displayCustomValue = (_, v) => v == null || v === '' ? '—' : String(v);
vm.runInNewContext(js, { exports: exportsObj, require: (name) => name === '@/lib/problemTables' ? {displayCustomValue} : {} });
const lib = exportsObj;
const URL = 'https://example.org/track/abc123';
const context = {trackingUrl: URL, problemNumber: 47, table: { columns: [], pt_days: 30}, values:{}};

function bodyFor(template, opts={}) {
  return lib.buildCustomerEmailContent('test@example.org', {...context, ...opts}, template).body;
}

test('tracking_link token expands to precisely the URL without metadata', () => {
  const result = bodyFor({subject_template:'Hello',body_template:'{{tracking_link}}'});
  assert.equal(result, URL);
});

test('tracking_link token does not add a label, details, or customer questions', () => {
  const result = bodyFor({subject_template:'Hello',body_template:'Before\n{{tracking_link}}\nAfter'});
  assert.equal(result, `Before\n${URL}\nAfter`);
  assert.doesNotMatch(result,/TICKET TRACKING LINK|Ticket Tracking page/);
});

test('built-in customer template has only the URL in its tracking-link section', () => {
  const template = lib.DEFAULT_CUSTOMER_EMAIL_TEMPLATE;
  assert.match(template.body_template,/\n\n{{tracking_link}}\n\n/);
  assert.doesNotMatch(template.body_template,/TICKET TRACKING LINK|The Ticket Tracking page also shows|Please review and update this ticket using the secure Ticket Tracking Link/);
  const body = bodyFor(template);
  assert.match(body, new RegExp(`\\n\\n${URL.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\n\\n`));
});

test('legacy templates do not inject Problem Type customer-chat questions into emails', () => {
  const result = bodyFor({subject_template:'Hello',body_template:'Intro\n\n{{tracking_link}}'}, {
    problemTypePrompts: [{column:'Problem Type', choice:'Missing SIF', message:'Please attach the SIF.'}],
  });
  assert.equal(result, `Intro\n\n${URL}`);
  assert.doesNotMatch(result, /Information requested from the customer:|Please attach the SIF\./);
});

test('saved custom templates with legacy problem_type_questions render no request section', () => {
  const result = bodyFor({subject_template:'Hello',body_template:'{{problem_type_questions}}\n\n{{tracking_link}}'}, {
    problemTypePrompts: [{column:'Problem Type', choice:'Missing SIF', message:'Please attach the SIF.'}],
  });
  assert.equal(result, URL);
  assert.doesNotMatch(result, /Information requested from the customer:|Problem Type: Missing SIF|Please attach the SIF\./);
});

test('built-in email no longer contains the customer-questions section', () => {
  const result = bodyFor(lib.DEFAULT_CUSTOMER_EMAIL_TEMPLATE, {
    problemTypePrompts: [{column:'Problem Type', choice:'Missing Sample Information form/Label', message:'Please send an image of the SIF'}],
  });
  assert.doesNotMatch(result, /Information requested from the customer:|Please send an image of the SIF/);
  assert.match(result, /https:\/\/example.org\/track\/abc123/);
});
