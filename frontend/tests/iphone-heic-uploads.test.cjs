const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const root = join(__dirname, '..', '..');
const read = file => readFileSync(join(root, file), 'utf8');
const imageAccept = /accept="image\/jpeg,image\/png,image\/gif,image\/webp,image\/heic,image\/heif,\.heic,\.heif"/;

test('ticket creation accepts HEIC/HEIF photos from iPhone library', () => {
  const source = read('frontend/components/ProblemForm.tsx');
  assert.match(source, imageAccept);
  assert.match(source, /iPhone HEIC\/HEIF/);
});

test('existing ticket and staff reply image pickers accept iPhone photos', () => {
  const source = read('frontend/app/problems/[id]/page.tsx');
  assert.equal((source.match(new RegExp(imageAccept.source, 'g')) || []).length, 2);
  assert.match(source, /iPhone HEIC\/HEIF/);
});

for (const route of ['track', 'acknowledge']) {
  test(`${route} customer image picker accepts HEIC/HEIF photos`, () => {
    const source = read(`frontend/app/${route}/[token]/page.tsx`);
    assert.match(source, imageAccept);
    assert.match(source, /JPEG, PNG, GIF, WebP or HEIC\/HEIF/);
    assert.match(source, /capture="environment"/);
  });
}

test('backend uses actual decoded image format rather than file extension/MIME', () => {
  const source = read('backend/problem_samples/image_processing.py');
  const views = read('backend/problem_samples/views.py');
  const requirements = read('backend/requirements.txt');
  assert.match(requirements, /pillow-heif>=1\.8,<2/);
  assert.match(source, /register_heif_opener\(\)/);
  assert.match(source, /image_format = \(image\.format or ''\)\.upper\(\)/);
  assert.match(source, /'HEIF', 'HEIC'/);
  assert.match(views, /return validate_problem_image\(uploaded\)/);
  assert.match(source, /format="WEBP"/);
});
