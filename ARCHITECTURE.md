# Architecture

## MVP

```text
Ontario customer service / Edmonton laboratory
                  |
                HTTPS
                  |
          Next.js frontend
                  |
             Django API
          /        |        \
 magic-link auth PostgreSQL   Customer Export
                  |
        ProblemTable
            |
      ProblemColumn[]
            |
      ProblemSample[]
       + custom_values JSON
```

`ProblemTable` is the list/table definition. `ProblemColumn` defines user-created typed fields for one table. `ProblemSample.custom_values` stores the per-row values keyed by immutable `ProblemColumn.field_key` values.

### Optional column explanations

`ProblemColumn.description` stores optional user-facing help text. The frontend renders a reusable `(i)` information control anywhere a column is directly presented to row users (create/edit labels, table headers, and Quick Filters). Blank descriptions render no information control.

This hybrid approach keeps the existing ALS Problem Sample fields strongly typed/indexable while allowing users to extend each table without database schema migrations.

## Database

The application database is PostgreSQL. Django reads the connection from `DATABASE_URL`; the local development default is `postgresql://problem_sample_tracker:problem_sample_tracker@127.0.0.1:5432/problem_sample_tracker`. Hosted environments can provide their own PostgreSQL URL without code changes. The backend uses `dj-database-url` for connection parsing and Psycopg 3 as the database driver.

Django migrations remain the source of truth for the relational schema. Dynamic problem-sample columns continue to live in `ProblemColumn` plus `ProblemSample.custom_values`, so user-created table fields do not require PostgreSQL schema changes. A legacy `db.sqlite3` may be retained temporarily only for one-time data export during migration; it is no longer the default application database.

## Production direction

```text
Microsoft Entra ID
       |
Azure App Service / approved ALS hosting
       |
Django API + Next.js
       |
approved Azure SQL/API integration
```

Authentication, hosting, email delivery, and customer-system access can be swapped later without redesigning the dynamic-table model.

- Every table has one protected built-in column: `Problem ID`. Constant values such as a lab/site name should use the general-purpose `Fixed Value` column type. `Row Creator` is a server-controlled read-only column that stores the original creator's email for each row.

## Row activity history

Each problem sample has an immutable activity stream stored in `ProblemHistory`. Creating a row, saving row changes, adding a follow-up comment, and confirming that the initial customer notification email was sent append a new history event with the authenticated actor and timestamp. Update events store before/after values for fields that changed. Clicking **I sent the email** in the post-create notification confirmation records a dedicated `customer_notification` activity; clicking **I didn't** does not. The row detail screen renders this history above the editable problem fields, comments, and row-information panels.


## Customer Export snapshot semantics

The Customer Export is treated as a complete snapshot. `CoyId`, `Company`, `Email`, and the other imported columns are not assumed to be unique. A successful import atomically replaces the prior customer directory and bulk-inserts every non-empty source row, including duplicate rows. This prevents repeated exports from accumulating duplicates while preserving the source data exactly enough for Distributor, End User, and Client Email lookup behavior.

## Group columns

A dynamic column may use type `group` and configure `group_role` as either `lab_technician` or `customer_service`. Row values store the selected registered employee email. The API validates new assignments against the current user profile role, and the frontend renders only users from the configured group.

## Prioritized Client Email dependencies

`ProblemColumn` supports the `client_email` type plus an ordered `client_email_dependencies` JSON list of ProblemColumn UUIDs. The legacy `depends_on_column` foreign key remains synchronized to the first dependency for backward compatibility. Row values are JSON lists of email strings in `ProblemSample.custom_values`; the serializer still accepts legacy single-string values and normalizes edited values to lists.

The frontend submits populated dependency-company values to `GET /api/customers/client-emails/suggest/` in configured priority order. The endpoint selects the first company that has at least one imported email and falls through when a higher-priority company has none. Empty query text returns all unique emails for the active company and seeds an uninitialized row. Fuzzy query text is only a visual filter/discovery mechanism; it does not change the active dependency company.

The row editor owns the final email list. Users can keep/delete selected addresses, clear all, or add a syntactically valid email that is not present in the latest Customer Export. Backend validation therefore validates the list's email syntax rather than enforcing customer-directory membership. When dependency configuration changes, existing values are marked uninitialized so the next editor session can seed the list from the new source company.

