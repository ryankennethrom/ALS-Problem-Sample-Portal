## Latest update

- The Django backend now uses **PostgreSQL by default** locally and in deployment. `DATABASE_URL` remains configurable for hosted PostgreSQL services. The previous `db.sqlite3` file is not deleted, and a one-time SQLite-to-PostgreSQL transfer procedure is documented below.

# Edmonton Problem Sample Tracker MVP

A Next.js + Django/DRF internal tracker for laboratory problem samples.

## Stack

- **Frontend:** Next.js App Router + TypeScript
- **Backend:** Django + Django REST Framework
- **Database:** PostgreSQL locally and in deployment
- **Authentication:** administrator-created username/password accounts for the temporary MVP; isolated so it can later be replaced by Microsoft Entra ID
- **Search:** identifier normalization + weighted fuzzy search, including user-created searchable columns
- **Customer sync:** Customer Export upload rather than direct access to ALS production systems
- **Dynamic tables:** users can create multiple Problem Sample Tables and add their own typed columns, similar to Microsoft Lists/Tables

## Dynamic Problem Sample Tables

The original Problem Samples CSV fields remain as standard fields on every problem sample. Users can additionally create any number of Problem Sample Tables and give each table its own custom columns.

Supported custom column types:

- Single line of text
- Multiple lines of text
- Number
- Choice
- Multiple choice
- Date
- Date and time
- Time
- Yes / No
- Email
- URL
- Fixed Value (table-wide, read-only on rows)
- Row Creator (read-only original creator email; automatically populated for new rows)
- Intercolumn Value Controller (single-value text field with directional equality/assignment rules between columns)

Custom columns can be marked required and/or searchable. Searchable custom values automatically participate in the fuzzy search engine. Deleting a custom column removes its values from rows in that table.

### Optional column explanations

Each custom column can have an optional explanation. When an explanation is configured in **Table Settings**, a small **(i)** icon appears beside the column name in problem-sample create/edit forms, the main table header, and Quick Filters. Users can hover, focus, or click the icon to read the explanation. Leaving the explanation blank hides the icon.

The schema uses `ProblemTable`, `ProblemColumn`, and `ProblemSample.custom_values`, so adding a new user-defined column does **not** require a Django database migration.

## Project layout

```text
frontend/   Next.js UI
backend/    Django REST API
sample-data/ exported/problem sample examples
```

## Quick start

### Backend

The backend expects PostgreSQL. On Ubuntu/WSL, install and start PostgreSQL first:

```bash
sudo apt update
sudo apt install -y postgresql postgresql-contrib
sudo service postgresql start

# Create the local development role once.
sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='problem_sample_tracker'" | grep -q 1 \
  || sudo -u postgres psql -c "CREATE ROLE problem_sample_tracker LOGIN PASSWORD 'problem_sample_tracker';"

# Create the local development database once.
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='problem_sample_tracker'" | grep -q 1 \
  || sudo -u postgres createdb -O problem_sample_tracker problem_sample_tracker
```

Then configure and run Django:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp -n .env.example .env
python manage.py migrate
python manage.py import_problem_samples ../sample-data/Problem\ Samples.csv
python manage.py runserver 8000
```

The example local connection is:

```text
postgresql://problem_sample_tracker:problem_sample_tracker@127.0.0.1:5432/problem_sample_tracker
```

For Railway or another hosted PostgreSQL provider, set `DATABASE_URL` to the provider's PostgreSQL connection URL instead. `dj-database-url` parses the URL and `psycopg` is the PostgreSQL driver.

### Moving an existing SQLite database to PostgreSQL

Upgrading the application does **not** delete `backend/db.sqlite3`, but PostgreSQL is a different database and starts empty. Before changing your existing `DATABASE_URL`, export the application data from SQLite:

```bash
cd backend
source .venv/bin/activate
DATABASE_URL="sqlite:///$PWD/db.sqlite3" python manage.py dumpdata \
  --exclude contenttypes \
  --exclude auth.permission \
  --exclude admin.logentry \
  --exclude sessions \
  --exclude accounts.loginlink \
  --exclude accounts.appsession \
  --indent 2 > sqlite-to-postgres.json
