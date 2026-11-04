const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const app = path.resolve(__dirname, '../app');
const publicDir = path.resolve(__dirname, '../public');

function pngDimensions(file) {
  const bytes = fs.readFileSync(file);
  assert.equal(bytes.subarray(0, 8).toString('hex'), '89504e470d0a1a0a', `${file} must be a valid PNG`);
  assert.equal(bytes.subarray(12, 16).toString(), 'IHDR');
  return [bytes.readUInt32BE(16), bytes.readUInt32BE(20)];
}

test('Next.js app router provides a valid multi-size browser favicon', () => {
  const bytes = fs.readFileSync(path.join(app, 'favicon.ico'));
  assert.equal(bytes.readUInt16LE(0), 0);
  assert.equal(bytes.readUInt16LE(2), 1);
  const count = bytes.readUInt16LE(4);
  assert.ok(count >= 3, 'favicon should include multiple resolutions');
  const sizes = new Set();
  for (let i = 0; i < count; i++) {
    const off = 6 + i * 16;
    const size = bytes[off] || 256;
    sizes.add(size);
    const length = bytes.readUInt32LE(off + 8);
    const offset = bytes.readUInt32LE(off + 12);
    assert.ok(length > 0 && offset + length <= bytes.length, 'ICO image entry must be readable');
  }
  assert.ok(sizes.has(16), 'favicon should support 16x16 browser tabs');
  assert.ok(sizes.has(32), 'favicon should support 32x32 browser tabs');
});

test('Next.js metadata icons use recognizable ALS artwork at appropriate sizes', () => {
  assert.deepEqual(pngDimensions(path.join(app, 'icon.png')), [192, 192]);
  assert.deepEqual(pngDimensions(path.join(app, 'apple-icon.png')), [180, 180]);
  assert.deepEqual(pngDimensions(path.join(publicDir, 'als-logo.png')), [270, 270]);
});

test('the app keeps its Problem Samples Tracker browser tab title', () => {
  const layout = fs.readFileSync(path.join(app, 'layout.tsx'), 'utf8');
  assert.match(layout, /title:\s*['"]Problem Samples Tracker['"]/);
});


test('every PNG payload inside the ICO is encoded as RGBA for Next.js', () => {
  const bytes = fs.readFileSync(path.join(app, 'favicon.ico'));
  const count = bytes.readUInt16LE(4);
  for (let i = 0; i < count; i++) {
    const entryOffset = 6 + i * 16;
    const size = bytes.readUInt32LE(entryOffset + 8);
    const offset = bytes.readUInt32LE(entryOffset + 12);
    const image = bytes.subarray(offset, offset + size);
    assert.equal(image.subarray(0, 8).toString('hex'), '89504e470d0a1a0a', `ICO frame ${i} must be PNG`);
    assert.equal(image.subarray(12, 16).toString(), 'IHDR');
    assert.equal(image.readUInt8(25), 6, `ICO frame ${i} must have PNG color type 6 (RGBA), not RGB`);
  }
});

test('Next.js standalone PNG icons are RGBA encoded', () => {
  for (const file of ['icon.png', 'apple-icon.png']) {
    const bytes = fs.readFileSync(path.join(app, file));
    assert.equal(bytes.readUInt8(25), 6, `${file} must be RGBA`);
  }
});
