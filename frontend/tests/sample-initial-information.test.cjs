const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

function loadEmailLib() {
  const source = fs.readFileSync(path.join(__dirname, '../lib/customerEmail.ts'), 'utf8');
  const js = ts.transpileModule(source, {compilerOptions: {target:ts.ScriptTarget.ES2020, module:ts.ModuleKind.CommonJS}}).outputText;
  const exports = {};
  const displayCustomValue = (column, value) => {
    if (value === null || value === undefined || value === '') return '—';
    if (Array.isArray(value)) return value.join(', ') || '—';
    if (column.column_type === 'boolean') return value ? 'Yes' : 'No';
    return String(value);
  };
  vm.runInNewContext(js, {exports, require: (name) => name === '@/lib/problemTables' ? {displayCustomValue} : {} });
  return exports;
}
function field(name, key, position, opts={}) {
  return {name, field_key:key, position, is_system:false, column_type:'text',
    include_in_customer_notification:true, default_value:null, ...opts};
}
const customTemplate = {
  subject_template: 'Ticket {{problem_id}}',
  body_template: 'Initial sample data:\n{{sample_initial_information}}\n\n{{tracking_link}}',
};
const emailContext = (columns, values) => ({ table:{columns,pt_days:30}, values, problemNumber:55, trackingUrl:'https://example.org/ticket/55' });

const bodyFor = (columns,values, template=customTemplate) => {
  return loadEmailLib().buildCustomerEmailContent('client@example.org',emailContext(columns,values),template).body;
};

test('includes tagged non-empty fields, in configured table order', () => {
  const result=bodyFor([
    field('Distributor','dist',2),field('Sample ID','sid',0),field('Brand','brand',1),
  ],{sid:'S-55',brand:'ACME',dist:'West'});
  assert.match(result,/Initial sample data:\nSample ID: S-55\nBrand: ACME\nDistributor: West\n/);
});

test('excludes non-tagged and system columns even if they contain values', () => {
  const result=bodyFor([
    field('Visible','visible',1),field('Private','private',2,{include_in_customer_notification:false}),
    field('Internal','internal',3,{is_system:true}),
  ],{visible:'Yes',private:'Secret text',internal:'System data'});
  assert.match(result,/Visible: Yes/);
  assert.doesNotMatch(result,/Private:|Secret text|Internal:|System data/);
});

test('omits empty, whitespace-only and empty-list fields entirely', () => {
  const result=bodyFor([
    field('Blank','blank',0),field('Whitespace','space',1),field('Empty list','list',2),
    field('Null','null',3),field('Zero','zero',4,{column_type:'number'}),
  ],{blank:'',space:'   ',list:[],null:null,zero:0});
  assert.doesNotMatch(result,/Blank:|Whitespace:|Empty list:|Null:/);
  assert.match(result,/Zero: 0/);
});

test('boolean false remains a filled-in value', () => {
  const result=bodyFor([field('Sample received','received',1,{column_type:'boolean'})],{received:false});
  assert.match(result,/Sample received: No/);
});

test('fixed-value fields use their configured value, blank defaults are omitted', () => {
  const result=bodyFor([
    field('Location','loc',0,{column_type:'fixed',default_value:'Edmonton'}),
    field('Empty Fixed','empty',1,{column_type:'fixed',default_value:''}),
  ],{});
  assert.match(result,/Location: Edmonton/);
  assert.doesNotMatch(result,/Empty Fixed:/);
});

test('empty selection resolves to no field lines, not placeholders or fallback labels', () => {
  const result=bodyFor([field('Sample Count','count',0)],{});
  assert.equal(result,'Initial sample data:\n\nhttps://example.org/ticket/55');
  assert.doesNotMatch(result,/Not provided|undefined|{{sample_initial_information}}/);
});

test('old templates without new token are left backward-compatible', () => {
  const result=bodyFor([field('Distributor','dist',0)],{dist:'ACME'}, {
    subject_template: 'Hello', body_template:'Legacy: {{problem_details}}\n{{tracking_link}}',
  });
  assert.match(result,/Ticket ID: 55/);
  assert.doesNotMatch(result,/{{sample_initial_information}}/);
});

test('builtin default template uses the new placeholder', () => {
  const lib=loadEmailLib();
  assert.match(lib.DEFAULT_CUSTOMER_EMAIL_TEMPLATE.body_template,/{{sample_initial_information}}/);
  assert.doesNotMatch(lib.DEFAULT_CUSTOMER_EMAIL_TEMPLATE.body_template,/{{problem_details}}/);
});
