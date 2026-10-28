const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const file = relative => fs.readFileSync(path.join(__dirname,'..',relative),'utf8');
const page = file('app/tables/[id]/page.tsx');
const service = file('../backend/problem_samples/system_email_service.py');
const matcher = file('../backend/problem_samples/brand_email_rules.py');
const serializer = file('../backend/problem_samples/serializers.py');
const migration = file('../backend/problem_samples/migrations/0098_brand_email_rules.py');

test('Brand editor supports company dependencies and per-rule ticket or company sources', () => {
  assert.match(page,/function BrandCompanyDependencies/);
  assert.match(page,/col\.column_type === 'distributor' \|\| col\.column_type === 'end_user'/);
  assert.match(page,/Match any of these Brand sources \(OR\)/);
  assert.match(page,/company_brand_dependencies:/);
  assert.match(page,/brand_cc_rules:/);
  assert.match(page,/only when sending a tracking link/);
  assert.doesNotMatch(page,/Cc of tracking and general customer email drafts/);
  assert.doesNotMatch(page,/type === 'distributor' && <BrandCCRulesEditor/);
});
test('new and resent tracking-link drafts use server-computed Brand CC', () => {
  assert.match(file('components/ProblemForm.tsx'),/cc: prepared\.brand_cc_recipients/);
  assert.match(file('app/problems/[id]/page.tsx'),/cc: problem\.brand_cc_recipients/);
  assert.match(file('../backend/problem_samples/views.py'),/def _brand_auto_cc\(/);
});
test('Brand CC is not enforced in ordinary customer emails or .eml drafts', () => {
  const ticket = file('app/problems/[id]/page.tsx');
  const general = file('components/GeneralCustomerEmailModal.tsx');
  const views = file('../backend/problem_samples/views.py');
  const customerSent = views.split('def customer_message_sent(')[1].split('def customer_notification_draft(')[0];
  const emlDraft = views.split('def customer_notification_draft(')[1].split('def customer_notification_sent(')[0];
  assert.doesNotMatch(ticket, /generalEmailCC|ccRecipients=\{generalEmailCC\}/);
  assert.match(general, /cc: \[\]/);
  assert.doesNotMatch(general, /Brand rules|ccRecipients/);
  assert.doesNotMatch(customerSent, /_brand_auto_cc|_brand_email_cc_for_values/);
  assert.doesNotMatch(emlDraft, /_brand_auto_cc|_brand_email_cc_for_values/);
  assert.match(customerSent, /_validated_email_list\(request\.data\.get\('cc'\)\)/);
  assert.match(emlDraft, /_validated_email_list\(request\.data\.get\('cc'\)\)/);
});

test('monthly reports are scoped to Brand columns and re-use OR matching', () => {
  assert.match(service,/ProblemColumn\.TYPE_BRAND/);
  assert.match(service,/rule_matches\(column, row\.custom_values/);
  assert.match(service,/column\.brand_cc_rules/);
});
test('legacy company-name rules require admin review before becoming active', () => {
  assert.match(migration,/item\['pending_brand_review'\] = True/);
  assert.match(matcher,/rule\.get\('pending_brand_review'\)/);
  assert.match(page,/Migrated Distributor-name rule/);
  assert.match(serializer,/attrs\['brand_cc_rules'\] = cleaned_rules/);
});
test('migration retains rule data and removes the legacy Distributor rule field', () => {
  assert.match(migration,/migrations\.RunPython\(move_rules/);
  assert.match(migration,/migrations\.RemoveField\('problemcolumn', 'distributor_cc_rules'\)/);
  assert.match(migration,/item\['sources'\] = \[source_id\]/);
  assert.match(migration,/SystemEmail\.objects\.filter/);
});