```

After PostgreSQL has been created and `.env` contains the PostgreSQL `DATABASE_URL`, create the schema and load the data:

```bash
python manage.py migrate
python manage.py loaddata sqlite-to-postgres.json
```

Keep a copy of `db.sqlite3` until you have verified the PostgreSQL data. Uploaded image/file contents live under `backend/media/`, not inside SQLite, so preserve that directory as well.

After the first migration, create at least one tracker administrator with `python manage.py create_tracker_admin --first-name <First> --last-name <Last>`. The command prints the derived username and generated random password once.

### Frontend

```bash
cd frontend
cp .env.local.example .env.local
npm install
npm run dev
```

Open http://localhost:3000.

## Main workflows

- `/` or `/dashboard` — open the dashboard after sign-in (new users who still need to choose a role visit `/account` first)
- `/problem-samples?table=<table-id>` — open a Problem Sample Table, search it, and see standard + custom columns; old `/?table=<table-id>` links redirect here
- `/problems/new?table=<table-id>` — add a row to a selected table
- `/tables` — create new Problem Sample Tables
- `/tables/<table-id>` — rename a table and add/edit/delete its custom columns
- `/customers` — upload the Customer Export (`.xlsx` or `.csv`)
  - imports are treated as full directory snapshots; no customer-export column is assumed unique, and duplicate source rows are preserved

## Search behavior

`GET /api/problem-samples/search/?q=...&table=<table-id>`

The search service:

- normalizes case, whitespace and punctuation;
- gives very high weight to exact/partial identifiers;
- searches the table's configured searchable columns plus high-value identifiers; Fixed Value columns participate in search like other configured columns;
- searches every user-defined column whose **Include in search** setting is enabled;
- uses `RapidFuzz` for typo tolerance;
- returns a numeric `search_score`.

These identifiers normalize equivalently:

```text
#JDP0101012
# JDP0101012
jdp-0101012
JDP0101012
```

For a larger production dataset, the search service can later switch to PostgreSQL `pg_trgm` + full-text search while keeping the API unchanged.

## Authentication

The temporary MVP uses administrator-created username/password accounts. An administrator creates an account from **Staff Accounts** by entering First Name and Last Name. The server derives a lowercase username such as `jane.smith` (adding a numeric suffix for duplicates), generates a cryptographically random password, and stores only Django's password hash. Email is not required. The generated password is returned only in the account-creation response so the administrator can hand it to the user.

Administrator permission is separate from the existing **Lab Technician** / **Customer Service** workflow role. Regular users still choose one of those workflow roles after first login. From **Staff Accounts**, an administrator can grant or remove administrator access for another user, reset another user's password to a newly generated random password, and delete another user. Password reset revokes that user's existing tracker sessions. These account-management actions cannot be used on the administrator's own account from the Staff Accounts page. Every authenticated user, including administrators, can change their own password from **My Account** by entering the current password and a new password of at least 12 characters. The new password is saved with Django's password hashing; other active tracker sessions for that account are revoked while the session performing the change remains signed in. The initial administrator is bootstrapped with `python manage.py create_tracker_admin --first-name <First> --last-name <Last>`. Microsoft Entra ID can later replace this temporary login layer and add staff email identities without changing the problem-sample domain model.

## Railway deployment

Deploy the backend and frontend as separate Railway services and attach PostgreSQL to the backend. Before putting real ALS customer data on personally managed external hosting, confirm that the external hosting arrangement is approved.


## Dynamic tables

New Problem Sample Tables start with only the protected auto-incrementing **Problem ID** column. Users add only the other fields that table needs (text, long text, number, choice, multiple choice, date, date/time, time, yes/no, email, URL, Fixed Value, Group, Distributor, End User, Client Email, and Row Creator). Constant values such as a lab or site name should be represented with the general-purpose **Fixed Value** column type.

## User roles

Regular accounts choose **Lab Technician** or **Customer Service** after their first username/password login. This remains workflow/profile metadata. **Administrator** is a separate security permission used for account creation and is not selectable from My Account.


### Customer-service email template

Creating a problem sample saves the ticket and its files without preparing or sending email. On the ticket detail page, **Send Tracking Link** prepares the secure link email for the selected customer address(es). **Email Customer** opens a separate editable message to those customer recipients without a tracking link or disposal side effects.

For **one customer recipient**, the app looks up that exact email in the current Customer Export and uses its unique `PrimaryContact` value when one is available (for example, `Hi Jane Smith,`). If the address is manual, missing from the export, or maps to conflicting contact names, it safely falls back to `Hi there,`. The internal `NAEDM.DE@ALSGlobal.com` copy does not cause the message to switch to the multiple-customer wording.

For **multiple customer recipients**, the message uses `Hi there,` and explains that ALS does not currently know the primary contact for the affected samples. Both templates include Problem ID plus useful populated row details such as Date Received, sample tracking number, number of problem samples, Problem Type, Issue Description, and courier/tracking information when those columns exist. The subject includes the Problem ID when available. The old customer-service phone sentence has been removed from the message.


## Built-in Problem ID

Every Problem Sample Table contains a non-editable **Problem ID** column. IDs are positive auto-incrementing numbers allocated independently within each table. Users cannot edit or delete this system column.

## Advanced search

Every Problem Sample Table has an **Advanced Search** panel generated from that table's column definitions. Users can combine up to 20 conditions and choose whether to match all conditions or any condition. Operators adapt to the field type, including text contains/equals, numeric comparisons and ranges, choice values, dates/date-times/times, yes/no, and empty/not-empty checks. The ordinary fuzzy search box can be used at the same time as advanced filters. Advanced Search also reuses a column type's normal input suggestions: Distributor, End User, Brand, and Client Email conditions use the same fuzzy Customer Export suggestion sources as ticket fields, while Choice/Multi-choice and Group conditions continue to show their configured values/users. The shared workflow-queue Advanced Search also uses the same fuzzy Distributor, End User, and Brand suggestions for those fields.

The endpoint is `POST /api/problem-samples/advanced-search/` with a body such as:

```json
{
  "table": "<table uuid>",
  "q": "optional fuzzy search text",
  "match": "all",
  "filters": [
    {"field_key": "problem-id", "operator": "gte", "value": "100"},
    {"field_key": "status", "operator": "equals", "value": "New"}
  ]
}
```


## Row history

Problem sample details include a History panel at the top. Creating a row, saving changes, sending a tracking link, sending general correspondence, revoking a link, and adding comments each record the authenticated staff user and timestamp. **Send Tracking Link** confirmation records **Sent tracking link to customer by email**; **Email Customer** confirmation records **Sent an email to the customer**. If a tracking email is not sent, staff must give a reason. Update entries include before/after values for changed fields.

## Operation notifications

The frontend includes DigitalSIF-style toast notifications in the top-right corner. Successful create/update/delete/import/authentication operations display green notifications, while failed operations display red notifications with the server error detail when available. Notifications can be dismissed manually and otherwise close automatically.

## Distributor columns

A table can define a **Distributor** column. Row editors use fuzzy autocomplete against the imported customer directory and only suggest companies whose `CoyType` is `Distributor`. Customer exports may be `.xlsx` or `.csv`; the importer recognizes `CoyId`, `Company`, `CoyType`, `Brand`, `City`, `State`, `LastDateRecd`, `DateCreated`, `PrimaryContact`, and `Email`.

## Company directory column types

- **Distributor** uses fuzzy autocomplete limited to customer rows where `CoyType = Distributor`.
- **End User** uses fuzzy autocomplete limited to customer rows where `CoyType = End User`.

## Client Email columns

A table can define a **Client Email** column backed by the imported customer directory. The row value is a **list of email addresses**, not a single string. The editor shows the current list with checkboxes and actions for **Keep Selected**, **Delete Selected**, **Clear All**, and **Add an Email**. A Filter box fuzzy-matches imported `Email`, `PrimaryContact`, and company information without using the text box itself as the stored value.

A Client Email column may optionally configure **multiple dependency fields in priority order**. Each dependency field's row value is treated as a company name. The app checks the configured fields from highest to lowest priority and uses the first populated company that has at least one imported email. If that company has no emails, it automatically falls through to the next configured dependency.

For example, a Client Email field may use `End User` as Priority 1 and `Distributor` as Priority 2. On a new/uninitialized row, all unique emails under the active company seed the list. The user can then select rows and keep only those addresses, delete selected addresses, clear the entire list, or add a valid email manually. Fuzzy filtering never resurrects an address that the user already deleted from a dependent list.

Changing any configured dependency field marks the Client Email list as uninitialized so the next edit can seed it from the new active company. Dependent Client Email columns do not use one table-wide default. Without dependencies, users can fuzzy-search the full imported directory and use Keep Selected to build a multi-address list. Manually added addresses do not have to appear in the latest Customer Export.

The customer importer treats the Customer Export as a complete snapshot and does not assume any export column is unique, so multiple contacts and duplicate rows from the source are preserved.

- Customer Export header matching and `CoyType` values are normalized (for example `CoyType`, `Coy Type`, `Coy-Type`, `DISTRIBUTOR`, and extra whitespace all resolve consistently).


## Customer notification fields
Table columns have an **Include in customer notification** option. Problem ID is always included automatically; other row fields appear in the generated customer email only when this option is enabled. Customer greetings use **Dear valued customer,**.


## Problem row files
Problem sample rows support multiple images (JPEG, PNG, GIF, WebP) and general file attachments. Files are uploaded through authenticated DRF row actions and stored through Django's configured file-storage backend. The included development configuration uses `backend/media/`; production deployments should point Django storage at persistent object/blob storage rather than an ephemeral application filesystem. Each file is limited to 25 MB.


## Customer notification files
Problem-row images and attachments remain stored with the sample but are not attached to customer notification emails. **Email Customer** always uses the normal `mailto:` flow. When the saved Problem Sample Tracking Link is valid, the public Problem Sample Tracking page displays image previews and protected download links for all files stored on that sample.

- Read-only fields in problem sample create/edit forms (including Problem ID, Fixed Value, and Row Creator columns) are visually greyed out.

## Row Creator columns

A **Row Creator** column is controlled by the server rather than the row editor. New rows automatically store the authenticated creator's ALS email (with username as a fallback), and the field is shown greyed out in both create and edit forms. Updates cannot change the stored creator value. When the column is added to an existing table, rows are backfilled from their recorded `created_by` account or legacy creator value when available. Row Creator columns can participate in fuzzy/advanced search and can optionally be included in customer notifications.


### Intercolumn Value Controller columns

An **Intercolumn Value Controller** is an editable single-value text column with one or more table-defined rules. Each rule links the controller to another supported single-value field and may run **Other field → Controller**, **Controller → Other field**, or **Both** directions. For example: `if Priority == High, set Escalation = Urgent`, and/or `if Escalation == Normal, set Priority = Low`.

Rules may reference text, long text, number, choice, date/date-time/time, yes/no, email, URL, another Intercolumn Value Controller, or the editable built-ins **Status**, **Current Workflow**, and **Dispose Automatically**. Multi-value Client Email/Multiple Choice fields and server-controlled/read-only fields are intentionally excluded. Rule trigger/assignment values are validated against the referenced field type when the rule is saved.

The frontend applies rules immediately while a row is edited for visibility, while the Django backend re-applies them authoritatively on save and during workflow lifecycle transitions. Chained rules are evaluated to a fixed point; non-converging cycles are rejected. Changing controller rules synchronizes existing rows and records System history for values changed by the new configuration. A field referenced by a controller cannot be deleted or have its type changed until the referencing rule is removed.

### Recent Row Modifier column
A `Recent Row Modifier` column is server-controlled and read-only. It contains the email (or username fallback) of the authenticated staff user who most recently saved the problem-sample row, or `Customer` when the most recent row change came from the public tracking link. Customer-originated changes clear the stale `modified_by` staff reference and update the row modification timestamp; the next authenticated staff save replaces `Customer` with that staff user's email/username. Existing rows are backfilled from `modified_by` / legacy modifier metadata, falling back to creator metadata when needed.


### Brand column type
Brand columns use fuzzy suggestions from distinct Brand values in the latest imported Customer Export. Saved values are validated against that directory, while unchanged historical values remain valid if a later export removes a brand.


### Problem sample row deletion
- A problem sample can be permanently deleted from its detail/editor page with **Delete Row**.
- Deletion requires a second confirmation in a destructive-action dialog.
- Django deletes related comments and history through cascading relationships. Related image/attachment records are also deleted, and their stored files are removed by the existing post-delete cleanup handlers.
- The table's `next_problem_id` counter is not decremented, so a deleted Problem ID is not reused.

## Problem Samples Automation email template

Customer notification emails now use the formal ALS problem-sample hold template. The subject is built from the row's Problem Type and Problem ID. The body automatically pulls ALS Sample Tracking Number, Reason for Hold (with Issue Description as a fallback), and Date Received when those columns exist. If more than one customer email address is selected, the message explains that multiple contacts are being notified because a primary contact could not be confirmed. Any other columns marked **Include in customer notification** are appended under **Additional information**. Before the email application is opened, the app shows a preparation dialog explaining that **OK** will construct the email and instructing the employee to review it and return to the tracker. Only after **OK** prepares the email does the app ask **I sent the email** / **I didn't**. Sent-email History and the automatic-disposal countdown start only after **I sent the email** is confirmed; confirming the email does not itself change Status.

## Containers and problem sample expiration

Every newly created problem sample must be assigned to a **Container**. The create form lets the user either enter an existing system-generated Container ID (for example `PC-000123`) or create a new container and immediately receive its ID so the physical container can be labelled before the row is saved. Existing legacy/imported rows may remain unassigned.

Each Problem Sample Table has a configurable **Problem Sample Expiration Period** measured in days. It defaults to **30 days** and is editable under **Manage Tables → Table Details**. Expiration is calculated from **Date Created**, not from notification time. A value of **0** means the sample is expired immediately from creation. Sending or resending a customer notification never starts, resets, or extends the expiration period.

The **Containers** page shows every container and the expiration state of its samples. The customer-notification template uses the table's configured Problem Sample Expiration Period instead of a hard-coded 30-day value.

## Shipping queue

The sidebar has a direct **To be shipped** tab at `/shipping/to-be-shipped`. This page shows only problem samples whose **Current Workflow** is **To be shipped back to client**. Users can search the queue, select one or many rows (including Select all visible), and choose **Ship Selected**. The backend validates the selection transactionally and changes every selected row to **Shipped back to client**, updates Recent Row Modifier fields, applies the existing tracking-link status-transition timing, and writes a History entry for each row. Completed **Shipped back to client** rows disappear from the queue and are removed from their containers.

## Current Workflow, Status, and container disposal
Every problem sample table has three required built-in controls: **Status**, **Current Workflow**, and **Dispose Automatically**. **Status** is descriptive and has six fixed built-in values: **NEW**, **IN PROGRESS**, **ON HOLD**, **SHIPPED BACK TO CLIENT**, **DISPOSED**, and **COMPLETED**. **Current Workflow** is the authoritative system-routing field and has immutable values **CS Follow-Up**, **Waiting For Customer**, **To be Disposed**, **To be shipped back to client**, **To be back to testing**, **Back to testing**, **Disposed**, and **Shipped back to client**. **Dispose Automatically** is fixed to **Yes** or **No**. New rows default to **Current Workflow = CS Follow-Up** and **Dispose Automatically = No**. The first confirmed customer email turns **Dispose Automatically** to **Yes** without changing Status or Current Workflow. When that period expires, **Current Workflow** is automatically persisted as **To be Disposed** and **Dispose Automatically** is turned back to **No**; Status is left unchanged and History records the workflow change.

Migration `0051_current_workflow` adds the indexed Current Workflow mirror and required built-in column. Existing rows that were in one of the old protected workflow Status values retain that routing value as Current Workflow; their Status is reset to the table descriptive default. Existing rows with a custom/non-workflow Status keep that Status and migrate to Current Workflow = CS Follow-Up.

A container is **Ready to Dispose** when it contains at least one ticket and every attached ticket has **Current Workflow = To be Disposed** or **Disposed**. When a row with **Dispose Automatically = Yes** reaches its table's Problem Sample Expiration Period, the backend persists a real workflow transition: **Current Workflow** becomes **To be Disposed** and **Dispose Automatically** becomes **No**. The Containers page highlights ready containers and provides a **Dispose Container** action. Disposing a container records who disposed it and when, changes every disposal-participating problem sample's **Current Workflow** to **Disposed**, leaves already **Disposed** tickets unchanged, updates Recent Row Modifier fields, records the workflow changes in History, and stores a rollback snapshot of the pre-disposal sample state. A disposed container exposes **Undo Disposal**, which restores that snapshot, clears the container's disposal stamp, and records an undo event in each sample's History. If any contained sample was manually changed after disposal, the undo is blocked rather than overwriting the newer change. Containers disposed before rollback snapshots existed fall back to recorded disposal History when possible.


### Changing a problem sample container
An existing ticket can be assigned to an active container, moved, or detached by changing or clearing **Container ID** and choosing **Save Changes**. The new-ticket form requires a container; the API still permits unassigned tickets. The API validates a supplied Container ID and records the old and new IDs in row History. Because container readiness is derived from current membership, both the source and destination container readiness states reflect the move immediately. Samples cannot be moved into or out of a disposed container; undo the container disposal first. New samples also cannot be assigned to a disposed container.

## Customer problem sample tracking links
Customer notification emails include a public secure Problem Sample Tracking URL. Customers do not need an ALS account and there is no separate access code. The tracking page offers **Permit immediate disposal**, **Give us more details about this ticket**, and **Ship back**. If **Dispose Automatically = Yes**, it also shows the remaining automatic-disposal countdown; submitting any customer response stops that countdown. Customers may revise a response while the ticket is still in an active or intermediate **To be ...** workflow. Responses become read-only only after Current Workflow reaches **Disposed**, **Back to testing**, or **Shipped back to client**. When the automatic-disposal deadline itself is reached, the backend changes **Current Workflow** to **To be Disposed** automatically while preserving Status; the customer can still revise the response until disposal is completed. A GET/page preview never acknowledges the row; the first explicit customer action records acknowledgement and applies the selected action.

## Problem Sample Tracking Link lifecycle
Problem Sample Tracking Links are persistent tokens whose public accessibility is controlled by a fixed 30-day window after the most recent **Current Workflow** transition into **To be Disposed**, **To be shipped back to client**, **To be back to testing**, **Back to testing**, **Disposed**, or **Shipped back to client**. Returning **Current Workflow** to **CS Follow-Up** clears that expiry clock and makes the same link accessible again. An automatic-disposal deadline counts as a real transition to **To be Disposed**, so its 30-day window begins at the actual deadline.

### Acknowledgement credentials are committed only after confirmed send

When a customer notification is prepared, the backend returns a temporary secure acknowledgement token without saving it to the ProblemSample row. New Problem Sample Tracking Links use `secrets.token_urlsafe(48)`, providing about 384 bits of cryptographic randomness. Existing UUID links remain valid after migration, but all newly generated links use the stronger token format. Migration `0043_secure_acknowledgement_token` converts the stored token field to a URL-safe string while preserving existing tracking URLs. The public problem sample tracking endpoint therefore cannot resolve a newly prepared link yet. Clicking **I sent the email** sends the prepared token back to the backend, which persists it together with the confirmed notification timestamp and normal status transition. Cancelling the launch or choosing **I didn't** leaves the database token empty. Migration `0044_remove_customer_access_code_hold_sample` removes the old customer acknowledgement-code field and converts the old `neither` customer action to `hold`.


### First confirmed customer email
The first confirmed customer email turns **Dispose Automatically** from **No** to **Yes** while **Current Workflow = CS Follow-Up**, without changing Status or Current Workflow. That No -> Yes change starts a fresh table-configured automatic-disposal period. Resending the email does not restart the period unless **Dispose Automatically** is later changed back from No to Yes.

## Shipping-back workflow

`Current Workflow = To be shipped back to client` records a pending return. Customer selection of **Ship back samples** sets that workflow. Once staff completes the return, Current Workflow becomes `Shipped back to client`. Completed shipped-back samples are ignored for container disposal readiness and are not changed when a container is disposed.

## CS Follow-Up queue

The Problem Samples navigation includes **CS Follow-Up**, a cross-table queue ordered oldest-first. It contains only rows whose **Current Workflow = CS Follow-Up**.


### CS Follow-Up ordering
The CS Follow-Up queue is ordered by problem sample creation time, oldest first, so the longest-waiting samples appear at the top.

### Back To Testing and NA.EDM notification

Administrators can change the NA.EDM recipient address on **Admin → Email Templates**. The saved address is used for Back to Testing notifications and included on customer emails when creating a ticket. Staff can view the active address but cannot edit it.

Choosing **Back to testing** on an existing ticket opens an internal email preview addressed to the configured NA.EDM recipient. Staff may add details, copy the address and message, and open their email app. The workflow change is saved only after they choose **I sent the email** or **I didn't send the email**; Cancel leaves the ticket unchanged. Confirmed messages are recorded in History. Customer **Give us more details about this ticket** responses enter **To be back to testing**, visible in the sidebar queue, until staff changes the workflow to **Back to testing**. Completing that transition removes the ticket from its container. A pending NA.EDM notification can be recorded from the ticket detail page.

### Public tracking link security

New tracking links use `secrets.token_urlsafe(48)`: 48 cryptographically random bytes (384 bits), encoded as 64 URL-safe characters. The server retains a pending token while staff prepares a customer email; it becomes public only after they confirm sending. The confirmation API accepts only that server-issued token.

Migration `0061_secure_public_tracking` replaces older tracking tokens, including UUID links with fewer than 128 random bits. **Previously emailed old links stop working.** For any ticket with a history entry **Legacy tracking link rotated; resend the customer email**, staff should open the ticket and use **Send Tracking Link** to send the new link. The migration also updates a stored system tracking-link field when present. Generated links already using 48 random bytes stay the same.

The public tracking page, customer actions, images, attachments, and older API alias share database-backed request limits: per client address, 60 reads/minute and 600 reads/hour, and 10 writes/minute and 60 writes/hour; per link, 120 reads/minute and 3 writes/minute plus 12 writes/hour. Exceeding a limit returns HTTP 429 with `Retry-After`. The limits apply across application workers. `PUBLIC_TRACKING_*_LIMIT_*` in `backend/.env.example` allow adjustment. By default the limiter uses `REMOTE_ADDR`. If a trusted reverse proxy appends `X-Forwarded-For`, set `PUBLIC_TRACKING_TRUSTED_PROXY_HOPS` only after verifying the proxy chain; otherwise users behind one proxy may share a limit. For heavy automated traffic, add rate limits at the public ingress as well.

### CS Follow-Up automatic-disposal countdown

The CS Follow-Up queue shows a **Days until up for disposal** column. Only samples with **Dispose Automatically = Yes** have an automatic-disposal countdown, based on the most recent **No → Yes** change plus the table's Problem Sample Expiration Period. Rows become progressively red as the deadline approaches. Once the deadline is reached, the backend changes **Current Workflow** to **To be Disposed**, so the row leaves CS Follow-Up and enters the disposal workflow while its descriptive Status remains unchanged. **Dispose Automatically = No** displays **Unknown**.

### CS Follow-Up navigation
`CS Follow-Up` is a top-level sidebar tab rather than a sub-item under `Problem Samples`. Its queue behavior, oldest-first ordering, age indicator, automatic-disposal countdown, and row urgency shading are unchanged.

## Disposal workspace

The previous top-level **Containers** navigation is now **Disposal** with two subpages:

- **Dispose Containers** (`/disposal/containers`) retains container creation, readiness, disposal, and undo-disposal workflows. Its internal **Ready to Dispose** view is at `/disposal/containers/ready-to-dispose`. Legacy `/containers` URLs redirect to the new locations.
- **Dispose Samples** (`/disposal/samples`) provides a ranked search across problem IDs, tracking values, customers, and searchable dynamic fields. Staff can dispose a single result immediately or select multiple results and dispose them together.

Direct sample disposal is transactional, records a **Disposed sample** history entry with the Status change, updates Recent Row Modifier fields, and applies the tracking-link status lifecycle. A sample in an already-disposed container must have the container disposal undone first. Samples already **Disposed** cannot be disposed again.

The new-ticket form requires staff to select or create a container before saving. The backend still permits containerless tickets for API imports, edits, and completed shipping/testing workflows. Completing **Shipped back to client** or **Back to testing** removes a ticket from its container; pending shipping and testing workflows retain membership. A nonempty container is ready to dispose only when **every attached ticket** is **To be Disposed** or **Disposed**. Disposal changes only the waiting tickets; a container whose tickets are all already Disposed can still be marked disposed and later undone.

- Disposal → Dispose Containers now defaults to the Ready to Dispose view; All Containers remains available as a secondary tab.

## Workflow queue search improvements

The workflow queues now use normalized search behavior so user-facing Problem ID queries such as `Problem #6`, `Problem ID #6`, `#6`, and `6` resolve correctly. This applies to CS Follow-Up, Dispose Samples, To be shipped, and To be back to testing.

