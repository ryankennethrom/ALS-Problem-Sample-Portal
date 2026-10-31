const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const root = join(__dirname, '..', '..');
const read = name => readFileSync(join(root, name), 'utf8');

for (const route of ['track', 'acknowledge']) {
  const source = read(`frontend/app/${route}/[token]/page.tsx`);
  test(`${route} form requires courier name alongside account number`, () => {
    assert.match(source, /<label htmlFor="return-courier-name">Courier name <strong aria-hidden="true">\*<\/strong><\/label>/);
    assert.match(source, /<input id="return-courier-name"[^\n]*value=\{courierName\}[^\n]*required placeholder=/);
    assert.match(source, /!courierName\.trim\(\) \|\| !courierAccountNumber\.trim\(\)/);
  });
  test(`${route} posts courier name and clears it when reopening`, () => {
    assert.match(source, /courier_name: returnMethod === 'courier_account' \? returnCourierName\.trim\(\) : ''/);
    assert.match(source, /chooseAction\('ship_back', '', \[\], \[\], shippingMethod, courierAccountNumber, courierName\)/);
    assert.match(source, /setShippingMethod\(''\); setCourierName\(''\); setCourierAccountNumber\(''\);/);
  });
}

test('backend rejects missing, oversized and misplaced courier names', () => {
  const source = read('backend/problem_samples/views.py');
  assert.match(source, /courier_name = ' '\.join\(str\(request\.data\.get\('courier_name'\) or ''\)\.split\(\)\)/);
  assert.match(source, /if not courier_name:\s*return Response\(\{'detail': 'Enter your courier name\.'/);
  assert.match(source, /if len\(courier_name\) > 200:/);
  assert.match(source, /elif courier_name or courier_account_number:/);
  assert.match(source, /elif shipping_method or courier_name or courier_account_number:/);
});

test('backend stores courier name and account in ticket history without a schema change', () => {
  const source = read('backend/problem_samples/views.py');
  assert.match(source, /details\['customer_courier_name'\] = courier_name/);
  assert.match(source, /details\['customer_courier_account_number'\] = courier_account_number/);
  assert.match(source, /'courier_account': 'Provide your courier name and account number'/);
});

test('staff ticket history displays courier name as well as account number', () => {
  const source = read('frontend/app/problems/[id]/page.tsx');
  assert.match(source, /customer_courier_name\?: string/);
  assert.match(source, /<strong>Courier name:<\/strong> \{entry\.details\.customer_courier_name\}/);
  assert.match(source, /<strong>Courier account number:<\/strong> \{entry\.details\.customer_courier_account_number\}/);
});