Customer email composition is frontend-driven through `frontend/lib/customerEmail.ts`. A single-recipient message performs an exact email lookup through the customer-directory endpoint and personalizes the greeting only when that address resolves to one unambiguous `PrimaryContact`. Multi-recipient messages intentionally use a generic greeting. Both modes build a concise detail block from the dynamic problem table, prioritizing received date, sample tracking, sample count, problem type, issue description, and courier fields, with a small fallback set for custom schemas.

- Customer Export header matching and `CoyType` values are normalized (for example `CoyType`, `Coy Type`, `Coy-Type`, `DISTRIBUTOR`, and extra whitespace all resolve consistently).


## Customer notification fields
Table columns have an **Include in customer notification** option. Problem ID is always included automatically; other row fields appear in the generated customer email only when this option is enabled. Customer greetings use **Dear valued customer,**.


## Problem row files
Problem sample rows support multiple images (JPEG, PNG, GIF, WebP) and general file attachments. Files are uploaded through authenticated DRF row actions and stored through Django's configured file-storage backend. The included development configuration uses `backend/media/`; production deployments should point Django storage at persistent object/blob storage rather than an ephemeral application filesystem. Each file is limited to 25 MB.


## Customer notification files
Problem-row images and attachments remain stored with the sample but are not attached to customer notification emails. **Email Customer** always uses the normal `mailto:` flow. When the saved Problem Sample Tracking Link is valid, the public Problem Sample Tracking page displays image previews and protected download links for all files stored on that sample.

- Read-only fields in problem sample create/edit forms (including Problem ID, Fixed Value, and Row Creator columns) are visually greyed out.


### Recent Row Modifier column
A `Recent Row Modifier` column is server-controlled and read-only. It contains the email (or username fallback) of the authenticated user who most recently saved the problem-sample row. Existing rows are backfilled from `modified_by` / legacy modifier metadata, falling back to creator metadata when needed.


### Brand column type
Brand columns use fuzzy suggestions from distinct Brand values in the latest imported Customer Export. Saved values are validated against that directory, while unchanged historical values remain valid if a later export removes a brand.


### Problem sample row deletion
- A problem sample can be permanently deleted from its detail/editor page with **Delete Row**.
- Deletion requires a second confirmation in a destructive-action dialog.
- Django deletes related comments and history through cascading relationships. Related image/attachment records are also deleted, and their stored files are removed by the existing post-delete cleanup handlers.
- The table's `next_problem_id` counter is not decremented, so a deleted Problem ID is not reused.

## Customer notification template

`frontend/lib/customerEmail.ts` owns the Problem Samples Automation customer-message template. It dynamically resolves common row labels (Problem Type, ALS Sample Tracking Number, Reason for Hold/Issue Description, Date Received), uses Problem Type + Problem ID in the subject, and adds a primary-contact disclaimer when multiple customer recipients are selected. Other columns that are explicitly enabled for customer notification remain included as additional information. The browser `mailto:` draft uses this same content builder. The create and detail flows use a two-stage confirmation: first a preparation dialog waits for **OK** before opening the user's email application; after preparation, a separate confirmation dialog asks whether the employee actually sent the message. Backend notification history/status changes are triggered only by the second dialog's **I sent the email** action.

## Containers and problem sample expiration

`ProblemContainer` provides a stable human-facing ID derived from its database sequence (`PC-000001`, `PC-000002`, ...). `ProblemSample.container` links each new row to a container while remaining nullable for legacy/imported data. The authenticated container API is available under `/api/problem-containers/`, including exact ID lookup.

`ProblemTable.pt_days` stores the configurable Problem Sample Expiration Period in days, defaulting to 30. Zero is valid and means the sample is immediately up for disposal when automatic disposal is activated. `ProblemSample.customer_notified_at` records the first confirmed customer-notification send. The derived expiration time is:

```text
automatic_disposal_started_at + ProblemTable.pt_days
```

`automatic_disposal_started_at` is reset whenever Status transitions into `Automatically Disposed`. The first confirmed customer email normally causes that initial transition, so it starts a fresh expiration period; resending the email while the row is already `Automatically Disposed` does not reset it. The container API aggregates sample states into `empty`, `active`, `partially_expired`, or `all_expired`; `all_expired` is true only when the container has at least one sample and every sample is expired.