Those four pages also include Advanced Search. Advanced conditions can target Problem ID, table, Current Workflow, Status, container, distributor, end user, brand, ALS/courier tracking fields, created/modified time, or all custom field values. Conditions can match all or any rules. Dispose Samples can run Advanced Search without requiring a basic search term. **To be back to testing** now supports selecting individual or all visible tickets and moving them together after one NA.EDM email sent/not-sent confirmation. The backend rejects stale selections as a unit, removes completed tickets from their containers, and records the outcome in each ticket's History.


## Sidebar navigation

Sidebar navigation is grouped into **Workflows**, **Tables**, **Admin**, and **Settings**. Workflows contains CS Follow-Up, Disposal, Shipping, and Back To Testing; Tables contains Problem Samples and Manage Tables. The **Admin** section is shown only to administrators and contains Customers and Staff Accounts. Settings contains My Account and Logout. CS Follow-Up uses a clock icon.

### Recently Disposed Containers

`Disposal -> Dispose Containers` now includes a **Recently Disposed** view. It lists disposed containers in descending `disposed_at` order (newest first), shows who disposed them and when, and keeps **Undo Disposal** available from the list. **Ready to Dispose** remains the default container view.

### Create Problem Sample workflow

The Workflows section includes **Create Problem Sample**. If exactly one problem-sample table exists, the workflow opens the create form for that table automatically. If multiple tables exist, the user chooses the table first. If no tables exist, the workflow links to Manage Tables.

