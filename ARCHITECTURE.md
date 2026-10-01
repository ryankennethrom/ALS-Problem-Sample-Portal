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
 username/password auth PostgreSQL   Customer Export
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


### Intercolumn Value Controller
`ProblemColumn.column_type = intercolumn_controller` stores a normal row-local text value plus an `intercolumn_rules` JSON list. Each rule identifies another column UUID, a direction (`other_to_controller`, `controller_to_other`, or `both`), and typed trigger/assignment values for the enabled direction(s). The column serializer canonicalizes and validates rule values against the referenced column before persistence. Supported referenced fields are scalar intrinsic types and the editable Status/Current Workflow/Dispose Automatically built-ins; read-only/computed, directory-backed, and multi-value fields are excluded.

`apply_intercolumn_rules_to_values()` evaluates all controller rules in column/rule order until the row reaches a fixed point. It also preserves the workflow invariant that routed/terminal Current Workflow values force Dispose Automatically to No. Repeated states/non-convergence raise a validation error rather than choosing an arbitrary result. `ProblemSampleSerializer` applies the engine on normal row writes; the acknowledgement/workflow lifecycle helper applies it to system/customer workflow transitions. Table Settings applies changed rule definitions across existing rows and records System history for resulting value changes. Referenced columns are protected from deletion or type changes until their rules are removed.

### Recent Row Modifier column
A `Recent Row Modifier` column is server-controlled and read-only. It contains the email (or username fallback) of the authenticated staff user who most recently saved the problem-sample row, or `Customer` when the most recent row change came from the public tracking link. Customer-originated changes clear the stale `modified_by` staff reference and update the row modification timestamp; the next authenticated staff save replaces `Customer` with that staff user's email/username. Existing rows are backfilled from `modified_by` / legacy modifier metadata, falling back to creator metadata when needed.


### Brand column type
Brand columns use fuzzy suggestions from distinct Brand values in the latest imported Customer Export. Saved values are validated against that directory, while unchanged historical values remain valid if a later export removes a brand.


### Problem sample row deletion
- A problem sample can be permanently deleted from its detail/editor page with **Delete Row**.
- Deletion requires a second confirmation in a destructive-action dialog.
- Django deletes related comments and history through cascading relationships. Related image/attachment records are also deleted, and their stored files are removed by the existing post-delete cleanup handlers.
- The table's `next_problem_id` counter is not decremented, so a deleted Problem ID is not reused.

## Customer notification template

`frontend/lib/customerEmail.ts` owns the editable **Send Tracking Link** template, including recipient and row details. The create form now saves the ticket directly without generating a token or opening email. On the detail page, Send Tracking Link prepares a server-issued token, opens a mailto draft, and activates the token only on confirmed send. A separate editable **Email Customer** modal sends general correspondence without including a link or changing notification/disposal state.

## Containers and problem sample expiration

`ProblemContainer` provides a stable human-facing ID derived from its database sequence (`PC-000001`, `PC-000002`, ...). `ProblemSample.container` remains nullable at the model and API layers, including API-created tickets. The frontend new-ticket form requires an existing or newly created container ID. The authenticated container API is available under `/api/problem-containers/`, including exact ID lookup.

`ProblemTable.pt_days` stores the configurable Problem Sample Expiration Period in days, defaulting to 30. Zero is valid and means the sample is immediately up for disposal when automatic disposal is activated. `ProblemSample.customer_notified_at` records the first confirmed customer-notification send. The derived expiration time is:

```text
automatic_disposal_started_at + ProblemTable.pt_days
```

`automatic_disposal_started_at` is reset whenever the required built-in `Dispose Automatically` value changes from `No` to `Yes`. The first confirmed customer email normally causes that initial change, so it starts a fresh expiration period; resending the email while automatic disposal is already enabled does not reset it. The container API aggregates sample states into `empty`, `active`, `partially_expired`, or `all_expired`; `all_expired` is true only when the container has at least one sample and every sample is expired.

