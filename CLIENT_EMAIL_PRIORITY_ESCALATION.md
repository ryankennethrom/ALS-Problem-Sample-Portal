# Client Email priority escalation (migrations 0101–0102)

In **Lab: All → Manage Tables → ALS Tickets → Client Email**, configure two or more dependency company fields in priority order. Enable **Make next priority email list as contact if no response after a duration** and choose a duration in hours (1–87,600). This configuration applies per Client Email column.

Each ticket stores the active email source. In the ticket editor and creator, **Current Email List: [source name]** opens a priority chooser; choosing a source loads the emails for that company's current Customer Export record, then the normal ticket save persists the choice. Changing a dependency company's value resets its prior source selection.

On an authenticated application refresh, an endpoint checks waiting tickets whose current confirmed tracking-link send is old enough. After the configured duration since the **later of the last confirmed tracking-link send or the latest customer response**, a ticket still in **Waiting for Customer Response** advances to the next *non-empty* dependency list and changes to **Follow Up Required**. **Dispose Automatically is also set to No** on escalation, stopping any active automatic-disposal countdown. The escalation history records this field change when it was previously Yes. An audit history entry records both the priority change and the reason to resend the tracking link. The app does NOT send the email for staff. If no later company has emails, the ticket stays unchanged. Other workflows are not touched.

Each confirmed tracking-link send (including a resend) restarts this response window. If **Dispose Automatically** is enabled, it also resets `automatic_disposal_started_at` to that send time. It does not enable an otherwise disabled disposal timer.

A five-minute cache cooldown limits checks; database row locks make ticket transitions idempotent across workers. A refresh is required for due changes to be evaluated; no cron worker is needed. Migration 0101 adds nullable timeout configuration and per-ticket tracking fields. Migration 0102 backfills those timestamps for existing tickets from their most recent confirmed **Sent tracking link to customer by email** history entry and latest public customer acknowledgement/response. Existing non-null timestamps are preserved. No history entry is added by this backfill. A waiting ticket whose historical response window has already expired can escalate during the next authenticated app refresh (if the rule is enabled and there is a usable next priority). Tickets without evidence of a confirmed tracking-link send remain ineligible until a new send is confirmed.

The automatic checks cannot send a tracking email, resolve absent customer email data, or replace a staff verification of the chosen recipients. Backup archives made before migration 0101 may require Restore & Upgrade.

## Older ticket migration

Run `python manage.py migrate` to apply migration 0102. The data-only migration does not change workflow or disposal timestamps directly and never sends emails. Existing waiting tickets become eligible for the normal refresh-based escalation calculation using historical send and customer-response activity. A refresh can create the normal escalation history event and move eligible tickets to **Follow Up Required**; staff must still resend tracking links manually. Historical backups restored after migration 0102 was already applied may require a separate backfill run.

## Legacy tracking-link send troubleshooting (migration 0103)

Older `Sent tracking link to customer by email` events contain the send time, but
not the original dependency priority. Migration `0103` safely reconciles missing
tracking-send timestamps from confirmed history (including records reintroduced
by restores); it does not create activity or switch workflows.

For historical tickets without an explicitly saved Client Email priority,
compare the distinct saved Client Email addresses with each configured
company's current Customer Export emails. The historical last-sent priority is
estimated as the nonempty dependency list with the **largest number of email
matches**. Priority 1 wins ties when it has usable addresses, including a tie
between later priorities. If Priority 1 has no usable addresses, ties are
resolved in favor of the earliest populated tied priority. Dependencies with
missing companies or empty email lists are never candidates. When the ticket
has no saved addresses, or all dependency email lists are empty, escalation
skips it instead of attributing the old send to an empty list. This is a
heuristic for legacy sends, not proof of which recipients received an email.
Explicitly saved priority state remains authoritative.
Future tracking-link send history records the
explicit priority selections for audit purposes.

If an existing ticket still does not escalate, run from the `backend` directory:

```bash
python manage.py diagnose_client_email_escalation --ticket-number 123
```

This prints the confirmed-send timer, current workflow, configured duration,
priority lists and the exact blocking condition. It is read-only. The ticket
must be **Waiting for Customer Response** with an elapsed deadline and at least
one later priority company that has a usable email in Customer Export. If there
are multiple tables using ticket number 123, results from all will be shown.
The automatic check is triggered by a signed-in app refresh and may be subject
to the five-minute cooldown.

## Troubleshooting an eligible legacy ticket that does not escalate

Run `python manage.py diagnose_client_email_escalation --ticket-number 56`
(replace 56 with the ticket number). An `ELIGIBLE` result means the data and
priority dependencies pass the diagnostic; it does not prove that the
on-refresh request was received or completed successfully. Refresh the
signed-in frontend, and inspect the browser Network tab for
`POST /api/system-emails/check-on-refresh/`. The response reports the two
independent checks with `monthly_reports_checked` and
`client_email_escalations_checked` flags; backend exceptions are logged.
The server-side escalation scan has a five-minute cooldown. Restored legacy
tickets whose indexed `current_workflow` and JSON `current-workflow` disagree
are now included in the candidate scan and rechecked using the effective
workflow before any ticket is changed.
