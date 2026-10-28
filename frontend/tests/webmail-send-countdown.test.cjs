const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

const root = path.join(__dirname,'..');
const source = filename => fs.readFileSync(path.join(root,filename), 'utf8');
const compile = filename => {
  const result = ts.transpileModule(source(filename), {compilerOptions: {
    jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS,
  },reportDiagnostics:true});
  assert.equal(result.diagnostics.filter(x=>x.category===ts.DiagnosticCategory.Error).length,0);
  return result.outputText;
};

function mount(filename, props) {
  let hookIndex = 0;
  const hooks = [], effects = [], intervals = new Map();
  let nextInterval = 0, now = 1000000;
  const attempts = [];
  const callbacks = [];
  const react = {
    useState(initial) { const index=hookIndex++; if (!(index in hooks)) hooks[index]=initial;
      return [hooks[index], value => {hooks[index]=typeof value==='function' ? value(hooks[index]) : value;}]; },
    useRef(initial) { const index=hookIndex++; if (!(index in hooks)) hooks[index]={current:initial}; return hooks[index]; },
    useEffect(fn, deps) { const index=hookIndex++; const old=effects[index];
      if (!old || deps.some((value,i)=>value!==old.deps[i])) {
        if(old?.cleanup) old.cleanup();
        callbacks.push(()=>{effects[index]={deps, cleanup:fn()};});
      }
    },
  };
  const jsx=(type, props={})=>typeof type==='function' ? type(props) : ({type,props});
  const mockWindow={setInterval(fn){const id=++nextInterval;intervals.set(id,fn);return id;},clearInterval(id){intervals.delete(id);}};
  const email = {invokeCustomerEmail(link){attempts.push(link);},mailtoForCustomerEmail(message){return `mailto:${message.to.join(',')}?subject=${encodeURIComponent(message.subject)}`;}};
  const modules = {
    react, 'react/jsx-runtime':{jsx,jsxs:jsx,Fragment:'fragment'},
    '@/lib/customerEmail':email,
    '@/lib/api':{api:async()=>({email:'lab@example.org'})},
    '@/lib/rackRemovalReminder':{rackRemovalReminder:()=>''},
  };
  const sandbox = {
    exports:{}, Date:class extends Date {static now(){return now;}},window:mockWindow,
    require(name){assert.ok(modules[name],`unexpected import: ${name}`);return modules[name];},
  };
  function load(filename){ const module={...sandbox,exports:{}};vm.runInNewContext(compile(filename),module,{filename});return module.exports; }
  modules['@/components/useWebmailSendCountdown'] = load('components/useWebmailSendCountdown.tsx');
  const Component = load(filename).default;
  let tree;
  function render() {hookIndex=0;tree=Component(props);while(callbacks.length) callbacks.shift()();return tree;}
  function descend(node) {if(node==null||typeof node==='boolean')return [];
    if(Array.isArray(node))return node.flatMap(descend);
    if(typeof node!=='object')return [node];
    return [node,...descend(node.props?.children)];}
  function text(node){return descend(node).filter(x=>typeof x==='string').join('');}
  function buttons(){return descend(tree).filter(node=>node?.type==='button').map(node=>({name:text(node),...node.props}));}
  function click(name){const button=buttons().find(b=>b.name===name);assert.ok(button,`Missing ${name}; found ${buttons().map(b=>b.name).join('; ')}`);return button.onClick();}
  function advance(ms){now+=ms;for(const fn of [...intervals.values()])fn();render();}
  render();
  return {render,click,advance,buttons,attempts,text:()=>text(tree)};
}
const content={to:['customer@example.org'],cc:[],subject:'Test',body:'Hello'};
function verifyFlow(mountArgs, send='Send Email') {
 const harness=mount(...mountArgs);
 assert.ok(harness.buttons().some(b=>b.name===send));
 assert.equal(harness.buttons().some(b=>b.name==='I sent the email'),false);
 harness.click(send);
 assert.equal(harness.attempts.length,1);
 harness.render();
 assert.match(harness.text(),/Opening Web Mail.*5 seconds/);
 assert.equal(harness.buttons().some(b=>b.name==='I sent the email'),false);
 harness.click('Cancel'); // each caller defines a valid cancellation callback
 harness.advance(5000);
 assert.equal(harness.buttons().filter(b=>['I sent the email',"I didn't send the email",'Cancel'].includes(b.name)).length,3);
 assert.equal(harness.buttons().some(b=>b.name===send),false);
 assert.equal(harness.attempts.length,1);
 return harness;
}

