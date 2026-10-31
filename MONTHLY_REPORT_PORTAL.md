# Monthly Brand Excel Report Downloads

Monthly emails now contain a private link to an XLSX download instead of an interactive HTML report. The existing `/reports/monthly/{token}` link redirects to the public API Excel endpoint `/api/public/monthly-reports/{token}/xlsx/`, preserving previously emailed links. The endpoint checks revocation and 90-day expiry, uses `no-store` response headers, and returns a downloadable workbook.

Each Brand CC/monthly rule has optional `report_column_ids` in its existing JSON configuration. `null` or absent means all non-sensitive table columns; an array of column UUID strings restricts the worksheet to those table columns. Ticket #, current workflow, creation timestamp, and matched Brand source are always included. All selected field values are snapshotted at report generation time and remain unchanged even if an administrator later edits columns or tickets.

The workbook has separate `Summary` and `Tickets` tabs, with styled headers, text wrapping, readable row heights, an autofilter and frozen ticket identifiers. The email prominently instructs recipients to open the `Tickets` tab to see ticket rows. Values resembling spreadsheet formulas are escaped; tracking links, tokens, client emails, and sensitive credentials are excluded even if an invalid ID is supplied. Each selected lab generates its own report, and staff must still send the email manually.

No database migration is required for this release because selection is stored in the existing `ProblemColumn.brand_cc_rules` JSON field and the snapshot is stored in the existing `SystemEmail.report_snapshot` JSON field. Previous queued reports remain downloadable as Excel from their saved snapshots.

## Upgrade note for Next.js route collision

Older installs may retain `frontend/app/reports/monthly/[token]/page.tsx` when using `cp -a`. The Excel release uses `route.ts` at that path, and Next.js cannot build both files together. `npm run dev` and `npm run build` now run `frontend/scripts/cleanup-stale-routes.cjs` first, which archives the obsolete page in `frontend/.legacy-routes/` and preserves the Excel route. You can also remove the obsolete `page.tsx` manually before starting Next.js. No backend or database changes are needed.
