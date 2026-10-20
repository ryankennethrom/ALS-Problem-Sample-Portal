const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

function loadLibrary(environment = {}) {
  const source = fs.readFileSync(path.join(__dirname, '../lib/customerEmail.ts'), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: {
    target: ts.ScriptTarget.ES2020,
    module: ts.ModuleKind.CommonJS,
  }}).outputText;
  const exports = {};
  vm.runInNewContext(code, {
    exports,
    require: () => ({}),
    URL,
    CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options.detail; } },
    ...environment,
  });
  return exports;
}

function message(to, subject, body, cc = []) {
  return { to, cc, subject, body };
}

function recordedLauncher() {
  const links = [];
  const events = [];
  const document = {
    createElement: () => ({href:'',style:{},click(){links.push(this.href);},remove(){}}),
    body: {appendChild(){}},
  };
  return {links,events,document,window:{dispatchEvent:event=>events.push(event)}};
}

test('short email uses mailto including To, Cc, Subject, Body', () => {
  const mod = loadLibrary();
  const mailto = mod.mailtoForCustomerEmail(message(
    ['one@example.com','two@example.com'], 'Case #31',
    'Hi there\nTracking: https://example.org/?x=1&y=2', ['cc@example.com']));
  const draft = mod.outlookWebDraftForMailto(mailto);
  assert.equal(draft.link, mailto);
  assert.equal(new URL(draft.link).protocol, 'mailto:');
  assert.equal(new URL(draft.link).searchParams.get('subject'), 'Case #31');
  assert.equal(new URL(draft.link).searchParams.get('cc'), 'cc@example.com');
  assert.equal(new URL(draft.link).searchParams.get('body'), 'Hi there\nTracking: https://example.org/?x=1&y=2');
  assert.deepEqual(Array.from(draft.to), ['one@example.com','two@example.com']);
  assert.equal(draft.manualBody, false);
});

test('short messages with Distributor CC launch immediately using registered mailto handler', () => {
  const env = recordedLauncher();
  const mod = loadLibrary(env);
  const full = mod.mailtoForCustomerEmail(message(['customer@example.com'], 'Status', 'Hello', ['distributor@example.org']));
  mod.invokeCustomerEmail(full);
  assert.deepEqual(env.links, [full]);
  assert.equal(env.events.length,1);
  assert.equal(env.events[0].detail.cc[0], 'distributor@example.org');
  assert.equal(env.events[0].type,mod.OUTLOOK_EMAIL_FALLBACK_EVENT);
});

test('short messages without CC still launch immediately', () => {
  const env = recordedLauncher();
  const mod = loadLibrary(env);
  const full = mod.mailtoForCustomerEmail(message(['customer@example.com'], 'Status', 'Hello'));
  mod.invokeCustomerEmail(full);
  assert.deepEqual(env.links,[full]);
  assert.equal(env.events.length, 1);
});

test('oversized email is not opened before manual review; full body remains available', () => {
  const env = recordedLauncher();
  const mod = loadLibrary(env);
  const body = 'ABC and a link: https://example.com/?id=2\n'.repeat(160);
  const full = mod.mailtoForCustomerEmail(message(['to@example.com'],'Monthly report',body,['cc@example.com']));
  mod.invokeCustomerEmail(full);
  assert.equal(env.links.length, 0);
  assert.equal(env.events.length, 1);
  const draft = env.events[0].detail;
  assert.equal(draft.body, body);
  assert.equal(draft.mailtoLink,full);
  assert.equal(draft.manualBody,true);
  assert.equal(draft.headersPrefilled,true);
  assert.ok(draft.link.length <= mod.OUTLOOK_WEB_COMPOSE_URL_LIMIT);
  assert.equal(new URL(draft.link).searchParams.get('body'),null);
  assert.equal(new URL(draft.link).searchParams.get('subject'),'Monthly report');
  assert.equal(new URL(draft.link).searchParams.get('cc'),'cc@example.com');
});

test('oversized subject drops subject from launched URL but preserves the original', () => {
  const mod = loadLibrary();
  const subject = 'Test' + '!'.repeat(2300);
  const draft = mod.outlookWebDraftForMailto(mod.mailtoForCustomerEmail(message(['to@example.com'],subject,'Important')));
  assert.equal(draft.headersPrefilled,false);
  assert.equal(draft.subject,subject);
  assert.ok(draft.link.length <= 1500);
  assert.equal(new URL(draft.link).searchParams.get('subject'),null);
});

test('very long CC list falls back to a safe mailto, retaining all recipients in preview', () => {
  const mod = loadLibrary();
  const cc = Array.from({length:120}, (_,i) => `manager${i}@example.org`);
  const draft = mod.outlookWebDraftForMailto(mod.mailtoForCustomerEmail(message(['to@example.com'],'Subject','Text',cc)));
  assert.equal(draft.cc.length,120);
  assert.equal(draft.manualBody,true);
  assert.equal(draft.headersPrefilled,false);
  assert.ok(draft.link.length <= 1500);
  assert.match(draft.link,/^mailto:/);
});

test('non-ASCII content percent-encodes and counts toward length cap', () => {
  const mod = loadLibrary();
  const body = '🎉'.repeat(150);
  const draft = mod.outlookWebDraftForMailto(mod.mailtoForCustomerEmail(message(['to@example.com'],'Symbols #&%',body)));
  assert.equal(draft.manualBody,true);
  assert.equal(draft.body,body);
  assert.ok(draft.fullLinkLength>body.length);
});

test('actual Distributor rule matching is retained in mailto Cc with de-duplication', () => {
  const mod = loadLibrary();
  const table = {columns:[{field_key:'distributor',column_type:'distributor',distributor_cc_rules:[
    {match_type:'wildcard',pattern:'Brandt*',cc_emails:['accounting@example.org','customer@example.org']},
    {match_type:'contains',pattern:'brandt',cc_emails:['ACCOUNTING@example.org','manager@example.org']},
  ]}]};
  const cc = mod.findDistributorCCRecipients(table,{distributor:'Brandt Equipment'},['customer@example.org']);
  assert.deepEqual(Array.from(cc), ['accounting@example.org','manager@example.org']);
  const draft = mod.outlookWebDraftForMailto(mod.mailtoForCustomerEmail(message(['customer@example.org'],'Ticket update','Body',cc)));
  assert.equal(new URL(draft.link).searchParams.get('cc'),'accounting@example.org,manager@example.org');
});

test('fallback UI launches mailto directly and requires no extra Cc confirmation checkbox', () => {
  const source = fs.readFileSync(path.join(__dirname,'../components/OutlookEmailManualCompose.tsx'),'utf8');
  assert.match(source,/href={draft.link}/);
  assert.match(source,/browser.*handler/);
  assert.match(source,/Copy Cc recipients/);
  assert.doesNotMatch(source,/ccAcknowledged/);
  assert.doesNotMatch(source,/target="_blank"[^>]*href={draft.link}/);
});

test('invalid non-mailto input does not open a draft', () => {
  const mod=loadLibrary();
  assert.throws(()=>mod.outlookWebDraftForMailto('https://outlook.office.com/mail/'));
});