test('tracking email opens once and waits five seconds for three confirmation buttons', () => {
 const actions=[];
 const harness=verifyFlow(['components/CustomerEmailModal.tsx',{
  content,onSent:()=>actions.push('sent'),onDidNotSend:r=>actions.push(r),onCancel:()=>actions.push('cancel'),requireNotSentReason:false,
 }]);
 harness.click("I didn't send the email");
 assert.deepEqual(actions,['cancel','User chose not to send the tracking-link email during ticket creation.']);
});

test('tracking email with a required reason only records not-sent after reason confirmation', () => {
 const actions=[];
 const harness=mount('components/CustomerEmailModal.tsx',{
  content,onSent:()=>actions.push('sent'),onDidNotSend:r=>actions.push(r),onCancel:()=>actions.push('cancel'),
 });
 harness.click('Send Email');harness.render();harness.advance(5000);
 harness.click("I didn't send the email");harness.render();
 assert.deepEqual(actions,[]);
 harness.click('Confirm email not sent');
 assert.deepEqual(actions,['Email unknown']);
});

test('Back to Testing shares the countdown and retains not-sent reason', async () => {
 const confirmations=[];
 const h=mount('components/BackToTestingEmailModal.tsx',{
  batchSamples:[{problemNumber:13,tableName:'ALS',containerId:'EDM PC-00001',trackingNumber:'123'}],
  onConfirm:(...args)=>confirmations.push(args),onCancel:()=>{},busy:false,error:'',
 });
 await Promise.resolve(); await Promise.resolve();
 h.render();
 h.click('Send Email');h.render();
 assert.equal(h.attempts.length,1);
 assert.match(h.text(),/Opening Web Mail.*5 seconds/);
 assert.equal(h.buttons().some(b=>b.name==='I sent the email'),false);
 h.advance(5000);
 h.click("I didn't send the email");h.render();
 assert.equal(confirmations.length,0);
 h.click('Confirm email not sent');
 assert.equal(confirmations.length,1);
 assert.equal(confirmations[0][0],false);
 assert.equal(confirmations[0][3],'Email unknown');
});

test('general customer email shows no sent/not-sent buttons until countdown ends', () => {
 const events=[];
 const h=verifyFlow(['components/GeneralCustomerEmailModal.tsx',{
  recipients:['customer@example.org'],problemNumber:21,
  onSent:m=>events.push(m),onCancel:()=>events.push('cancel'),
 }]);
 h.click('I sent the email');
 assert.equal(events.length,2);assert.deepEqual(Array.from(events[1].cc),[]);
});

test('mention email auto-opens once, then requires explicit confirmation to save follow-up', () => {
 let sent=0;
 const h=mount('components/MentionEmailModal.tsx',{
  emails:[{email:'lab@example.org',recipients:['lab@example.org'],subject:'Mention',body:'Body'}],
  onComplete:()=>{sent++;},onCancel:()=>{},
 });
 assert.equal(h.attempts.length,1);
 h.render();
 assert.match(h.text(),/Opening Web Mail.*5 seconds/);
 assert.equal(h.buttons().some(b=>b.name==='Send Email'),false);
 assert.equal(sent,0);
 h.advance(5000);
 assert.equal(sent,0);
 h.click('I sent the email');assert.equal(sent,1);
});

