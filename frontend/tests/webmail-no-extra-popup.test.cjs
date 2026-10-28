const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

const root = path.join(__dirname, '..');
function mount() {
  let index=0;
  const hooks=[], effects=[];
  const listeners = new Map();
  const copied=[];
  const react={
    useState(initial) { const n=index++; if (!(n in hooks)) hooks[n]=initial;
      return [hooks[n], value=> {hooks[n]=typeof value==='function'?value(hooks[n]):value;}]; },
    useEffect(fn, deps) { const n=index++; if (!effects[n]) effects[n]={deps, cleanup:fn()}; },
  };
  const jsx=(type,props={})=>typeof type==='function'?type(props):{type,props};
  const email={OUTLOOK_EMAIL_FALLBACK_EVENT:'als-outlook-email-manual-compose'};
  const source=fs.readFileSync(path.join(root,'components/OutlookEmailManualCompose.tsx'),'utf8');
  const code=ts.transpileModule(source,{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS},reportDiagnostics:true});
  assert.equal(code.diagnostics.filter(d=>d.category===ts.DiagnosticCategory.Error).length,0);
  const exp={};
  vm.runInNewContext(code.outputText,{
    exports:exp,
    require:name=> ({react,'react/jsx-runtime':{jsx,jsxs:jsx,Fragment:'fragment'},'@/lib/customerEmail':email})[name],
    window:{addEventListener:(name,cb)=>listeners.set(name,cb),removeEventListener:(name)=>listeners.delete(name)},
    navigator:{clipboard:{writeText:async text=>{copied.push(text);}}},
  });
  let tree;
  function render(){index=0;tree=exp.default();return tree;}
  function nodes(node){if(node==null)return[];if(Array.isArray(node))return node.flatMap(nodes);if(typeof node!=='object')return[node];return[node,...nodes(node.props?.children)];}
  function labels(){return nodes(tree).filter(n=>typeof n==='string').join(' ');}
  function dispatch(draft){listeners.get(email.OUTLOOK_EMAIL_FALLBACK_EVENT)({detail:draft});render();}
  function button(label){const b=nodes(tree).find(n=>n?.type==='button'&&nodes(n.props?.children).filter(x=>typeof x==='string').join('')===label);assert.ok(b,`Missing ${label}`);return b;}
  render();
  return{render,dispatch,copied,labels,button,tree:()=>tree};
}
const email={to:['x@example.org'],cc:['cc@example.org'],subject:'Subject',body:'Full body',link:'mailto:x@example.org?subject=Subject',manualBody:false,headersPrefilled:true,fullLinkLength:123,mailtoLink:'mailto:x@example.org'};

test('short draft never creates a second email dialog',()=>{
 const h=mount();
 assert.equal(h.tree(),null);
 h.dispatch(email);
 assert.equal(h.tree(),null);
 assert.doesNotMatch(h.labels(),/Check your email draft/);
});

test('oversized draft shows a non-modal warning and complete copy options',async()=>{
 const h=mount();
 h.dispatch({...email,manualBody:true});
 assert.equal(h.tree().type,'aside');
 assert.equal(h.tree().props.className,'outlook-manual-notice');
 assert.doesNotMatch(h.labels(),/Check your email draft/);
 assert.match(h.labels(),/not included/);
 assert.doesNotMatch(h.labels(),/I sent the email/);
 await h.button('Copy full message').props.onClick();
 assert.deepEqual(h.copied,['Full body']);
 await h.button('Copy Cc recipients').props.onClick();
 assert.deepEqual(h.copied,['Full body','cc@example.org']);
 h.button('Dismiss').props.onClick();h.render();
 assert.equal(h.tree(),null);
});

test('next normal email automatically clears the previous oversized warning',()=>{
 const h=mount();
 h.dispatch({...email,manualBody:true});
 assert.notEqual(h.tree(),null);
 h.dispatch(email);
 assert.equal(h.tree(),null);
});

test('oversized notice clearly warns when other email headers are omitted',()=>{
 const h=mount();
 h.dispatch({...email,manualBody:true,headersPrefilled:false});
 assert.match(h.labels(),/recipient addresses or the subject may also be missing/);
 assert.ok(h.button('Copy Subject'));
});
