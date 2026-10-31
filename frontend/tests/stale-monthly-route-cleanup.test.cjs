const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const projectRoot = path.join(__dirname, '..');
const cleanupSource = path.join(projectRoot, 'scripts', 'cleanup-stale-routes.cjs');
const reportRelative = path.join('app', 'reports', 'monthly', '[token]');

function testFixture(fn) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'als-legacy-routes-'));
  const scriptDir = path.join(root, 'scripts');
  const reportDir = path.join(root, reportRelative);
  fs.mkdirSync(scriptDir, { recursive: true });
  fs.mkdirSync(reportDir, { recursive: true });
  fs.copyFileSync(cleanupSource, path.join(scriptDir, 'cleanup-stale-routes.cjs'));
  const run = () => spawnSync(process.execPath, [path.join(scriptDir, 'cleanup-stale-routes.cjs')], { cwd: root, encoding: 'utf8' });
  try { fn({ root, reportDir, run }); } finally { fs.rmSync(root, { recursive: true, force: true }); }
}

test('Next.js route collision guard is executed before npm build and dev', () => {
  const pkg = require('../package.json');
  assert.equal(pkg.scripts.prebuild, 'node scripts/cleanup-stale-routes.cjs');
  assert.equal(pkg.scripts.predev, 'node scripts/cleanup-stale-routes.cjs');
  assert.ok(fs.existsSync(path.join(projectRoot, reportRelative, 'route.ts')));
  assert.equal(fs.existsSync(path.join(projectRoot, reportRelative, 'page.tsx')), false);
});

test('old HTML page is archived without touching new Excel route', () => testFixture(({ root, reportDir, run }) => {
  const page = path.join(reportDir, 'page.tsx');
  const route = path.join(reportDir, 'route.ts');
  fs.writeFileSync(page, '// old HTML report');
  fs.writeFileSync(route, '// new Excel route');
  const result = run();
  assert.equal(result.status, 0, result.stderr);
  assert.equal(fs.existsSync(page), false);
  assert.equal(fs.readFileSync(route, 'utf8'), '// new Excel route');
  assert.equal(fs.readFileSync(path.join(root, '.legacy-routes', 'monthly-report-page.tsx'), 'utf8'), '// old HTML report');
  assert.equal(run().status, 0, 'cleanup is safe to rerun');
}));

test('old page is not removed unless the new Excel route exists', () => testFixture(({ reportDir, run }) => {
  const page = path.join(reportDir, 'page.tsx');
  fs.writeFileSync(page, '// only an HTML page');
  assert.equal(run().status, 0);
  assert.equal(fs.readFileSync(page, 'utf8'), '// only an HTML page');
}));

test('preexisting archived page is not overwritten', () => testFixture(({ root, reportDir, run }) => {
  const backupDir = path.join(root, '.legacy-routes');
  fs.mkdirSync(backupDir);
  fs.writeFileSync(path.join(backupDir, 'monthly-report-page.tsx'), '// first backup');
  fs.writeFileSync(path.join(reportDir, 'route.ts'), '// Excel');
  fs.writeFileSync(path.join(reportDir, 'page.tsx'), '// second backup');
  assert.equal(run().status, 0);
  assert.equal(fs.readFileSync(path.join(backupDir, 'monthly-report-page.tsx'), 'utf8'), '// first backup');
  assert.equal(fs.readFileSync(path.join(backupDir, 'monthly-report-page-1.tsx'), 'utf8'), '// second backup');
}));