## Most recent container suggestion

When creating a problem sample with **Use an existing container**, the form now fetches the newest non-disposed container and shows it as a one-click suggestion. The user can still type any other valid active Container ID. Disposed containers are never suggested.

## Advanced Search layout fix (2026-09-03)
- Workflow Advanced Search panels are anchored to the full search row instead of the Advanced Search button, preventing the panel from extending underneath the sidebar.
- Advanced Search stays within the content card width at desktop, tablet, and mobile sizes.
- Condition fields now shrink safely without overflowing their grid cells.
- `Between` conditions display two values with an `and` separator; value-less operators show a clear `No value required` placeholder.
- The fix applies to CS Follow-Up, Dispose Samples, To Be Shipped, To Be Back to Testing, and the shared table Advanced Search styling.


## Advanced Search alignment update
- Advanced Search buttons now align directly with the search input instead of centering against the label + input block.
- The button height matches the 38px search input across shared workflow/table search layouts.


### Customer notification files
Images and attachments remain stored with problem samples, but **Email Customer** always opens the normal `mailto:` email-client flow. Stored files are not attached to customer notification emails and no `.eml` draft is generated because files exist on the sample. The public Problem Sample Tracking page shows those stored images/files through token-scoped endpoints while the Problem Sample Tracking Link remains valid; after link expiry/token purge, those endpoints return not found.

