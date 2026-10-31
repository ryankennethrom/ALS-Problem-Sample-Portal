const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const source = p => fs.readFileSync(path.join(__dirname,'..',p),'utf8');
const jsx = (type, props) => ({type,props:props || {}});
const fragments = {Fragment:'fragment'};
function compile(p) {
 const result=ts.transpileModule(source(p), {compilerOptions:{jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS,esModuleInterop:true},reportDiagnostics:true});
 assert.equal(result.diagnostics.filter(d=>d.category===ts.DiagnosticCategory.Error).length,0);
 const m={exports:{}};
 vm.runInNewContext(result.outputText,{exports:m.exports,require(name){
   if(name==='react/jsx-runtime') return {jsx,jsxs:jsx,Fragment:'fragment'};
   if(name==='react') return {default:fragments, ...fragments};
   throw new Error('Unexpected import '+name);
 }});
 return m.exports;
}
test('admin obtains an openable tracking URL while staff sees only the text',()=>{
 const component=compile('components/TrackingLinkDisplay.tsx').default;
 const url='https://tracker.example/track/token123';
 const staff=component({url,canOpen:false});
 assert.equal(staff.type,'span');
 assert.equal(staff.props.children,url);
 assert.equal(staff.props.href,undefined);
 const fakeEvent={prevented:false,preventDefault(){this.prevented=true;}};
 staff.props.onCopy(fakeEvent);
 assert.equal(fakeEvent.prevented,true);
 const admin=component({url,canOpen:true});
 assert.equal(admin.type,'a');
 assert.equal(admin.props.href,url);
});
test('no URL returns a dash rather than a link',()=>{
 const component=compile('components/TrackingLinkDisplay.tsx').default;
 const missing=component({url:'',canOpen:false});
 assert.notEqual(missing.type,'a');
});
test('message preview preserves and wraps inline tracking URLs without anchors',()=>{
 const {TrackingLinkInlineText}=compile('components/TrackingLinkPreviewText.tsx');
 const result=TrackingLinkInlineText({text:'See https://tracker.example/track/tokenXYZ today.'});
 const segments=result.props.children;
 assert.ok(segments.some(c=>c?.type==='span' && c.props.children.includes('tokenXYZ')));
 assert.ok(segments.every(c=>c?.type!=='a'));
});
test('history field changes with tracking URLs are noninteractive for staff',()=>{
 const page=source('app/problems/[id]/page.tsx');
 assert.match(page, /history-before">\{currentUser\?\.is_admin \? displayHistoryValue\(change\.before\) : <TrackingLinkInlineText/);
 assert.match(page, /history-after">\{currentUser\?\.is_admin \? displayHistoryValue\(change\.after\) : <TrackingLinkInlineText/);
});