### Current Workflow, Status, and container disposal
`Status` is a required built-in descriptive choice field with six immutable values: `NEW`, `IN PROGRESS`, `ON HOLD`, `SHIPPED BACK TO CLIENT`, `DISPOSED`, and `COMPLETED`. Routing is owned by a separate required system `ProblemColumn(field_key="current-workflow", column_type="choice")` and the indexed `ProblemSample.current_workflow` mirror. Its immutable values include `CS Follow-Up`, `To be Disposed`, `To be shipped back to client`, `To be back to testing`, `Back to testing`, `Disposed`, and `Shipped back to client`. Automatic-disposal state is separate again in the required system `ProblemColumn(field_key="dispose-automatically")`, whose immutable choices are `Yes` and `No`. Workflow endpoints, queues, public customer actions, container readiness, automatic disposal, and tracking-link expiry read/write Current Workflow instead of descriptive Status. Migration `0065_optional_container_testing_workflow` restores the pending testing choice to existing tables and detaches legacy tickets already in final shipping/testing workflows.

Container readiness is computed from every attached ticket's persisted **Current Workflow**. At least one ticket must be attached and all attached tickets must be `To be Disposed` or `Disposed`. An expired `Dispose Automatically = Yes` countdown is first persisted as `Current Workflow = To be Disposed` and `Dispose Automatically = No`. `POST /api/problem-containers/{id}/dispose/` is transactional, refuses non-ready/empty containers, captures a JSON rollback snapshot only for `To be Disposed` tickets, changes those tickets to `Disposed`, and stamps `disposed_at`/`disposed_by` on the container. A container with only `Disposed` tickets can be stamped as disposed. `POST /api/problem-containers/{id}/undo-disposal/` restores snapshot-participating tickets, clears the stamp/snapshot, and records History. For legacy disposed containers without a snapshot, the endpoint can fall back to disposal History to recover prior workflow.


### Changing a problem sample container
An existing problem sample can be moved to another active container or detached by changing or clearing **Container ID** and choosing **Save Changes**. New tickets created through the frontend require a container, while the API permits unassigned tickets. The API validates a supplied ID and records container changes in row History. Completing `Shipped back to client` or `Back to testing` automatically detaches the ticket, both through the detail editor and through the bulk shipping action. A database constraint enforces this for final states; pending shipping/testing tickets remain attached until completed. Samples cannot be moved into or out of a disposed container; undo the container disposal first.

### Public customer acknowledgement
`ProblemSample` has an opaque high-entropy tracking token generated with `secrets.token_urlsafe(48)` and an optional `customer_acknowledgement_action`. Public GET/POST endpoints live under `/api/public/problem-sample-tracking/<token>/` with `AllowAny`. When `Current Workflow = CS Follow-Up`, tracking-page choices are driven by the separate `Dispose Automatically` Yes/No field. A due automatic-disposal countdown is persisted as `Current Workflow = To be Disposed` before the public payload is generated; descriptive Status is preserved. The first customer POST records acknowledgement and applies the selected workflow action atomically.


Expired tracking links remain stored but public endpoints reject them after the 30-day window. Revocation explicitly removes the link row so the old token is unusable even if the workflow later returns to CS Follow-Up.

## Customer-notification acknowledgement credential lifecycle

Acknowledgement tokens are not model defaults. `ProblemSample.acknowledgement_token` defaults to `NULL`. `POST /api/problem-samples/{id}/customer-notification-credentials/` returns an unsaved secure token/link for composing a message (or reuses an already-persisted token from a prior confirmed send). `POST /api/problem-samples/{id}/customer-notification-sent/` validates and saves a newly prepared token only when the employee confirms **I sent the email**. Until then the public token lookup has no matching database row and returns 404. Migration `0033` removed legacy default-generated credentials from rows where `customer_notified_at` is null; migration `0044` removes the obsolete acknowledgement-code column.

