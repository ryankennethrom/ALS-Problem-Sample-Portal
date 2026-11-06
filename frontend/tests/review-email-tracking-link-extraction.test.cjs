const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

const code = fs.readFileSync(path.join(__dirname,'../lib/trackingLinkAccess.ts'), 'utf8');
const output = ts.transpileModule(code, {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
const loadedModule = {exports:{}};
vm.runInNewContext(output,{exports:loadedModule.exports});
const {trackingLinkFromEmail} = loadedModule.exports;

test('extracts full tracking URL with query parameters from customer email',()=>{
 assert.equal(trackingLinkFromEmail('Hello\nhttps://tracker.example/track/token_ABC-123?message=1\nRegards'),
 'https://tracker.example/track/token_ABC-123?message=1');
});

test('removes trailing prose punctuation without truncating tracking token',()=>{
 assert.equal(trackingLinkFromEmail('Review this: https://tracker.example/track/abc123.'),
 'https://tracker.example/track/abc123');
});

test('returns null for email without a customer tracking URL',()=>{
 assert.equal(trackingLinkFromEmail('View https://tracker.example/problems/101'),null);
 assert.equal(trackingLinkFromEmail(''),null);
});
