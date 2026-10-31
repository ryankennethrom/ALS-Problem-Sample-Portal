const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.join(__dirname,'..');
const route=fs.readFileSync(path.join(root,'app/reports/monthly/[token]/route.ts'),'utf8');
const app=fs.readFileSync(path.join(root,'components/AppShell.tsx'),'utf8');
const backend=fs.readFileSync(path.join(root,'../backend/problem_samples/monthly_report_portal.py'),'utf8');
const config=fs.readFileSync(path.join(root,'../backend/config/urls.py'),'utf8');
const table=fs.readFileSync(path.join(root,'app/tables/[id]/page.tsx'),'utf8');
const serializer=fs.readFileSync(path.join(root,'../backend/problem_samples/serializers.py'),'utf8');
const service=fs.readFileSync(path.join(root,'../backend/problem_samples/system_email_service.py'),'utf8');
test('old report links now download Excel instead of rendering an HTML page',()=>{
 assert.match(route,/NextResponse.redirect/);
 assert.match(route,/backend-api\/public\/monthly-reports/);
 assert.match(route,/\/xlsx\//);
 assert.match(app,/pathname.startsWith\('\/reports\/monthly\/'\)/);
 assert.equal(fs.existsSync(path.join(root,'app/reports/monthly/[token]/page.tsx')),false);
});
test('Excel download endpoint validates bearer link and expiry',()=>{
 assert.match(config,/PublicMonthlyReportExcelView/);
 assert.match(backend,/public_report_or_none\(token\)/);
 assert.match(backend,/public_revoked_at/);
 assert.match(backend,/public_expires_at/);
 assert.match(backend,/openxmlformats-officedocument.spreadsheetml.sheet/);
 assert.match(backend,/private, no-store/);
});
test('admin selects report columns per Brand monthly rule, saved to JSON',()=>{
 assert.match(table,/Excel report — ticket columns/);
 assert.match(table,/report_column_ids/);
 assert.match(table,/Select columns/);
 assert.match(serializer,/report_column_ids/);
 assert.match(serializer,/eligible_ids/);
});
test('queued emails keep report link and snapshots for reproducible Excel downloads',()=>{
 assert.match(backend,/Download Excel monthly report/);
 assert.match(service,/finalize_report\(mail\)/);
 assert.match(service,/snapshot_tickets\(column, rule, start, end, matches, lab\)/);
 assert.match(backend,/render_excel\(mail.report_snapshot\)/);
});
test('workbook has separate Summary and Tickets sheets, wrap and spreadsheet-injection protections',()=>{
 assert.match(backend,/create_sheet\('Summary'\)/);
 assert.match(backend,/create_sheet\('Tickets'\)/);
 assert.match(backend,/open the Tickets tab/);
 assert.match(backend,/wrap_text=True/);
 assert.match(backend,/row_dimensions/);
 assert.match(backend,/auto_filter.ref/);
 assert.match(backend,/freeze_panes/);
 assert.match(backend,/_excel_value/);
});
