const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.join(__dirname,'..');
const editor=fs.readFileSync(path.join(root,'app/tables/[id]/page.tsx'),'utf8');
const ruleType=fs.readFileSync(path.join(root,'lib/problemTables.ts'),'utf8');
const api=fs.readFileSync(path.join(root,'../backend/problem_samples/monthly_report_portal.py'),'utf8');
const serializer=fs.readFileSync(path.join(root,'../backend/problem_samples/serializers.py'),'utf8');
const mailUI=fs.readFileSync(path.join(root,'app/send-system-emails/page.tsx'),'utf8');
test('rule configuration supports all eligible columns or a selected subset',()=>{
 assert.match(ruleType,/report_column_ids\?: string\[\] \| null/);
 assert.match(editor,/All eligible columns \(default\)/);
 assert.match(editor,/Select columns/);
 assert.match(editor,/report_column_ids:event.target.checked/);
});
test('pending rule edits must be saved before generating the Excel report',()=>{
 assert.match(editor,/JSON.stringify\(saved.report_column_ids \?\? null\)/);
 assert.match(editor,/JSON.stringify\(rule.report_column_ids \?\? null\)/);
 assert.match(editor,/disabled=\{!isSaved\(rule\)/);
});
test('serializer validates configured columns using the table and strips ineligible columns',()=>{
 assert.match(serializer,/eligible_ids =/);
 assert.match(serializer,/reportable_column\(field\)/);
 assert.match(serializer,/set\(selected_columns\).issubset\(eligible_ids\)/);
 assert.match(api,/configured_ids = rule.get\('report_column_ids'\)/);
});
test('staff report view offers Excel download and revocation rather than PDF actions',()=>{
 assert.match(mailUI,/Download Excel report/);
 assert.match(mailUI,/Revoke this report link/);
 assert.doesNotMatch(mailUI,/download its PDFs/);
});
