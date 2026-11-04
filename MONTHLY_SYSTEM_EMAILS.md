# Brand monthly reports — Send System Emails

## Behavior

Existing Distributor CC rules are migrated to Brand rules and paused for administrator review because the matching field changes from a company name to its Brand. **Review and save these rules before they can send CCs or generate new reports.** See `BRAND_CC_MONTHLY_RULES.md`.

In **Manage Tables → Brand column → CC/monthly rules**, tick **Send Monthly Reports** for any matching rule.
The same addresses in that CC rule become the **To** recipients of its monthly report. Only tracking-link emails use these addresses as automatic CC recipients; general customer correspondence does not. Monthly reports use the same addresses as To recipients.

An authenticated app refresh prepares **one pending draft per rule per completed calendar month** (including a zero-ticket report). Each report includes only tickets **created during that month** in the table containing that Brand column, whose selected Brand sources match the rule (case-insensitive, using the existing matching mode). The report also summarizes their current workflows as of the time the draft was queued. At most five ticket links are included to keep the email-app URL compact. Reports are fixed snapshots: changing a rule after a draft is created does not update or delete that draft.

**No email is automatically sent.** Staff must open **Send System Emails → Pending System Emails**, review the draft, open their existing email app, send it there, and explicitly click **I sent the email**. Clicking **I didn't send it** keeps it pending. Marking sent records the staff member and timestamp but is not independent confirmation of external delivery.

## Send a manual report right away

In **Manage Tables → Brand column → CC/monthly rules**, save a valid rule with **Send Monthly Reports** enabled, then click **Send Monthly Report Now** underneath that rule. Unsaved rule changes must be saved first so the report uses the same filter and recipients as the database. Admin access is required.

The button prepares a **month-to-date report** (the 1st through the moment of preparation) for the same table and matching Brand pattern. It navigates straight to the prepared draft in **Send System Emails**. Review its recipients, open it in your email app, and explicitly confirm **I sent the email** after actually sending. This button **does not send email by itself**. Reports can be regenerated later as separate drafts.

Manual reports do not replace or suppress the normal scheduled report for the full month. They are distinguished as **Manual month-to-date** in the queue, and repeated HTTP requests for the same button click are deduplicated by a request UUID. Migration `0087_manual_monthly_distributor_reports.py` adds the distinction and idempotency key to the SystemEmail model.

## Automatic generation on app refresh (no cron job required)

Whenever an authenticated staff member reloads the application, the app asks the backend to check for due monthly Brand reports. It happens once per page load; moving between pages does not trigger repeated checks. A short five-minute server-side cooldown prevents repeated full scans during heavy usage. An unsuccessful check is retried on the next eligible refresh.

The backend evaluates **the previous completed month**, based on **America/Edmonton** calendar months. It creates a pending draft for each active, validated Brand rule and lab, including rules with zero matches. Newly enabled rules do not queue reports for months that ended before they were enabled. The database uniqueness constraint prevents duplicate scheduled reports for the same rule, lab, and month even if multiple workers perform checks.

All staff can trigger the background eligibility check by refreshing; **only admins** can edit Brand rules and use **Check for due reports** to force an immediate catch-up. No data from other labs is returned to the user's browser by the automatic check.

The job does **not** run at a specific time automatically. If nobody opens or refreshes the app after a reporting month ends, the report is generated the next time somebody refreshes. The actual email remains pending under **Action Required → Send System Emails** until staff send and confirm it.

**Railway:** The former `queue_monthly_brand_reports` cron service is no longer required. Disable or remove that scheduled service after deploying the updated app. The management command remains available for manual troubleshooting, but the normal web app now performs the check without it.

## Deployment caution

For sensitive customer information, confirm that Brand-rule email addresses are approved report recipients. Staff should verify each draft's recipients before sending. The email app may limit URL length, so reports have a concise list of sample links rather than an unbounded list.
