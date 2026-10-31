const test = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const src = (path) => readFileSync(join(__dirname, '..', path), 'utf8');
const frontend = src('app/problems/[id]/page.tsx');
const backend = src('../backend/problem_samples/views.py');

test('reply editor accepts images and files for tracking-link chat', () => {
  assert.match(frontend, /id="staff-reply-images"[\s\S]*?type="file"/);
  assert.match(frontend, /id="staff-reply-attachments"[\s\S]*?type="file"/);
  assert.match(frontend, /reply_files: \{[\s\S]*?historyReplyImages\.map[\s\S]*?historyReplyAttachments\.map/);
});

test('reply confirmation uploads files only after staff confirms sent', () => {
  assert.match(frontend, /async function confirmHistoryReplySent\(\)[\s\S]*?new FormData\(\)/);
  assert.match(frontend, /historyReplyEmailDraft\.images\.forEach\(file => payload\.append\('images', file\)\)/);
  assert.match(frontend, /historyReplyEmailDraft\.attachments\.forEach\(file => payload\.append\('attachments', file\)\)/);
});

test('email contains a tracking-chat reference rather than actual file attachments', () => {
  assert.match(backend, /\[View image\/file in the tracking link chat\]/);
  assert.match(backend, /staff_reply_images': saved_images/);
  assert.match(backend, /staff_reply_attachments': saved_attachments/);
});

test('customer tracking thread renders staff reply images and attachments', () => {
  assert.match(backend, /'images': \[image for image in details\.get\('staff_reply_images'/);
  assert.match(backend, /'attachments': \[file for file in details\.get\('staff_reply_attachments'/);
  const chat = src('app/track/[token]/page.tsx');
  assert.match(chat, /message\.images!\.map/);
  assert.match(chat, /message\.attachments!\.map/);
});