### Status and container disposal workflow
Status is a fixed application-level workflow field. Each table has a system `ProblemColumn(field_key="status", column_type="choice")` with exactly eight choices: `Automatically Disposed`, `Halted Automatic Disposal`, `To be Disposed`, `To be shipped back to client`, `To be back to testing`, `Back to testing`, `Disposed`, and `Shipped back to client`. Users cannot add, rename, or remove Status choices. Migration `0036_automatic_disposal_statuses` maps the three former customer-contact statuses into this two-state automatic-disposal model and updates each table's fixed Status choices/default.

Container readiness is computed from current row state after excluding samples whose Status is `Shipped back to client`. At least one non-ignored sample must remain, and every remaining sample must either be `To be Disposed`, or have Status `Automatically Disposed` together with `expiration_status == "expired"`. `Halted Automatic Disposal`, `To be shipped back to client`, `To be back to testing`, and `Back to testing` are not automatically disposal-eligible. `POST /api/problem-containers/{id}/dispose/` is transactional, refuses non-ready/empty-workload containers, captures a JSON rollback snapshot only for samples it will change, sets those samples to `Disposed`, leaves `Shipped back to client` samples unchanged, updates Recent Row Modifier values for changed rows, writes row History entries, and stamps `disposed_at`/`disposed_by` on the container. `POST /api/problem-containers/{id}/undo-disposal/` restores only the snapshot-participating samples transactionally, clears the disposal stamp/snapshot, and records row History entries. It refuses to roll back if a sample changed by disposal no longer has Status `Disposed`, preventing an undo from overwriting later changes. For legacy disposed containers without a snapshot, the endpoint can fall back to the latest matching disposal History record to recover the prior Status.


### Changing a problem sample container
An existing problem sample can be moved to another active container from its detail/editor page by changing **Container ID** and choosing **Save Changes**. The API validates the target Container ID and records the old and new Container IDs in row History. Because container readiness is derived from current membership, both the source and destination container readiness states reflect the move immediately. Samples cannot be moved into or out of a disposed container; undo the container disposal first. New samples also cannot be assigned to a disposed container.

### Public customer acknowledgement
`ProblemSample` has an opaque high-entropy acknowledgement token generated with `secrets.token_urlsafe(48)` (about 384 bits of randomness), an acknowledgement timestamp, and optional `customer_acknowledgement_action` (`dispose`, `ship_back`, or `hold`). Public GET/POST endpoints live under `/api/public/problem-sample-tracking/<token>/` with `AllowAny`; the token itself is the customer credential and there is no separate access code or acknowledgement button. A GET only displays the page and choices, so passive link previews do not acknowledge a sample. For unresolved rows whose Status is `Automatically Disposed`, the GET payload includes the current days-until-disposal countdown and the frontend presents **Stop eventual disposal** (`hold` → `Halted Automatic Disposal`), **Permit immediate disposal** (`dispose` → `To be Disposed`), and **Ship back** (`ship_back` → `To be shipped back to client`). At zero days the page says the sample(s) are up for disposal now. Other unresolved pre-response states retain the generic action labels. The first POST records acknowledgement and the selected action atomically. The frontend public route is `/track/<token>`. Migration `0043_secure_acknowledgement_token` moves the token from UUID storage to a unique URL-safe string field and preserves existing UUID-based URLs. Migration `0044_remove_customer_access_code_hold_sample` removes the old acknowledgement-code field and migrates the old `neither` action to `hold`. The public acknowledgement/action window is fixed at 30 days from the most recent qualifying Status transition. Workflow Status `Disposed` takes precedence and changes the public state to **Problem Sample Dumped**; `Shipped back to client` shows **Shipping samples back to client**; expiration-period expiry by itself does not.


Expired acknowledgement credentials are destructive: after the 30-day window, `acknowledgement_token` is set to `NULL`. Middleware runs the purge before backend requests, and migration 0031 purges rows already expired at deployment time.

## Customer-notification acknowledgement credential lifecycle

Acknowledgement tokens are not model defaults. `ProblemSample.acknowledgement_token` defaults to `NULL`. `POST /api/problem-samples/{id}/customer-notification-credentials/` returns an unsaved secure token/link for composing a message (or reuses an already-persisted token from a prior confirmed send). `POST /api/problem-samples/{id}/customer-notification-sent/` validates and saves a newly prepared token only when the employee confirms **I sent the email**. Until then the public token lookup has no matching database row and returns 404. Migration `0033` removed legacy default-generated credentials from rows where `customer_notified_at` is null; migration `0044` removes the obsolete acknowledgement-code column.


