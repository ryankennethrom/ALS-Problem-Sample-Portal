const test = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const root = join(__dirname, '..');
const settings = readFileSync(join(root, 'app/tables/[id]/page.tsx'), 'utf8');
const serializer = readFileSync(join(root, '../backend/problem_samples/serializers.py'), 'utf8');
const views = readFileSync(join(root, '../backend/problem_samples/views.py'), 'utf8');

test('add column offers separate existing and future inputs', () => {
  assert.match(settings, /label="Fill existing with"/);
  assert.match(settings, /<DefaultValueField type=\{colType\} choices=\{newChoiceList\} value=\{defaultValue\}/);
  assert.match(settings, /fill_existing_with: .*normalizeDefault\(colType, fillExistingWith\)/);
  assert.match(settings, /setFillExistingWith\(blankDefault\(next\)\)/);
});
test('backend consumes one-time fill value without storing it as a default', () => {
  assert.match(serializer, /fill_existing_with = serializers\.JSONField\(required=False, allow_null=True, write_only=True\)/);
  assert.match(serializer, /validated_data\.pop\('fill_existing_with', None\)/);
  assert.match(views, /fill_existing = getattr\(column, '_fill_existing_with', None\)/);
  assert.doesNotMatch(views, /default = column\.default_value\n\s*has_default/);
});
