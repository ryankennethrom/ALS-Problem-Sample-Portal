# Staff Ticket Creation Time

## How it works

- The **first Create Ticket click** (or form submission by keyboard) starts a server-recorded timing session.
- The timer includes any container-fit confirmation, email drafting and review, and time that the page is left open.
- Only when the staff member confirms **I sent the email** or **I didn't send the email** **and** the backend successfully creates the ticket is that session completed and included in the report.
- If staff cancel, leave the page, lose the connection, or a creation request fails, that attempt is not included. Uncompleted sessions older than 14 days are removed when another timer starts.
- Repeated final confirmation responses cannot create duplicate timing results.
- The report groups successful creations by the **Edmonton date on which the final confirmation completed**, not by the date staff initially clicked Create Ticket. No records are backfilled for tickets created before this version was deployed.
- Time is elapsed wall-clock time (including idle time, file transfer, and email composition), **not tracked keyboard/mouse activity**.
- Deleted tickets do not erase completed timing statistics.

## Admin access

Admin sidebar → **Ticket Creation Time**. Default report: last seven calendar days including today. Administrators can select 7/30/90-day windows, choose custom dates, and filter by staff. The report shows total tickets, total elapsed time, and average time per ticket, together with per-staff and per-day breakdowns.

Backend endpoints:

- `POST /api/ticket-creation-timing/start/` — authenticated staff; creates a pending timer.
- `POST /api/problem-samples/create-prepared/` — accepts an optional `creation_timing_id` for backward compatibility and closes that timer only on successful ticket creation.
- `GET /api/admin/ticket-creation-time/?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD` — administrators only.

## Migration and tests

Apply migration `0088_ticket_creation_timings.py` with `python manage.py migrate`.

Run `python manage.py test problem_samples.test_ticket_creation_timings` against a safe local PostgreSQL test database. Frontend regression tests: `cd frontend && node --test tests/*.test.cjs` (with globally installed TypeScript available to Node).