`POST /api/problem-samples/{id}/revoke-tracking-link/` locks the ticket and deletes its current `ProblemTrackingLink`, clears any stale pending token, and writes a History entry. Existing public GET/POST and file URLs then return 404, including after later workflow changes. The next prepared tracking email generates a fresh token. `POST /api/problem-samples/{id}/customer-message-sent/` records a confirmed general email with recipients and subject; it never invokes link creation, `customer_notified_at`, or automatic-disposal lifecycle changes. Only Send Tracking Link uses the editable tracking email template. The frontend create flow posts the ticket directly before exposing these distinct actions on its detail page.


### System-owned Customer emailed status
`Dispose Automatically = Yes` means automatic disposal is active; its countdown is based on the most recent `No → Yes` change plus the table's Problem Sample Expiration Period. `No` stops automatic disposal and is the default for new samples. The first confirmed **I sent the email** action records the notification time and sets this field to `Yes`; later resend confirmations do not restart expiration unless the field is changed back to `No` and then to `Yes` again. Customer acknowledgement is tracked independently by `acknowledged_at`; the selected customer action then determines whether the sample is halted, immediately routed to disposal, or routed to shipping.


## Shipping-back and disposal behavior

- Fixed Current Workflow `To be shipped back to client` represents a pending customer return.
- The public **Ship back samples** action transitions Current Workflow to that pending value.
- `Shipped back to client` samples leave their container when shipping completes.
- Container disposal checks all attached tickets and changes only `To be Disposed` tickets to `Disposed`.

### Shipping queue and bulk completion

The authenticated staff route `/shipping/to-be-shipped` is backed by `GET /api/problem-samples/to-be-shipped/`, which returns a lightweight representation of rows whose Current Workflow is `To be shipped back to client`. `POST /api/problem-samples/bulk-ship-back/` accepts one or more problem-sample UUIDs, locks the selected rows transactionally, verifies that every row is still pending shipment, and changes each to `Shipped back to client`. The action also updates server-controlled Recent Row Modifier columns, invokes the existing acknowledgement-status lifecycle transition, and creates a row History event. A stale selection is rejected as a unit rather than partially updating rows. The frontend supports search, individual selection, and Select all visible.

## CS Follow-Up queue

The Problem Samples navigation includes **CS Follow-Up**, a cross-table oldest-first queue containing only rows whose **Current Workflow** is `CS Follow-Up`.

### Back To Testing notification

Public customer tracking uses a server-generated 48-byte `secrets.token_urlsafe` capability token. New staff email drafts save an unactivated pending token and only activate it after send confirmation. Migration `0061_secure_public_tracking` rotates historical shorter tokens; tickets that had been emailed receive a history entry instructing staff to resend the link. Public reads, responses, and file downloads pass through a database-backed per-IP and per-token rate limiter before row lookups. The public POST locks the ticket row before applying a customer action, so concurrent submissions cannot overwrite each other. Tracking pages and public responses use `Referrer-Policy: no-referrer` and `Cache-Control: no-store`. The proxy trust hop setting must reflect the actual ingress before forwarded client addresses are used for limits.

The `/to-be-back-to-testing` queue lists tickets whose Current Workflow is `To be back to testing`, using `GET /api/problem-samples/to-be-back-to-testing/`. It uses the same search, advanced filters, selection, and Select all visible controls as `/shipping/to-be-shipped`. Customer requested-information responses enter this pending workflow while retaining their container. `POST /api/problem-samples/bulk-back-to-testing/` locks and validates the entire selected batch before moving tickets to final `Back to testing` and detaching them from containers. A shared NA.EDM email preview requires a sent decision (message and current configured recipient) or a required not-sent reason; the endpoint records each outcome and change in per-ticket History. Single-ticket updates still require the same email decision. `POST /api/problem-samples/{id}/back-to-testing-notification/` records a later confirmed NA.EDM notification. The older `/back-to-testing` endpoint remains available for existing clients.

