const assert = require('node:assert/strict');
const {test} = require('node:test');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');

const source = readFileSync(join(__dirname, '../components/BrandAutocomplete.tsx'), 'utf8');

test('brand suggestions do not fetch or open while the input is unfocused', () => {
  assert.match(source, /const \[searchEnabled, setSearchEnabled\] = useState\(false\)/);
  assert.match(source, /if \(!searchEnabled\)\s*\{\s*setSuggestions\(\[\]\);\s*setOpen\(false\);/);
  assert.match(source, /\}, \[text, searchEnabled\]\)/);
});

test('focusing the brand input enables suggestions; blurring disables them and invalidates in-flight results', () => {
  assert.match(source, /onFocus=\{\(\) => \{\s*setSearchEnabled\(true\)/);
  assert.match(source, /onBlur=\{\(\) => window\.setTimeout\(\(\) => \{\s*setOpen\(false\);\s*setSearchEnabled\(false\);\s*requestId\.current \+= 1;/);
  assert.match(source, /if \(currentRequest !== requestId\.current\) return;/);
});

test('choosing a brand stops autocomplete from reopening on the selected value', () => {
  assert.match(source, /function choose\([\s\S]*?setOpen\(false\);\s*setSearchEnabled\(false\);/);
});