- Customer notification emails tell recipients that the Problem Sample Tracking page may contain images or files associated with the problem sample(s).

## Required reason for staff changes

Staff-driven changes to existing problem-sample rows require a reason. The detail-page Save Changes action, Dispose Samples bulk action, Shipping bulk action, Back To Testing bulk action, container disposal, and container-disposal undo all prompt for a reason before the change is submitted. The backend also rejects these mutations when no reason is supplied. The reason is stored in the existing ProblemHistory JSON details and displayed in the row History alongside the field changes. System/customer-driven events such as customer acknowledgement and customer-notification confirmation are not prompted for a staff reason.

## CS Follow-Up table selection

CS Follow-Up is explicitly scoped to a selected Problem Sample Table. The table dropdown uses the real `ProblemTable` relationship, and the queue renders that table's actual columns instead of a fixed set of inferred workflow fields. Basic and Advanced Search are also evaluated against the selected table's real searchable columns. The selected table's follow-up rows remain oldest-first.


## Dispose Automatically default
New problem samples default to **CS Follow-Up** with **Dispose Automatically = No**. The two old automatic-disposal Status values are legacy-only migration inputs and are not selectable Status values.

## Built-in automatic-disposal countdown
Every problem-sample table includes the required built-in **Dispose Automatically** Yes/No field and a read-only **Days until up for disposal** column. Changing **Dispose Automatically** from No to Yes starts/restarts the countdown from that moment using the table's Problem Sample Expiration Period. **No** displays **Unknown**. When the deadline is reached, the backend persists **Current Workflow = To be Disposed** and changes **Dispose Automatically = No** while preserving the descriptive Status. A zero-day period performs that transition immediately.