- CS Follow-Up displays a prominent Oldest problem sample requiring follow up indicator based on the oldest row in the current filtered result set; it refreshes the displayed age every minute and reacts to table selection, basic search, Quick Filters, and Advanced Search.

## Follow-Up automatic-disposal warning

`ShippingProblemSampleSerializer` exposes `pt_days` and `days_until_automatic_disposal` for queue views. The countdown is only populated while `Dispose Automatically = Yes`; rows with automatic disposal disabled do not have an automatic-disposal timer. Request middleware persists due countdowns as `Current Workflow = To be Disposed`, so overdue rows leave CS Follow-Up and container readiness relies only on persisted Current Workflow.

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

`frontend/lib/workflowQueueSearch.ts` centralizes normalized workflow-queue text matching and client-side advanced-filter evaluation. `frontend/components/WorkflowQueueAdvancedSearch.tsx` provides the shared Advanced Search UI used by CS Follow-Up, Dispose Samples, To be shipped, and To be back to testing.

Backend fuzzy search recognizes user-facing Problem ID forms through `problem_number_from_query()` in `backend/problem_samples/search.py`. `GET /api/problem-samples/disposal-browse/` supplies the Dispose Samples candidate set when advanced conditions are used without a basic search query.


### Customer notification files
Images and attachments remain stored with problem samples, but **Email Customer** always opens the normal `mailto:` email-client flow. Stored files are not attached to customer notification emails and no `.eml` draft is generated because files exist on the sample. The public Problem Sample Tracking page shows those stored images/files through token-scoped endpoints while the Problem Sample Tracking Link remains valid; after link expiry/token purge, those endpoints return not found.

- Customer notification emails tell recipients that the Problem Sample Tracking page may contain images or files associated with the problem sample(s).

## Staff change reasons

Manual staff mutations of an existing ProblemSample require an `X-Change-Reason` request header (maximum 1000 characters). This requirement is enforced for ProblemSample PATCH updates and the staff workflow endpoints that dispose samples, ship samples, return samples to testing, dispose containers, or undo container disposal. The reason is stored under `ProblemHistory.details.reason`; no schema migration is required. Customer/public acknowledgement actions and system-controlled email-status transitions are excluded. `x-change-reason` is included in the Django CORS allow-list for the separate frontend/backend development origins.

## Problem sample creation timestamp

- `ProblemSample.created_at` is the canonical read-only Date Created field.
- It is displayed in the main problem-sample table, CS Follow-Up, Dispose Samples, To Be Shipped, To Be Back to Testing, and the individual row detail page.
- No duplicate date field is stored in `custom_values`; the existing model timestamp is used.

### CS Follow-Up table scoping

`GET/POST /api/problem-samples/follow-up-required/` requires a real ProblemTable id (`table`). GET supports the basic `q` search; POST supports the table-schema Advanced Search payload. Both paths restrict candidates to the selected table relation and then to follow-up workflow states. The frontend loads `/problem-tables/`, presents an explicit table selector, and renders `selectedTable.columns` directly.


## Halted automatic disposal default

New problem samples default to `Status = CS Follow-Up` and `Dispose Automatically = No`. Migration `0049_dispose_automatically_and_custom_statuses.py` maps legacy `Automatically Disposed`/`Halted Automatic Disposal` rows into the new dedicated Yes/No field.

- `Days until up for disposal` is a system `ProblemColumn` (`system-days-until-automatic-disposal`, position 2) computed from `ProblemSample.days_until_automatic_disposal`; it is read-only and follows `Status` in every table.


### Automatic disposal expiration anchor
- Changing `Dispose Automatically` from No to Yes always starts a fresh Problem Sample Expiration Period.
- The first confirmed customer email activates that field without changing Status.
- Saving a row that is already Yes does not reset the period.
- When the period expires, Status becomes `To be Disposed` and Dispose Automatically becomes No.