### System-owned Customer emailed status
`Automatically Disposed` means automatic disposal is active; its countdown is based on the most recent transition into that Status plus the table's Problem Sample Expiration Period. `Halted Automatic Disposal` means that automatic disposal is stopped and is the default for new samples. The first confirmed **I sent the email** action records the notification time and changes Status to `Automatically Disposed`; later resend confirmations do not restart expiration unless Status transitions into `Automatically Disposed` again. Customer acknowledgement is tracked independently by `acknowledged_at`; the selected customer action then determines whether the sample is halted, immediately routed to disposal, or routed to shipping.


## Shipping-back and disposal behavior

- Fixed status `To be shipped back to client` represents a pending customer return.
- The public **Ship back samples** action transitions to that pending status.
- `Shipped back to client` samples are excluded from container disposal-readiness checks.
- Container disposal does not mutate `Shipped back to client` samples and snapshots only samples actually changed to `Disposed`.

### Shipping queue and bulk completion

The authenticated staff route `/shipping/to-be-shipped` is backed by `GET /api/problem-samples/to-be-shipped/`, which returns a lightweight representation of rows whose effective workflow Status is `To be shipped back to client`. `POST /api/problem-samples/bulk-ship-back/` accepts one or more problem-sample UUIDs, locks the selected rows transactionally, verifies that every row is still pending shipment, and changes each to `Shipped back to client`. The action also updates server-controlled Recent Row Modifier columns, invokes the existing acknowledgement-status lifecycle transition, and creates a row History event. A stale selection is rejected as a unit rather than partially updating rows. The frontend supports search, individual selection, and Select all visible.

## Follow-Up Required queue

The Problem Samples navigation includes **Follow-Up Required**, a cross-table oldest-first queue that excludes disposal and shipping workflow states. The testing states `To be back to testing` and `Back to testing` remain in Follow-Up Required.

### Back To Testing queue

The authenticated route `/back-to-testing/to-be-back-to-testing` is backed by `GET /api/problem-samples/to-be-back-to-testing/`. `POST /api/problem-samples/bulk-back-to-testing/` accepts one or more problem-sample UUIDs, locks them transactionally, verifies every row is still `To be back to testing`, and changes each row to `Back to testing`. It also updates Recent Row Modifier columns, applies tracking-link status timing, and writes a per-row History event. A stale selection rejects the whole batch.

Migration `0035_back_to_testing_statuses` updates existing system Status-column choice lists to the nine-value vocabulary.

- Follow-Up Required displays a prominent Oldest problem sample requiring follow up indicator based on the oldest row in the current filtered result set; it refreshes the displayed age every minute and reacts to table selection, basic search, Quick Filters, and Advanced Search.

## Follow-Up automatic-disposal warning

`ShippingProblemSampleSerializer` exposes `pt_days` and `days_until_automatic_disposal` for queue views. The countdown is only populated while a sample is in `Automatically Disposed`, matching `ProblemSample.is_disposal_eligible`; other follow-up states do not have an automatic-disposal timer. The Follow-Up Required page maps the remaining fraction of the configured expiration period into progressively stronger warning row backgrounds and shows `Eligible now` at zero days.

## Disposal workspace

- Frontend routes:
  - `/disposal/containers` and `/disposal/containers/ready-to-dispose` use `ContainersView`.
  - `/disposal/samples` provides server-ranked problem-sample search and single/bulk disposal actions.
  - `/containers` and `/containers/ready-to-dispose` remain redirect-only compatibility routes.
- Problem sample API actions:
  - `GET /api/problem-samples/disposal-search/?q=...` returns ranked compact problem-sample rows.
  - `POST /api/problem-samples/bulk-dispose/` accepts `problem_ids` and atomically sets non-disposed samples to `Disposed` after validation.
- `ProblemContainerSerializer` and container disposal ignore workflow states `Disposed` and `Shipped back to client` when computing the remaining physical disposal workload.

## Workflow queue search

`frontend/lib/workflowQueueSearch.ts` centralizes normalized workflow-queue text matching and client-side advanced-filter evaluation. `frontend/components/WorkflowQueueAdvancedSearch.tsx` provides the shared Advanced Search UI used by Follow Up Required, Dispose Samples, To be shipped, and To be back to testing.