### Automatic disposal expiration anchor
- A **No -> Yes** change always starts a fresh Problem Sample Expiration Period.
- Saving a row that is already **Yes** does not restart the period.
- The first confirmed customer email activates the countdown only if it is the first notification and the row is not already in a protected workflow state.
- Expiry creates a System History event showing the Status and Dispose Automatically changes.

## Optional change-reason modal

Staff-driven problem-sample changes use a dedicated modal instead of `window.prompt`. The modal offers Continue with a reason, Skip, and Cancel. Reasons remain limited to 1000 characters and are included in the existing history details when supplied. Skip permits the change without storing an empty reason; Cancel aborts the action. The backend accepts an omitted reason while continuing to enforce the maximum reason length.

### Customer acknowledgement and notification history
Customer acknowledgement history entries display **Customer acknowledged problem sample**. Customer-selected routing changes are stored with their before/after values. **Sent an email to the customer** records any field changes caused by confirming the first email; normally that is **Dispose Automatically: No -> Yes** and the newly started countdown. When the countdown later expires, a separate System History event records **Status -> To be Disposed** and **Dispose Automatically -> No**.

## CS Follow-Up quick filters

The CS Follow-Up workflow exposes a Quick Filters section for the currently selected real problem-sample table. Each Choice column with configured choices receives an All/value dropdown. Quick filters can be combined with the basic search and Advanced Search and are enforced by the backend follow-up endpoint. The Oldest problem sample requiring follow up indicator follows the current filtered result set, so it always identifies the oldest row remaining after the selected table, basic search, Quick Filters, and Advanced Search are applied.