### Staff change reason UI

`frontend/components/ChangeReasonModal.tsx` provides the shared promise-based reason modal used by row edits, sample disposal, shipping, back-to-testing, container disposal, and undo disposal. `frontend/lib/changeReason.ts` only emits the `X-Change-Reason` header when a non-empty reason was supplied. Backend `problem_samples.views._change_reason` treats the reason as optional and `._history_details` adds it to history only when present.

### Customer acknowledgement history

The public problem sample tracking endpoint writes a `ProblemHistory` action of `acknowledged` with summary `Customer acknowledged problem sample`. Its `details.changes` list records user-visible row fields changed by acknowledgement, including Current Workflow when customer routing changes it. The problem detail History renderer displays change lists for acknowledged actions as well as staff updates and customer-email events.


## Customer notification history changes

The `customer-notification-sent` action stores visible row changes in `ProblemHistory.details.changes`. The first confirmed email normally records `Dispose Automatically: No -> Yes` and the newly started countdown. A later automatic deadline creates a separate System history event for `Status -> To be Disposed` and `Dispose Automatically -> No`.

### CS Follow-Up quick filters

`frontend/app/follow-up-required/page.tsx` derives Quick Filters from the selected `ProblemTable.columns`, limited to Choice columns with configured choices. Active values are submitted as `quick_filters` to `POST /problem-samples/follow-up-required/` whenever quick or advanced filters are active. `ProblemSampleViewSet.follow_up_required` passes those conditions into the shared `advanced_search_problem_samples` implementation, keeping table scoping and workflow-status filtering server-side.


## Authentication

Temporary staff authentication uses administrator-created username/password accounts. Django's built-in `User` stores the derived username, First Name, Last Name, and password hash; staff email is intentionally blank until Microsoft Entra integration is available. `AppSession` remains the bearer-session model used by the frontend after a successful `POST /api/auth/login/`.

`UserProfile.is_admin` is a dedicated security permission and is deliberately separate from `UserProfile.role`, whose values remain Lab Technician and Customer Service for Group-column/workflow behavior. `GET/POST /api/auth/accounts/` is administrator-only. POST accepts First Name and Last Name, derives a unique username such as `jane.smith`, creates a cryptographically random password, and returns that generated password only in the creation response. An initial administrator can be bootstrapped with the `create_tracker_admin` management command.

Regular new accounts with no workflow role still receive the required first-login role gate. Administrator accounts bypass that gate unless they voluntarily set a workflow role from My Account. Microsoft Entra can later replace the temporary login endpoint and populate email identities while leaving the tracker/domain APIs unchanged.

## Persistent problem sample tracking links
- Each problem sample row has at most one secure tracking token/link. Once saved, that same link is reused.
- Workflow expiry keeps the link row for possible reactivation; explicit staff revocation deletes it permanently. A replacement link uses a new random token.
- The tracking link expires 30 days after the latest **Current Workflow** transition into To be Disposed, Disposed, To be shipped back to client, Shipped back to client, or Back to testing. Each later transition into one of those workflows resets the 30-day expiry.
- Descriptive Status changes do not start/reset tracking-link expiry.
- Every problem-sample table has read-only built-in Tracking Link and Tracking Link Expiry columns.

- Returning a problem sample's **Current Workflow** to CS Follow-Up clears the active tracking-link expiry and makes the same persistent tracking link accessible again.

### Required first-login role gate
`AppShell` renders `RequiredRoleModal` whenever `/api/auth/me/` reports `needs_role=true`. The modal blocks the protected portal with no dismiss action until the user explicitly selects Lab Technician or Customer Service and the PATCH to `/api/auth/me/` succeeds. Existing role-bearing accounts bypass the gate.

### Migration graph compatibility