Backend fuzzy search recognizes user-facing Problem ID forms through `problem_number_from_query()` in `backend/problem_samples/search.py`. `GET /api/problem-samples/disposal-browse/` supplies the Dispose Samples candidate set when advanced conditions are used without a basic search query.


### Customer notification files
Images and attachments remain stored with problem samples, but **Email Customer** always opens the normal `mailto:` email-client flow. Stored files are not attached to customer notification emails and no `.eml` draft is generated because files exist on the sample. The public Problem Sample Tracking page shows those stored images/files through token-scoped endpoints while the Problem Sample Tracking Link remains valid; after link expiry/token purge, those endpoints return not found.

- Customer notification emails tell recipients that the Problem Sample Tracking page may contain images or files associated with the problem sample(s).

## Staff change reasons

Manual staff mutations of an existing ProblemSample require an `X-Change-Reason` request header (maximum 1000 characters). This requirement is enforced for ProblemSample PATCH updates and the staff workflow endpoints that dispose samples, ship samples, return samples to testing, dispose containers, or undo container disposal. The reason is stored under `ProblemHistory.details.reason`; no schema migration is required. Customer/public acknowledgement actions and system-controlled email-status transitions are excluded. `x-change-reason` is included in the Django CORS allow-list for the separate frontend/backend development origins.

## Problem sample creation timestamp

- `ProblemSample.created_at` is the canonical read-only Date Created field.
- It is displayed in the main problem-sample table, Follow Up Required, Dispose Samples, To Be Shipped, To Be Back to Testing, and the individual row detail page.
- No duplicate date field is stored in `custom_values`; the existing model timestamp is used.

### Follow Up Required table scoping

`GET/POST /api/problem-samples/follow-up-required/` requires a real ProblemTable id (`table`). GET supports the basic `q` search; POST supports the table-schema Advanced Search payload. Both paths restrict candidates to the selected table relation and then to follow-up workflow states. The frontend loads `/problem-tables/`, presents an explicit table selector, and renders `selectedTable.columns` directly.


## Halted automatic disposal default

New problem samples default to **Halted Automatic Disposal**. Migration `0037_halted_automatic_disposal_default.py` updates existing Status-column defaults and the model-level default without changing the workflow status of existing problem-sample rows. The halted workflow state does not by itself mean the customer has acknowledged; acknowledgement remains tracked by `acknowledged_at`, and a default-halted sample remains unacknowledged until the customer selects one of the public-link actions.

- `Days until up for disposal` is a system `ProblemColumn` (`system-days-until-automatic-disposal`, position 2) computed from `ProblemSample.days_until_automatic_disposal`; it is read-only and follows `Status` in every table.


### Automatic disposal expiration anchor
- Entering **Automatically Disposed** always starts a fresh Problem Sample Expiration Period.
- The first confirmed customer email changes a halted sample to **Automatically Disposed**, so that first transition starts the period.
- Saving a row that is already **Automatically Disposed** does not reset the period; the status must actually transition into it.
- Customer acknowledgement changes the sample to **Halted Automatic Disposal**. A later staff transition back to **Automatically Disposed** starts another fresh period.

### Staff change reason UI

`frontend/components/ChangeReasonModal.tsx` provides the shared promise-based reason modal used by row edits, sample disposal, shipping, back-to-testing, container disposal, and undo disposal. `frontend/lib/changeReason.ts` only emits the `X-Change-Reason` header when a non-empty reason was supplied. Backend `problem_samples.views._change_reason` treats the reason as optional and `._history_details` adds it to history only when present.

### Customer acknowledgement history

The public problem sample tracking endpoint writes a `ProblemHistory` action of `acknowledged` with summary `Customer acknowledged problem sample`. Its `details.changes` list records user-visible row fields changed by acknowledgement, currently Status when the workflow status transitions. The problem detail History renderer displays change lists for acknowledged actions as well as staff updates and customer-email events.


## Customer notification history changes

The `customer-notification-sent` action stores visible row changes in `ProblemHistory.details.changes`. The first confirmed email records both the Status transition into `Automatically Disposed` and the resulting built-in `Days until up for disposal` display value. The problem detail History UI renders `changes` for customer-notification events; resends that cause no row changes do not fabricate change entries.

### Follow Up Required quick filters