## Persistent problem sample tracking links
- Each problem sample row has at most one secure tracking token/link. Once saved, that same link is reused.
- Workflow expiry leaves the token stored and blocks public access; staff revocation removes the link and invalidates its token permanently.
- The link expires 30 days after the latest **Current Workflow** transition into To be Disposed, Disposed, To be shipped back to client, Shipped back to client, To be back to testing, or Back to testing.
- Returning **Current Workflow** to CS Follow-Up clears the active tracking-link expiry.
- Every problem-sample table has read-only built-in Tracking Link and Tracking Link Expiry columns.

### Required role selection for new accounts
New staff accounts with no role are blocked by a non-dismissible role-selection modal until they explicitly choose Lab Technician or Customer Service. The modal has no close/cancel path, does not preselect a role, and saves through the existing `/api/auth/me/` role update endpoint. Existing accounts with a role are unaffected.

### Migration branch merge

The canonical migration graph includes `0045_alter_problemsample_acknowledgement_token` and the tracking-link branch, merged by `0047_merge_tracking_link_migration_branches`. This prevents migration conflicts when upgrading a working copy that retained the earlier 0045 token-field migration during ZIP overlay updates.

- Customer tracking options are driven by **Dispose Automatically** plus **Current Workflow**; the exact customer-facing choice label is preserved in response History.
- Staff-facing Tracking Link values wrap within their grid column so long secure URLs do not overflow the problem-sample form.

### Customer tracking actions
- Available while the workflow is not complete: Permit immediate disposal, Give us more details about this ticket, or Ship back.
- Customers may replace an earlier response, including while Current Workflow is **To be Disposed**, **To be shipped back to client**, or **To be back to testing**.
- **Give us more details about this ticket** returns Current Workflow to **CS Follow-Up**.
- Customer responses are locked once Current Workflow is **Disposed**, **Back to testing**, or **Shipped back to client**.


## Customer tracking signatures
Customers must type their name as a signature before submitting any tracking-page action. The signature is stored in History with that response.

- Customer **Give us more details about this ticket** responses open a required multiline modal (up to 4000 characters); the submitted information and typed-name signature are saved with the History event before the row moves to **To be back to testing**.

### Next.js production prerendering
Pages/components that use `useSearchParams()` are rendered below React `Suspense` boundaries. This is required by current Next.js production builds and prevents CSR-bailout prerender errors on `/problem-samples` and `/problems/new`.

## Current temporary staff authentication (supersedes earlier login-link notes)

Staff email magic-link/Brevo login is disabled. The current endpoints are `POST /api/auth/login/` for username/password sign-in and administrator-only `GET/POST /api/auth/accounts/` for account listing/creation. Accounts require First Name, Last Name, and a server-derived username; no email address is required. `UserProfile.is_admin` is the account-management permission. Existing Lab Technician/Customer Service values remain separate workflow roles.

## Customer Export administration