`problem_samples` migration `0047_merge_tracking_link_migration_branches` merges the earlier acknowledgement-token field branch with the persistent tracking-link lifecycle branch. Both branches are intentionally retained so existing development databases and clean installations converge on one leaf migration.

- Customer tracking options are driven by `Dispose Automatically` plus `Current Workflow`; the exact customer-facing choice label is preserved in response/history.
- Staff-facing Tracking Link values wrap within their grid column so long secure URLs do not overflow the problem-sample form.


### Customer tracking actions by follow-up status
- Available actions are **Permit immediate disposal**, **Give us more details about this ticket**, and **Ship back**.
- An existing customer response remains editable in active and intermediate queue workflows, including **To be Disposed**, **To be shipped back to client**, and **To be back to testing**.
- **Give us more details about this ticket** returns Current Workflow to **CS Follow-Up**.
- Submitting any customer response turns `Dispose Automatically` off.
- Once Current Workflow is **Disposed**, **Back to testing**, or **Shipped back to client**, both the UI and public POST endpoint reject further response changes.


### Customer tracking response signatures
Public Problem Sample Tracking Link responses require a non-empty typed-name signature (maximum 200 characters). The frontend disables workflow-action buttons until a name is entered, and the backend independently rejects unsigned responses. Each submitted name is stored in the corresponding `ProblemHistory.details.customer_signature` value so it remains tied to the exact customer action. Successful submissions clear the input so a later response must be signed again.

- Customer **Give us more details about this ticket** responses open a required multiline modal (up to 4000 characters); the submitted information and typed-name signature are saved with the History event before the row moves to **Back to testing**.

## Next.js search-parameter boundaries
The root problem-sample table page renders its search-param-dependent content through `Suspense`. The New Problem Sample route also wraps `ProblemForm`, which reads the `table` query parameter, in `Suspense`. Keep this boundary when changing either route so Vercel/Next.js production prerendering remains valid.

### Customer administration and import history

`/api/customers/`, `/api/customers/import/`, and `/api/customers/overview/` require a tracker administrator. The Customers navigation entry is also rendered only for administrators. `CustomerImport` is retained as an audit trail rather than deleted during snapshot replacement; `Customer` rows are still atomically replaced by each successful export. The overview endpoint returns the current directory row count plus up to the 100 most recent upload records. Form-specific suggestion endpoints remain authenticated-user APIs so Distributor, End User, Brand, and Client Email fields continue to function for workflow users.


## Current automatic-disposal lifecycle

`Dispose Automatically` is a required built-in Yes/No field independent of Status. A No -> Yes change starts/restarts `automatic_disposal_started_at`. When the table-specific expiration deadline is reached, `AutomaticDisposalTransitionMiddleware` calls the model lifecycle transition before request handling. The row's built-in Status and legacy core `status` field are both set to `To be Disposed`, `Dispose Automatically` is set to `No`, the tracking-link terminal-status timestamp is anchored to the actual deadline, and a System History event records both field changes. `ProblemSample.is_disposal_eligible` now returns true only for persisted `To be Disposed` rows. A zero-day expiration is also applied immediately in create/edit/customer-notification confirmation requests so the response already contains the terminal workflow state.

## Customer email history and disabled Email Customer state (2026-09-11)

- `POST /api/problem-samples/{id}/customer-notification-sent/` stores `Sent tracking link to customer by email` for the first confirmed notification and marks the history details with `first_notification: true`.
- Subsequent confirmed Send Tracking Link emails use the same tracking-specific summary. Confirmed general Email Customer messages store `Sent an email to the customer` with no link or automatic-disposal change.
- `HistorySerializer` preserves the stored notification summary so event-specific history text reaches the frontend.
- The detail page always renders **Email Customer**; when `findCustomerEmails(...)` resolves no recipient, the button is disabled rather than omitted.


### Administrator-managed email templates