`frontend/app/follow-up-required/page.tsx` derives Quick Filters from the selected `ProblemTable.columns`, limited to Choice columns with configured choices. Active values are submitted as `quick_filters` to `POST /problem-samples/follow-up-required/` whenever quick or advanced filters are active. `ProblemSampleViewSet.follow_up_required` passes those conditions into the shared `advanced_search_problem_samples` implementation, keeping table scoping and workflow-status filtering server-side.


## Authentication

Staff login uses single-use email sign-in links. Each link carries a `secrets.token_urlsafe(48)` token (about 384 bits of entropy); only its SHA-256 hash is stored in `LoginLink`. Links expire after 5 minutes and are consumed atomically on the first successful verification. Requesting a new link invalidates any older unused link for that email. The frontend removes the token from the visible URL/history before exchanging it for the normal app session token. New users choose their role from My Account immediately after their first verified sign-in.

- Login verification is guarded so React development Strict Mode cannot redeem the same one-time sign-in link twice.


## Login verification link redirect behavior
After a staff login link is successfully exchanged, the frontend uses a full browser redirect so the verification page is immediately replaced by the portal. Existing users go to the portal home page; first-time users who still need to select a role go to My Account.

- When using Django's console email backend locally, the backend prints a separate clean `LOCAL DEVELOPMENT SIGN-IN LINK` because the raw MIME email may display quoted-printable encoding such as `=3D` and soft line breaks.


## Persistent problem sample tracking links
- Each problem sample row has at most one secure tracking token/link. Once saved, that same link is reused.
- Tracking tokens are never purged from the database. Expiry controls public accessibility only.
- The tracking link expires 30 days after the latest Status transition into To be Disposed, Disposed, To be shipped back to client, Shipped back to client, To be back to testing, or Back to testing. Each later transition into one of those statuses resets the 30-day expiry.
- Halted Automatic Disposal and Automatically Disposed do not themselves start/reset tracking-link expiry.
- Every problem-sample table has read-only built-in Tracking Link and Tracking Link Expiry columns.

- Returning a problem sample to `Automatically Disposed` or `Halted Automatic Disposal` clears the active tracking-link expiry and makes the same persistent tracking link accessible again.

### Required first-login role gate
`AppShell` renders `RequiredRoleModal` whenever `/api/auth/me/` reports `needs_role=true`. The modal blocks the protected portal with no dismiss action until the user explicitly selects Lab Technician or Customer Service and the PATCH to `/api/auth/me/` succeeds. Existing role-bearing accounts bypass the gate.

### Migration graph compatibility

`problem_samples` migration `0047_merge_tracking_link_migration_branches` merges the earlier acknowledgement-token field branch with the persistent tracking-link lifecycle branch. Both branches are intentionally retained so existing development databases and clean installations converge on one leaf migration.

- Customer tracking options are status-aware: Automatically Disposed shows **Stop eventual disposal**, **Permit immediate disposal**, and **Ship back**; the exact customer-facing choice label is preserved in the response/history.
- Staff-facing Tracking Link values wrap within their grid column so long secure URLs do not overflow the problem-sample form.


### Customer tracking actions by follow-up status
- **Automatically Disposed:** Stop eventual disposal, Permit immediate disposal, Fill out requested information (if applicable), or Ship back.
- **Halted Automatic Disposal:** Permit immediate disposal, Fill out requested information (if applicable), or Ship back.
- **Fill out requested information (if applicable)** sets the problem sample to **To be back to testing**.
- Returning/staying in **Halted Automatic Disposal** keeps the current halted-state choices available on the tracking page, so a customer can later permit disposal, provide requested information, or request shipment back.


### Customer tracking response signatures
Public Problem Sample Tracking Link responses require a non-empty typed-name signature (maximum 200 characters). The frontend disables workflow-action buttons until a name is entered, and the backend independently rejects unsigned responses. Each submitted name is stored in the corresponding `ProblemHistory.details.customer_signature` value so it remains tied to the exact customer action. Successful submissions clear the input so a later response must be signed again.

- Customer **Fill out requested information (if applicable)** responses open a required multiline modal (up to 4000 characters); the submitted information and typed-name signature are saved with the History event before the row moves to **To be back to testing**.

## Next.js search-parameter boundaries
The root problem-sample table page renders its search-param-dependent content through `Suspense`. The New Problem Sample route also wraps `ProblemForm`, which reads the `table` query parameter, in `Suspense`. Keep this boundary when changing either route so Vercel/Next.js production prerendering remains valid.
