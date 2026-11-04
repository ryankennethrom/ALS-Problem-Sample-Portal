const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.resolve(__dirname, '../app/tables/[id]/page.tsx'), 'utf8');

test('client email timeout accepts zero instead of clamping it to one', () => {
  assert.match(source, /type="number" min=\{0\} max=\{87600\}/);
  assert.match(source, /Math\.max\(0, Math\.min\(87600,/);
  assert.doesNotMatch(source, /Math\.max\(1, Math\.min\(87600,/);
});
test('zero hour option is explained and does not disable escalation', () => {
  assert.match(source, /Set to 0 hours to make the ticket eligible on the next escalation check/);
  assert.match(source, /checked=\{value !== null\}/);
  assert.match(source, /client_email_fallback_hours: type === 'client_email' && dependencyIds.length > 1 \? fallbackHours : null/);
  assert.match(source, /client_email_fallback_hours: colType === 'client_email' && colDependencyIds.length > 1 \? colFallbackHours : null/);
});
