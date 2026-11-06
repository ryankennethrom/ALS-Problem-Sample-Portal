const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const component = fs.readFileSync(path.join(__dirname, '../components/GeneralCustomerEmailModal.tsx'), 'utf8');

test('Email Customer defaults to a single Ticket prefix in the subject', () => {
  assert.match(component, /useState\(`Ticket #\$\{problemNumber\}`\)/);
  assert.doesNotMatch(component, /Ticket Ticket #/i);
});

test('Email Customer default message uses one ticket prefix', () => {
  assert.match(component, /regarding ticket #\$\{problemNumber\}/);
  assert.doesNotMatch(component, /ticket ticket #/i);
});

test('Email Customer preserves editable subject and sends its current value', () => {
  assert.match(component, /subject: subject\.trim\(\)/);
  assert.match(component, /value=\{subject\}/);
  assert.match(component, /onChange=\{event => \{ setSubject\(event\.target\.value\); \}\}/);
});