test('customer history reply opens automatically without an extra Send Email button', () => {
 let saved=0;
 const h=mount('components/CustomerHistoryReplyEmailModal.tsx',{
  email:{...content,direct_url:'',customer_message:''},onSent:()=>{saved++;},onCancel:()=>{},
 });
 assert.equal(h.attempts.length,1);
 h.render();
 assert.match(h.text(),/Opening Web Mail.*5 seconds/);
 assert.equal(h.buttons().some(b=>b.name==='Send Email'),false);
 assert.equal(saved,0);
 h.advance(5000);
 assert.equal(saved,0);
 h.click('I sent the email');assert.equal(saved,1);
});

test('system emails keep unsent reports pending and gate confirm-sent on countdown',()=>{
 const code=source('app/send-system-emails/page.tsx');
 assert.match(code,/if \(!selected \|\| seconds !== 0\) return;/);
 assert.match(code,/seconds === 0.*confirmSent/);
 assert.match(code,/seconds === 0.*I didn't send the email/);
 assert.match(code,/attemptedDraftId\.current = selected\.id/);
 assert.doesNotMatch(code,/onClick=\{openMailApp\}.*Send Email/);
});

test('Action Required emails use Send Email before the same countdown',()=>{
 const code=source('components/ActionRequiredEmailModal.tsx');
 assert.match(code,/start\(\{ to: draft\.recipients/);
 assert.match(code,/seconds === 0.*I sent the email/);
 assert.match(code,/seconds === 0.*I didn't send the email/);
});

test('history reply no longer launches mail before the dialog Send Email click',()=>{
 const code=source('app/problems/[id]/page.tsx');
 assert.doesNotMatch(code,/const launchedAt = Date\.now\(\)/);
 assert.doesNotMatch(code,/invokeCustomerEmail\(mailtoForCustomerEmail/);
});

test('ticket-creation tracking email automatically requests webmail and starts countdown, without Send Email step', () => {
 const actions=[];
 const h=mount('components/CustomerEmailModal.tsx', {
  content, autoStart:true, requireNotSentReason:false,
  onSent:()=>actions.push('sent'), onDidNotSend:()=>actions.push('not-sent'), onCancel:()=>actions.push('cancel'),
 });
 assert.equal(h.attempts.length,1,'webmail should be requested automatically on modal mount');
 h.render();
 assert.match(h.text(),/Opening Web Mail.*5 seconds/);
 assert.equal(h.buttons().some(b=>b.name==='Send Email'),false);
 assert.equal(h.buttons().some(b=>b.name==='I sent the email'),false);
 assert.equal(h.buttons().some(b=>b.name==="I didn't send the email"),false);
 assert.ok(h.buttons().some(b=>b.name==='Review email details'));
 h.render();
 assert.equal(h.attempts.length,1,'rerenders must not launch another draft');
 h.advance(5000);
 assert.ok(h.buttons().some(b=>b.name==='I sent the email'));
 assert.ok(h.buttons().some(b=>b.name==="I didn't send the email"));
 assert.ok(h.buttons().some(b=>b.name==='Cancel'));
 assert.equal(actions.length,0,'countdown expiry never records email as sent');
 h.click('I sent the email');
 assert.deepEqual(actions,['sent']);
});

test('automatic webmail attempt supports optional email review and retry without a second modal', () => {
 const h=mount('components/CustomerEmailModal.tsx', {
  content, autoStart:true, requireNotSentReason:false,
  onSent:()=>{}, onDidNotSend:()=>{}, onCancel:()=>{},
 });
 assert.equal(h.attempts.length,1);
 h.render();
 h.click('Review email details');h.render();
 assert.match(h.text(),/Recipients/);
 assert.match(h.text(),/customer@example.org/);
 h.advance(5000);
 h.click('Open Web Mail again');
 assert.equal(h.attempts.length,2,'retry requires an explicit click');
 h.render();
 assert.ok(h.buttons().some(b=>b.name==='I sent the email'), 'retry should not reset the completed countdown');
});

test('auto-launch with no customer address never attempts an empty email', () => {
 const h=mount('components/CustomerEmailModal.tsx', {
  content:null, autoStart:true, requireNotSentReason:false,
  onSent:()=>{}, onDidNotSend:()=>{}, onCancel:()=>{},
 });
 h.render();
 assert.equal(h.attempts.length,0);
 assert.ok(h.buttons().some(b=>b.name==="I didn't send the email"));
 assert.ok(!h.buttons().some(b=>b.name==='Send Email'));
});

test('resending a tracking link also skips the second Send Email click',()=>{
 const detail=source('app/problems/[id]/page.tsx');
 assert.match(detail,/pendingEmailLaunch && <CustomerEmailModal autoStart content=\{pendingEmailLaunch\.content\}/);
});

test('customer reply preview remains collapsed until requested; retry does not restart confirmation clock',()=>{
 const actions=[];
 const h=mount('components/CustomerHistoryReplyEmailModal.tsx',{
  email:{...content,direct_url:'',customer_message:'Original message'},
  onSent:()=>actions.push('sent'),onCancel:()=>actions.push('cancel'),
 });
 h.render();
 assert.doesNotMatch(h.text(),/Original message/);
 h.click('Review email details');h.render();
 assert.match(h.text(),/Recipients|To:/);
 assert.equal(h.attempts.length,1);
 h.render();assert.equal(h.attempts.length,1);
 h.advance(5000);
 h.click('Open Web Mail again');
 assert.equal(h.attempts.length,2);
 h.render();assert.ok(h.buttons().some(b=>b.name==='I sent the email'));
 assert.equal(actions.length,0);
});

test('mention email preview is optional and retry does not mark history saved',()=>{
 let saved=0;
 const h=mount('components/MentionEmailModal.tsx',{
  emails:[{email:'lab@example.org',recipients:['lab@example.org'],mentions:['@Lab'],subject:'Ticket',body:'Notification text'}],
  onComplete:()=>{saved++;},onCancel:()=>{},
 });
 h.render();
 assert.doesNotMatch(h.text(),/Mentions: @Lab/);
 h.click('Review email details');h.render();
 assert.match(h.text(),/Mentions: @Lab/);
 h.advance(5000);h.click('Open Web Mail again');
 assert.equal(h.attempts.length,2);assert.equal(saved,0);
 h.render();h.click("I didn't send the email");assert.equal(saved,0);
});

test('mention emails with no recipients do not request a mail handler',()=>{
 const h=mount('components/MentionEmailModal.tsx',{
  emails:[{email:'',recipients:[],mentions:[],subject:'None',body:'None'}],
  onComplete:()=>{},onCancel:()=>{},
 });
 h.render();assert.equal(h.attempts.length,0);
 assert.ok(!h.buttons().some(b=>b.name==='I sent the email'));
});

test('other editable email composers retain Send Email so staff can finish writing',()=>{
 const general=source('components/GeneralCustomerEmailModal.tsx');
 const testing=source('components/BackToTestingEmailModal.tsx');
 assert.match(general,/onClick=\{openEmail\}.*Send Email/);
 assert.match(testing,/onClick=\{proceed\}.*Send Email/);
 assert.match(general,/onChange=\{event => \{ setSubject/);
 assert.match(testing,/Additional details \(optional\)/);
});

test('prepared system monthly reports auto-launch and still require staff confirmation',()=>{
 const code=source('app/send-system-emails/page.tsx');
 assert.match(code,/"Review and send" is the user's decision/);
 assert.match(code,/attemptedDraftId\.current = ''/);
 assert.match(code,/start\(\{ to: selected\.to_emails/);
 assert.match(code,/if \(!selected \|\| seconds !== 0\) return;/);
 assert.doesNotMatch(code,/onClick=\{openMailApp\}/);
 assert.match(code,/Try Opening Web Mail/);
});

test('prepared Action Required update auto-launches after Send Email with retry',()=>{
 const code=source('components/ActionRequiredEmailModal.tsx');
 assert.match(code,/onClick=\{preview\}/);
 assert.match(code,/\{busy \? 'Preparing…' : 'Send Email'\}/);
 assert.match(code,/attemptedDraft\.current = draft/);
 assert.match(code,/start\(\{ to: draft\.recipients/);
 assert.match(code,/seconds === 0.*I sent the email/);
 assert.match(code,/Try Opening Web Mail/);
});
