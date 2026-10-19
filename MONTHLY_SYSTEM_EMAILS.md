# Distributor monthly reports — Send System Emails

## Behavior

In **Manage Tables → Distributor column → CC rules**, tick **Send Monthly Reports** for any matching rule.
The same addresses in that CC rule become the **To** recipients of its monthly report. Regular customer emails continue using the rule's CC addresses as before.

A Railway scheduled job prepares **one pending draft per rule per completed calendar month** (including a zero-ticket report). Each report includes only tickets **created during that month** in the table containing that Distributor column, whose saved Distributor value matches the rule (case-insensitive, using the existing matching mode). The report also summarizes their current workflows as of the time the draft was queued. At most five ticket links are included to keep the email-app URL compact. Reports are fixed snapshots: changing a rule after a draft is created does not update or delete that draft.

**No email is automatically sent.** Staff must open **Send System Emails → Pending System Emails**, review the draft, open their existing email app, send it there, and explicitly click **I sent the email**. Clicking **I didn't send it** keeps it pending. Marking sent records the staff member and timestamp but is not independent confirmation of external delivery.

## Railway cron deployment (separate service)

1. Add a new Railway service from the same repository and backend directory, using the same `DATABASE_URL`, Django settings/secrets, and `FRONTEND_URL` as the backend.
2. Set the start command to:
   `python manage.py queue_monthly_distributor_reports`
3. Configure Railway **Cron Schedule**: `0 15 * * *` (every day, 15:00 UTC). The job exits when finished. The recurring daily check provides catch-up if one invocation fails; a database uniqueness constraint ensures the same rule/month cannot be enqueued twice.
4. Apply migration `0083_system_emails.py` with `python manage.py migrate` before scheduling the job.
5. In the app, an administrator can click **Check for due reports** to queue the previous month's reports on demand, useful for local testing.

The report period is based on **America/Edmonton calendar months**. Newly enabled rules do not queue months that ended before they were enabled. The previous month's draft will appear once its monthly period has closed and the scheduler/administrator has queued it.

If you only run the Django web server without the separate Railway Cron service, reports are *not automatically queued*. The dashboard only counts drafts already stored in PostgreSQL.

## Deployment caution

For sensitive customer information, confirm that CC-rule email addresses are approved report recipients. Staff should verify each draft's recipients before sending. The email app may limit URL length, so reports have a concise list of sample links rather than an unbounded list.
