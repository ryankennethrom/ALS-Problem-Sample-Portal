#!/usr/bin/env node
'use strict';

// Older ALS Ticket Tracker installations contain an HTML monthly-report page.
// The monthly-report URL is now a route handler that downloads an Excel file.
// `cp -a` updates do not remove old files, and Next.js rejects page.tsx + route.ts
// in the same directory. Archive ONLY this known-obsolete route before build/dev.
const fs = require('node:fs');
const path = require('node:path');

const frontendDir = path.resolve(__dirname, '..');
const reportDir = path.join(frontendDir, 'app', 'reports', 'monthly', '[token]');
const excelRoute = path.join(reportDir, 'route.ts');
const obsoletePage = path.join(reportDir, 'page.tsx');

if (fs.existsSync(excelRoute) && fs.existsSync(obsoletePage)) {
  const backupDir = path.join(frontendDir, '.legacy-routes');
  fs.mkdirSync(backupDir, { recursive: true });
  let backup = path.join(backupDir, 'monthly-report-page.tsx');
  let attempt = 1;
  while (fs.existsSync(backup)) {
    backup = path.join(backupDir, `monthly-report-page-${attempt++}.tsx`);
  }
  fs.renameSync(obsoletePage, backup);
  console.log(`[ALS Ticket Tracker] Archived obsolete monthly report page to ${path.relative(frontendDir, backup)}. Excel download route kept.`);
}