The **Customers** page is administrator-only. Administrators can see the current customer row count, upload replacement Customer Exports, search the directory, and review retained upload history including filename, timestamp, uploader, imported row count, and days since upload. The import history is retained across future replacement uploads. Specialized customer suggestion APIs used inside problem-sample forms remain available to authenticated non-admin users.

### Customer email history / unavailable recipient UX (2026-09-11)

- Every confirmed **Send Tracking Link** email is recorded as **Sent tracking link to customer by email**, including resends.
- **Email Customer** correspondence is recorded separately as **Sent an email to the customer** and never creates or activates a tracking link.
- Customer-notification history serialization now preserves the event-specific stored summary instead of overwriting it with one generic label.
- The problem-detail **Email Customer** button remains visible when no customer email can be resolved; it is disabled/greyed out and explains that no customer email is available on hover.


## Admin email templates

Administrators have an **Admin > Email Templates** page. The **Send Tracking Link** email subject and body are stored in the database and can be edited without redeploying the application. The `{{tracking_link}}` placeholder is mandatory for this template. **Email Customer** uses a separate editable general message. Other staff can read the tracking template to compose its email.

## Tracking link and customer email controls

Creating a ticket does not create an active tracking link. On the ticket detail page, **Send Tracking Link** prepares a secure URL, opens the tracking email in the staff member's email app, and activates the URL only after **I sent the email** is confirmed. Resending an existing link reuses its token. The first confirmed tracking-link email in CS Follow-Up may activate Dispose Automatically according to the existing workflow; general **Email Customer** messages do not change that field, the tracking link, or the customer-notified timestamp.

**Revoke Tracking Link** immediately invalidates the current URL for public pages, responses, and file downloads, and records the action in History. Staff may then use **Send Tracking Link** to issue a different token; the old URL remains invalid. An open-workflow ticket with no active link, including one whose link was revoked, appears in **Tracking Not Sent**. Existing 30-day workflow expiry rules still apply to links that have not been revoked.


### Client Email clipboard controls

Client Email fields include per-address **Copy** buttons and a **Copy All** button. Copy All copies every email currently kept in the field as a semicolon-separated recipient list suitable for pasting into Outlook.


## CS Follow-Up and fixed Status values

Migration `0052_cs_follow_up_and_fixed_statuses` renames the default Current Workflow from `Follow Up Required` to `CS Follow-Up` and standardizes Status across every table to `NEW`, `IN PROGRESS`, `ON HOLD`, `SHIPPED BACK TO CLIENT`, `DISPOSED`, and `COMPLETED`. Existing Status values are normalized into that set; unrecognized values become `NEW`.

## Dashboard
The Dashboard is tracker-wide across all problem-sample tables. "Opened" means the problem sample row's `created_at` timestamp. It shows rolling counts for the last 24 hours, 7 days, 30 days, 183 days, and 365 days plus an inclusive custom date range. The graph supports week, month, 6 months, year, and custom ranges and uses daily, weekly, or monthly buckets as appropriate.

**Tracking Not Sent** counts tickets across all tables whose Current Workflow is not a terminating or terminal workflow and which have no persisted `ProblemTrackingLink` row. Pending email tokens do not count as sent links. The Dashboard card links to the CS Follow-Up > Tracking Not Sent subtab; its selected-table list applies the same database filter before search and quick filters. The former NEW shortcut redirects there.

## Finished ticket deletion

Admin > Delete Old Tickets previews and deletes tickets whose **Current Workflow** is `Disposed` or `Shipped back to client` within an inclusive creation-date range. The default range has no lower bound and ends on the day before the configured-age anniversary of today's Edmonton date; this excludes tickets younger than the configured age. The administrator can select another start and end date, preview the count by workflow, and type `DELETE <count>` before confirming. The API checks administrator access and the exact previewed set inside a transaction; if matches changed, it refuses deletion and requires another preview. Deleting a ticket cascades to its tracking link and ticket-related records. Tickets waiting for disposal, shipping, or testing are excluded.

The administrator can define the **Old Tickets** age in whole calendar months (1–1200) on that page. Migration `0064_old_ticket_definition` initializes it to 24 months. The dashboard's **Old Tickets** card counts tickets in every table and workflow whose creation date is before the month-anniversary date in the Edmonton timezone. The cleanup tool's default end date is the preceding day, so its default deletion preview uses the same age cutoff; its preview still includes only finished workflows. A custom cleanup date range changes that one deletion preview and does not change the saved Old Tickets definition.

## Email not sent reason

Choosing **I didn't send the email** in the Send Tracking Link or Back to Testing dialog opens a required reason field prefilled with `Email unknown`. Blank reasons are rejected by the API (up to 500 characters). Those attempts record the reason in ticket History. Cancel closes the email preview without recording a sending decision. General **Email Customer** correspondence can be cancelled before confirming a send.

## Ticket table Image Search

Ticket tables include an **Image Search (N)** action. The count reflects the images attached to tickets in the table's current result set. Opening Image Search carries the current basic query, Advanced Search conditions/match mode, and Quick Filters into a dedicated image gallery. Gallery cards use large contained previews so images can usually be inspected without enlargement, while each image can also be opened in a full-screen viewer. Every image result includes a direct **Go to ticket** action.

### Direct camera capture
Staff can use **Take Photo** anywhere ticket images are added. The browser requests camera permission, prefers the rear/environment camera, captures a JPEG in-browser, and uses the existing ticket-image upload API. On the Create Ticket form the photo is queued until the tracking-link email step is finalized; on an existing ticket it uploads immediately after capture. Camera access requires HTTPS or localhost.
