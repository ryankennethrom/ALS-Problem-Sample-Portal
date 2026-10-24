const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const read = p => fs.readFileSync(path.resolve(__dirname, '..', p),'utf8');

test('OAuth callback exchanges code via existing authenticated backend API and clears URL', () => {
  const page = read('app/auth/callback/page.tsx');
  assert.match(page, /replaceState\(null, '', '\/auth\/callback'\)/);
  assert.match(page, /api\('\/auth\/microsoft\/callback\/'/);
});
test('My Account keeps Microsoft optional', () => {
  const page = read('app/account/page.tsx');
  assert.match(page, /Microsoft 365 — Optional Email Connection/);
  assert.match(page, /Connect Microsoft 365/);
  assert.match(page, /Disconnect Microsoft 365/);
});
test('Graph is offered for connected staff and old mailto for unconnected', () => {
  for (const name of ['CustomerEmailModal.tsx','GeneralCustomerEmailModal.tsx','MentionEmailModal.tsx','CustomerHistoryReplyEmailModal.tsx','BackToTestingEmailModal.tsx']) {
    const value = read('components/'+name);
    assert.match(value, /useMicrosoftConnection/);
    assert.match(value, /MicrosoftSendButton/);
    assert.match(value, /invokeCustomerEmail/);
  }
});
test('Send System Emails and action required update support Graph', () => {
  assert.match(read('app/send-system-emails/page.tsx'), /MicrosoftSendButton/);
  assert.match(read('components/ActionRequiredEmailModal.tsx'), /MicrosoftSendButton/);
});
