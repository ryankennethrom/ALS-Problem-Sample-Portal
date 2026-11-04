const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const root = join(__dirname, '..', '..');
const read = path => readFileSync(join(root, path), 'utf8');

for (const route of ['track', 'acknowledge']) {
  const source = read(`frontend/app/${route}/[token]/page.tsx`);
  test(`${route} offers an optional address for shipped returns but not pickup`, () => {
    assert.match(source, /\(shippingMethod === 'courier_account' \|\| shippingMethod === 'shipping_quote'\) && <div className="public-return-address">/);
    assert.match(source, /Return shipping address <span>\(optional\)<\/span>/);
    assert.match(source, /<textarea id="return-shipping-address"[^\n]+maxLength=\{1000\}[^\n]+value=\{returnShippingAddress\}/);
    assert.doesNotMatch(source, /<textarea id="return-shipping-address"[^\n]*required/);
  });
  test(`${route} posts optional address and resets the input after confirming the return`, () => {
    assert.match(source, /return_shipping_address: returnMethod === 'pickup' \? '' : shippingAddress\.trim\(\)/);
    assert.match(source, /setReturnShippingAddress\(''\)/);
    assert.match(source, /chooseAction\('ship_back', '', \[\], \[\], shippingMethod, courierAccountNumber, courierName, returnShippingAddress\)/);
  });
}

test('backend stores optional address only in shipping-return history, without altering ticket schema', () => {
  const source = read('backend/problem_samples/views.py');
  assert.match(source, /if return_shipping_address:\s+details\['customer_return_shipping_address'\] = return_shipping_address/);
  assert.match(source, /if return_shipping_address and shipping_method == 'pickup':/);
  assert.match(source, /if len\(return_shipping_address\) > 1000:/);
  assert.match(source, /elif shipping_method or courier_name or courier_account_number or return_shipping_address:/);
});

test('staff can read multiline return address in the corresponding ticket history entry', () => {
  const details = read('frontend/app/problems/[id]/page.tsx');
  const style = read('frontend/app/globals.css');
  assert.match(details, /customer_return_shipping_address\?: string/);
  assert.match(details, /entry\.details\.customer_return_shipping_address && <div><strong>Return shipping address:<\/strong>/);
  assert.match(style, /\.history-return-shipping-address\{white-space:pre-wrap;/);
});
