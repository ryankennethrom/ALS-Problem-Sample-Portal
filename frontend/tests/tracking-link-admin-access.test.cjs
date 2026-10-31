const test = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const root = join(__dirname, '..');
const source = file => readFileSync(join(root, file), 'utf8');

test('ticket detail renders visible URL for staff but a clickable anchor for admins', () => {
  const detail = source('app/problems/[id]/page.tsx');
  assert.match(detail, /<TrackingLinkDisplay url=\{p\.tracking_url\} canOpen=\{Boolean\(currentUser\?\.is_admin\)\} fullUrl/);
  assert.match(detail, /currentUser\?\.is_admin && p\.tracking_url && <button[^>]+onClick=\{revokeTrackingLink\}/);
});

test('ticket list displays a non-clickable tracking URL to non-admin users', () => {
  const list = source('app/problem-samples/page.tsx');
  assert.match(list, /c\.field_key === 'system-tracking-link'[\s\S]*?<TrackingLinkDisplay url=\{p\.tracking_url\} canOpen=\{Boolean\(currentUser\?\.is_admin\)\}/);
});

test('Follow Up Required shows staff URL as non-clickable text', () => {
  const list = source('app/follow-up-required/page.tsx');
  assert.match(list, /column\.field_key === 'system-tracking-link'[\s\S]*?<TrackingLinkDisplay url=\{item\.tracking_url\} canOpen=\{Boolean\(currentUser\?\.is_admin\)\}/);
});

test('shared display has an anchor only for administrators and disables UI copying for staff', () => {
  const display = source('components/TrackingLinkDisplay.tsx');
  assert.match(display, /if \(canOpen\) \{/);
  assert.match(display, /<a[^>]*href=\{url\}/);
  assert.match(display, /<span className="tracking-link-noninteractive tracking-link-value"/);
  assert.match(display, /onCopy=\{event => event\.preventDefault\(\)\}/);
  assert.match(display, /onDragStart=\{event => event\.preventDefault\(\)\}/);
  const css = source('app/globals.css');
  assert.match(css, /\.tracking-link-noninteractive\{user-select:none;-webkit-user-select:none/);
});

test('staff email preview shows but does not turn tracking URLs into links or offer Copy email', () => {
  const modal = source('components/CustomerEmailModal.tsx');
  assert.match(modal, /currentUser\?\.is_admin && <button[\s\S]*?>Copy email<\/button>/);
  assert.match(modal, /<TrackingLinkPreviewText text=\{content\.body\} \/>/);
  assert.match(modal, /start\(content\)/);
  const reply = source('components/CustomerHistoryReplyEmailModal.tsx');
  assert.match(reply, /<TrackingLinkPreviewText text=\{email\.body\} \/>/);
  assert.match(reply, /start\(\{ to: email\.to, cc: email\.cc \|\| \[\], subject: email\.subject, body: email\.body \}\)/);
});

test('preview uses noninteractive text spans for tracking URLs and no href', () => {
  const text = source('components/TrackingLinkPreviewText.tsx');
  assert.match(text, /\.split\(TRACKING_URL\)/);
  assert.match(text, /tracking-link-noninteractive/);
  assert.doesNotMatch(text, /href=/);
});

test('backend provides tracking URLs to staff but keeps standalone token admin-only', () => {
  const serializers = source('../backend/problem_samples/serializers.py');
  assert.match(serializers, /def get_acknowledgement_token\(self, obj\):\n        return obj\.acknowledgement_token if self\._can_view_tracking_link\(\) else None/);
  assert.match(serializers, /def get_tracking_url\(self, obj\):\n        return self\.get_acknowledgement_url\(obj\)/);
  assert.match(serializers, /exclude = \['pending_tracking_token'\]/);
  assert.match(serializers, /def get_details\(self, obj\):[\s\S]*?return obj\.details or \{\}/);
  const views = source('../backend/problem_samples/views.py');
  assert.match(views, /def customer_notification_credentials\(self, request, pk=None\)/);
  assert.match(views, /def prepare_new\(self, request\)/);
});