`problem_samples.EmailTemplate` stores editable email copy. `/api/email-templates/customer-notification/` is readable by authenticated staff and writable only by tracker administrators. The frontend Send Tracking Link flow retrieves this template immediately before composing its mailto URL. General Email Customer messages have their own editable draft.

`problem_samples.NotificationRecipient` stores the NA.EDM address (default `NAEDM.DE@ALSGlobal.com`). `/api/email-templates/edmonton-recipient/` allows authenticated staff to read it and administrators to change it. The new-ticket customer email includes this address; the customer email body uses `{{na_edm_email}}`; and the Back to Testing email preview loads it on opening. Confirming a sent Back to Testing email requires the same active address, preventing a stale preview from recording a different destination. Migration `0060_notification_recipient` upgrades the previously saved default customer email template to use the placeholder.


## CS Follow-Up and fixed Status values

Migration `0052_cs_follow_up_and_fixed_statuses` renames the default Current Workflow from `Follow Up Required` to `CS Follow-Up` and standardizes Status across every table to `NEW`, `IN PROGRESS`, `ON HOLD`, `SHIPPED BACK TO CLIENT`, `DISPOSED`, and `COMPLETED`. Existing Status values are normalized into that set; unrecognized values become `NEW`.

### Ticket-table Image Search

`frontend/app/problem-samples/page.tsx` derives an image count from the currently matched ticket rows and serializes the active basic query, Advanced Search filters/match mode, and Quick Filters into the Image Search route. `frontend/app/problem-samples/image-search/page.tsx` replays that same query against the existing ticket APIs, flattens each matching ticket's `images` relation into gallery results, and provides large contained previews, a full-screen lightbox, and links back to the owning ticket. No separate image-search database index is required because ticket serializers already include image metadata.

## Direct camera capture
`frontend/components/CameraCapture.tsx` provides a reusable browser-camera modal using `navigator.mediaDevices.getUserMedia`. It prefers the environment-facing camera and renders a video preview. Captures are drawn to a canvas and encoded as JPEG before being passed back as a `File`, keeping them compatible with the backend image validator (JPEG/PNG/GIF/WebP). New-ticket captures are held in `ProblemForm` until prepared-ticket finalization; existing-ticket captures upload immediately through the standard `/problem-samples/{id}/images/` endpoint.


## Production image storage and staff image delivery
Staff ticket images are no longer rendered from raw Django `/media/` URLs. Ticket Details and Image Search fetch image bytes through the authenticated `GET /api/problem-samples/{ticket_id}/images/{image_id}/content/` endpoint, so production does not depend on Django's development-only media serving. A missing backing file returns a controlled 404 and the frontend displays **Image file unavailable**.

Uploads still require durable file storage. `MEDIA_ROOT` now uses, in order: an explicit `MEDIA_ROOT` environment variable, Railway's automatically provided `RAILWAY_VOLUME_MOUNT_PATH`, or the local `backend/media` directory. In Railway, attach a persistent Volume to the Django backend (for example at `/app/media`) before relying on uploaded ticket images across deployments. Database rows only store file paths; they do not preserve the image bytes if ephemeral storage is replaced.

## Staff image delivery
Problem image metadata excludes the storage/media URL. Staff image previews are fetched with the existing bearer session through the authenticated image-content endpoint, then displayed using a browser blob URL. This avoids exposing `/media/` URLs and prevents HTTPS pages from issuing mixed-content image requests.

## Date-based container disposal
`ProblemContainerViewSet.dispose_by_date` accepts `cutoff_date` (`YYYY-MM-DD`) and locks the container transactionally. Every attached ticket must have a local `created_at` date strictly earlier than the cutoff. Eligible non-disposed tickets are transitioned to `Disposed` using the same snapshot/history mechanism as normal container disposal, allowing Undo Disposal to restore prior workflow state. `ProblemContainerSerializer.samples` exposes `created_at` and `created_date` for the Dispose by Date UI.
