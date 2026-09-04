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

- `/` — open a Problem Sample Table, search it, and see standard + custom columns
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

The temporary MVP uses administrator-created username/password accounts. An administrator creates an account from **User Accounts** by entering First Name and Last Name. The server derives a lowercase username such as `jane.smith` (adding a numeric suffix for duplicates), generates a cryptographically random password, and stores only Django's password hash. Email is not required. The generated password is returned only in the account-creation response so the administrator can hand it to the user.

Administrator permission is separate from the existing **Lab Technician** / **Customer Service** workflow role. Regular users still choose one of those workflow roles after first login. From **User Accounts**, an administrator can grant or remove administrator access for another user, reset another user's password to a newly generated random password, and delete another user. Password reset revokes that user's existing tracker sessions. These account-management actions cannot be used on the administrator's own account from the User Accounts page. Every authenticated user, including administrators, can change their own password from **My Account** by entering the current password and a new password of at least 12 characters. The new password is saved with Django's password hashing; other active tracker sessions for that account are revoked while the session performing the change remains signed in. The initial administrator is bootstrapped with `python manage.py create_tracker_admin --first-name <First> --last-name <Last>`. Microsoft Entra ID can later replace this temporary login layer and add staff email identities without changing the problem-sample domain model.

## Railway deployment

Deploy the backend and frontend as separate Railway services and attach PostgreSQL to the backend. Before putting real ALS customer data on personally managed external hosting, confirm that the external hosting arrangement is approved.


## Dynamic tables

New Problem Sample Tables start with only the protected auto-incrementing **Problem ID** column. Users add only the other fields that table needs (text, long text, number, choice, multiple choice, date, date/time, time, yes/no, email, URL, Fixed Value, Group, Distributor, End User, Client Email, and Row Creator). Constant values such as a lab or site name should be represented with the general-purpose **Fixed Value** column type.

## User roles

Regular accounts choose **Lab Technician** or **Customer Service** after their first username/password login. This remains workflow/profile metadata. **Administrator** is a separate security permission used for account creation and is not selectable from My Account.


### Customer-service email template

Creating a problem sample automatically invokes **Email Customer** when the selected table has a populated email column. On this initial creation email, the customer address(es) and `NAEDM.DE@ALSGlobal.com` are placed in **To**. No automatic CC recipient is added. The manual **Email Customer** button on an existing problem sample continues to address the selected customer email(s) only.

For **one customer recipient**, the app looks up that exact email in the current Customer Export and uses its unique `PrimaryContact` value when one is available (for example, `Hi Jane Smith,`). If the address is manual, missing from the export, or maps to conflicting contact names, it safely falls back to `Hi there,`. The internal `NAEDM.DE@ALSGlobal.com` copy does not cause the message to switch to the multiple-customer wording.

For **multiple customer recipients**, the message uses `Hi there,` and explains that ALS does not currently know the primary contact for the affected samples. Both templates include Problem ID plus useful populated row details such as Date Received, sample tracking number, number of problem samples, Problem Type, Issue Description, and courier/tracking information when those columns exist. The subject includes the Problem ID when available. The old customer-service phone sentence has been removed from the message.


## Built-in Problem ID

Every Problem Sample Table contains a non-editable **Problem ID** column. IDs are positive auto-incrementing numbers allocated independently within each table. Users cannot edit or delete this system column.

## Advanced search

Every Problem Sample Table has an **Advanced Search** panel generated from that table's column definitions. Users can combine up to 20 conditions and choose whether to match all conditions or any condition. Operators adapt to the field type, including text contains/equals, numeric comparisons and ranges, choice values, dates/date-times/times, yes/no, and empty/not-empty checks. The ordinary fuzzy search box can be used at the same time as advanced filters.

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

Problem sample details include a History panel at the top. Creating a row, saving row changes, adding a comment, and confirming **I sent the email** after the initial customer-notification draft create timestamped activity entries associated with the authenticated user. The email confirmation is recorded as **Sent an email to the customer**; choosing **I didn't** simply continues without adding that event. Update entries include before/after values for changed fields.

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


### Recent Row Modifier column
A `Recent Row Modifier` column is server-controlled and read-only. It contains the email (or username fallback) of the authenticated user who most recently saved the problem-sample row. Existing rows are backfilled from `modified_by` / legacy modifier metadata, falling back to creator metadata when needed.


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

The sidebar includes **Shipping → To be shipped**. This page shows only problem samples whose workflow Status is **To be shipped back to client**. Users can search the queue, select one or many rows (including Select all visible), and choose **Ship Selected**. The backend validates the selection transactionally and changes every selected row to **Shipped back to client**, updates Recent Row Modifier fields, applies the existing tracking-link status-transition timing, and writes a History entry for each row. Completed **Shipped back to client** rows disappear from the queue and continue to be ignored by container disposal readiness/disposal.

## Required Status workflow and container disposal
Every problem sample table has a built-in **Status** choice column with exactly eight fixed values: **Automatically Disposed**, **Halted Automatic Disposal**, **To be Disposed**, **To be shipped back to client**, **To be back to testing**, **Back to testing**, **Disposed**, and **Shipped back to client**. No additional status values can be added, renamed, or removed. New rows default to **Halted Automatic Disposal**. Confirming **I sent the email** for the first time changes Status to **Automatically Disposed**. Each transition into **Automatically Disposed** starts a fresh table-configured expiration period. A customer action then routes the sample to the selected workflow state.

A container is **Ready to Dispose** when it contains at least one problem sample and every non-ignored sample is either marked **To be Disposed**, or is marked **Automatically Disposed** and has passed its table's Problem Sample Expiration Period. **Halted Automatic Disposal** does not become disposal-eligible automatically after expiration; it must first be explicitly changed to **To be Disposed**. The Containers page highlights ready containers and provides a **Dispose Container** action. Disposing a container records who disposed it and when, changes every disposal-participating problem sample's Status to **Disposed**, leaves **Shipped back to client** samples unchanged, updates Recent Row Modifier fields, records the changed statuses in History, and stores a rollback snapshot of the pre-disposal sample state. A disposed container exposes **Undo Disposal**, which restores that snapshot, clears the container's disposal stamp, and records an undo event in each sample's History. If any contained sample was manually changed after disposal, the undo is blocked rather than overwriting the newer change. Containers disposed before rollback snapshots existed fall back to the recorded disposal History to restore the previous Status when possible.


### Changing a problem sample container
An existing problem sample can be moved to another active container from its detail/editor page by changing **Container ID** and choosing **Save Changes**. The API validates the target Container ID and records the old and new Container IDs in row History. Because container readiness is derived from current membership, both the source and destination container readiness states reflect the move immediately. Samples cannot be moved into or out of a disposed container; undo the container disposal first. New samples also cannot be assigned to a disposed container.

## Customer problem sample tracking links
Customer notification emails include a public secure Problem Sample Tracking URL. In the generated email, the tracking URL is visually separated with a clear label and blank lines before and after the URL so it stands out from the surrounding message. The tracking page includes a **Problem Sample Details** section using the same customer-safe field selection as the notification email: core sample/hold information plus populated fields explicitly marked **Include in customer notification**; staff-only user/email fields are excluded. Customers do not need an ALS account and there is no separate access/verification code or acknowledgement button. A GET/page preview does not acknowledge the row. When the current Status is **Automatically Disposed**, the page tells the customer how many days remain until the sample(s) are up for disposal (or that they are up for disposal now) and offers **Stop eventual disposal**, **Permit immediate disposal**, and **Ship back**. These map to **Halted Automatic Disposal**, **To be Disposed**, and **To be shipped back to client** respectively. For other unresolved pre-response states the page retains the generic **Dispose Sample(s)**, **Ship back samples**, and **Hold sample** choices. The first explicit choice both records `acknowledged_at` (and the customer-acknowledgement History event) and applies the selected action in the same request. If it is left unanswered, the link remains in its pre-acknowledgement state. The Problem Sample Tracking Link follows a fixed 30-day post-status window once acknowledgement occurs. If the row's workflow Status is **Disposed**, the public link shows **Problem Sample Dumped**. If the Status is **Shipped back to client**, it shows **Shipping samples back to client**. Being past the problem sample expiration period alone never displays the dumped message.

## Problem Sample Tracking Link lifecycle

Public Problem Sample Tracking Links use a fixed 30-day window after actual customer acknowledgement while Status is `Halted Automatic Disposal`, or after the most recent Status change to `To be Disposed`, `To be shipped back to client`, `To be back to testing`, `Back to testing`, `Disposed`, or `Shipped back to client`. A change between those statuses before expiry resets the 30-day window. Returning to `Automatically Disposed` before expiry clears the window and restores the public page to its pre-acknowledgement state. Once a 30-day window has elapsed, the old link remains unavailable and its acknowledgement token is permanently cleared from the database on the next backend request. Migration 0031 also clears credentials for rows that are already expired when it is applied.

### Acknowledgement credentials are committed only after confirmed send

When a customer notification is prepared, the backend returns a temporary secure acknowledgement token without saving it to the ProblemSample row. New Problem Sample Tracking Links use `secrets.token_urlsafe(48)`, providing about 384 bits of cryptographic randomness. Existing UUID links remain valid after migration, but all newly generated links use the stronger token format. Migration `0043_secure_acknowledgement_token` converts the stored token field to a URL-safe string while preserving existing tracking URLs. The public problem sample tracking endpoint therefore cannot resolve a newly prepared link yet. Clicking **I sent the email** sends the prepared token back to the backend, which persists it together with the confirmed notification timestamp and normal status transition. Cancelling the launch or choosing **I didn't** leaves the database token empty. Migration `0044_remove_customer_access_code_hold_sample` removes the old customer acknowledgement-code field and converts the old `neither` customer action to `hold`.


### System-owned emailed status
`Automatically Disposed` and `Halted Automatic Disposal` are both fixed workflow states. New rows default to `Halted Automatic Disposal`. The **first** confirmed customer email changes Status to `Automatically Disposed`, and entering that status starts a fresh table-configured automatic-disposal expiration period. Later resend confirmations do not restart the period unless Status actually transitions into `Automatically Disposed` again.


## Shipping-back status

`To be shipped back to client` records a pending return. Customer selection of **Ship back samples** sets this status. Once staff completes the return, set `Shipped back to client`. Completed shipped-back samples are ignored for container disposal readiness and are not changed when a container is disposed.

## Follow-Up Required queue

The Problem Samples navigation includes **Follow-Up Required**, a cross-table queue ordered oldest-first. It excludes disposal and shipping workflow states; **To be back to testing** and **Back to testing** remain visible because they are neither disposal nor shipping states.


### Follow-Up Required ordering
The Follow-Up Required queue is ordered by problem sample creation time, oldest first, so the longest-waiting samples appear at the top.

### Back To Testing queue

The sidebar includes **Back To Testing → To be back to testing**. This page shows only samples whose workflow Status is **To be back to testing**. Users can search the queue, select one or many rows (including Select all visible), and choose **Back to Testing**. The backend validates the selection transactionally and changes every selected row to **Back to testing**, updates Recent Row Modifier fields, applies the tracking-link lifecycle transition, and writes a History entry for each row. Completed rows disappear from the dedicated queue. Both testing statuses block container disposal.

Migration `0035_back_to_testing_statuses.py` updates every built-in Status column to include the two testing workflow values.

- Follow-Up Required now displays a prominent Oldest problem sample requiring follow up indicator based on the oldest eligible sample creation timestamp; it refreshes the displayed age every minute.

### Follow-Up Required automatic-disposal countdown

The Follow-Up Required queue shows a **Days until up for disposal** column. Only samples in **Automatically Disposed** have an automatic-disposal countdown, based on the most recent transition into **Automatically Disposed** plus the table's Problem Sample Expiration Period. Rows become progressively red as the deadline approaches; at zero days the row is deep red and displays **Eligible now**. **Halted Automatic Disposal** displays **Not automatic**.

### Follow Up Required navigation
`Follow Up Required` is a top-level sidebar tab rather than a sub-item under `Problem Samples`. Its queue behavior, oldest-first ordering, age indicator, automatic-disposal countdown, and row urgency shading are unchanged.

## Disposal workspace

The previous top-level **Containers** navigation is now **Disposal** with two subpages:

- **Dispose Containers** (`/disposal/containers`) retains container creation, readiness, disposal, and undo-disposal workflows. Its internal **Ready to Dispose** view is at `/disposal/containers/ready-to-dispose`. Legacy `/containers` URLs redirect to the new locations.
- **Dispose Samples** (`/disposal/samples`) provides a ranked search across problem IDs, tracking values, customers, and searchable dynamic fields. Staff can dispose a single result immediately or select multiple results and dispose them together.

Direct sample disposal is transactional, records a **Disposed sample** history entry with the Status change, updates Recent Row Modifier fields, and applies the tracking-link status lifecycle. A sample in an already-disposed container must have the container disposal undone first. Samples already **Disposed** cannot be disposed again.

Container readiness and container disposal now ignore samples already **Disposed** in addition to samples **Shipped back to client**, because those samples are no longer part of the physical container disposal workload.

- Disposal → Dispose Containers now defaults to the Ready to Dispose view; All Containers remains available as a secondary tab.

## Workflow queue search improvements

The workflow queues now use normalized search behavior so user-facing Problem ID queries such as `Problem #6`, `Problem ID #6`, `#6`, and `6` resolve correctly. This applies to Follow Up Required, Dispose Samples, Shipping > To be shipped, and Back To Testing > To be back to testing.

Those four pages also include Advanced Search. Advanced conditions can target Problem ID, table, workflow status, container, distributor, end user, brand, ALS/courier tracking fields, created/modified time, or all custom field values. Conditions can match all or any rules. Dispose Samples can run Advanced Search without requiring a basic search term.


## Sidebar navigation

Sidebar navigation is grouped into **Workflows**, **Tables**, and **Settings**. Workflows contains Follow Up Required, Disposal, Shipping, and Back To Testing; Tables contains Problem Samples and Manage Tables; Settings contains Customers, My Account, and Logout. Follow Up Required uses a clock icon.

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
- The fix applies to Follow Up Required, Dispose Samples, To Be Shipped, To Be Back to Testing, and the shared table Advanced Search styling.


## Advanced Search alignment update
- Advanced Search buttons now align directly with the search input instead of centering against the label + input block.
- The button height matches the 38px search input across shared workflow/table search layouts.


### Customer notification files
Images and attachments remain stored with problem samples, but **Email Customer** always opens the normal `mailto:` email-client flow. Stored files are not attached to customer notification emails and no `.eml` draft is generated because files exist on the sample. The public Problem Sample Tracking page shows those stored images/files through token-scoped endpoints while the Problem Sample Tracking Link remains valid; after link expiry/token purge, those endpoints return not found.

- Customer notification emails tell recipients that the Problem Sample Tracking page may contain images or files associated with the problem sample(s).

## Required reason for staff changes

Staff-driven changes to existing problem-sample rows require a reason. The detail-page Save Changes action, Dispose Samples bulk action, Shipping bulk action, Back To Testing bulk action, container disposal, and container-disposal undo all prompt for a reason before the change is submitted. The backend also rejects these mutations when no reason is supplied. The reason is stored in the existing ProblemHistory JSON details and displayed in the row History alongside the field changes. System/customer-driven events such as customer acknowledgement and customer-notification confirmation are not prompted for a staff reason.

## Follow Up Required table selection

Follow Up Required is explicitly scoped to a selected Problem Sample Table. The table dropdown uses the real `ProblemTable` relationship, and the queue renders that table's actual columns instead of a fixed set of inferred workflow fields. Basic and Advanced Search are also evaluated against the selected table's real searchable columns. The selected table's follow-up rows remain oldest-first.


## Halted automatic disposal default

New problem samples default to **Halted Automatic Disposal**. Migration `0037_halted_automatic_disposal_default.py` updates existing Status-column defaults and the model-level default without changing the workflow status of existing problem-sample rows. The halted workflow state does not by itself mean the customer has acknowledged; acknowledgement remains tracked by `acknowledged_at`, and a default-halted sample remains unacknowledged until the customer selects one of the public-link actions.

## Built-in automatic-disposal countdown

Every problem-sample table now includes a read-only **Days until up for disposal** built-in column immediately after **Status**. It is computed from **Date Created + the table's Problem Sample Expiration Period**. It shows **Not automatic** when automatic disposal is halted, **Eligible now** at the deadline, or the remaining whole-day countdown otherwise.


### Automatic disposal expiration anchor
- Entering **Automatically Disposed** always starts a fresh Problem Sample Expiration Period.
- The first confirmed customer email changes a halted sample to **Automatically Disposed**, so that first transition starts the period.
- Saving a row that is already **Automatically Disposed** does not reset the period; the status must actually transition into it.
- Customer acknowledgement changes the sample to **Halted Automatic Disposal**. A later staff transition back to **Automatically Disposed** starts another fresh period.

## Optional change-reason modal

Staff-driven problem-sample changes use a dedicated modal instead of `window.prompt`. The modal offers Continue with a reason, Skip, and Cancel. Reasons remain limited to 1000 characters and are included in the existing history details when supplied. Skip permits the change without storing an empty reason; Cancel aborts the action. The backend accepts an omitted reason while continuing to enforce the maximum reason length.

### Customer acknowledgement history wording

Customer acknowledgement history entries display **Customer acknowledged problem sample**. When acknowledgement changes a row field (normally Status from **Automatically Disposed** to **Halted Automatic Disposal**), History stores and displays the before/after field values.


## Customer email history field changes

**Sent an email to the customer** history events now include the before/after values of any problem-sample fields changed by confirming the email. On the first confirmed email, this normally includes **Status** changing from **Halted Automatic Disposal** to **Automatically Disposed** and **Days until up for disposal** changing from **Not automatic** to the newly restarted expiration countdown. Later email sends that do not change row fields remain simple email history events without an empty change list.

## Follow Up Required quick filters

The Follow Up Required workflow exposes a Quick Filters section for the currently selected real problem-sample table. Each Choice column with configured choices receives an All/value dropdown. Quick filters can be combined with the basic search and Advanced Search and are enforced by the backend follow-up endpoint. The Oldest problem sample requiring follow up indicator follows the current filtered result set, so it always identifies the oldest row remaining after the selected table, basic search, Quick Filters, and Advanced Search are applied.



## Persistent problem sample tracking links
- Each problem sample row has at most one secure tracking token/link. Once saved, that same link is reused.
- Tracking tokens are never purged from the database. Expiry controls public accessibility only.
- The tracking link expires 30 days after the latest Status transition into To be Disposed, Disposed, To be shipped back to client, Shipped back to client, To be back to testing, or Back to testing. Each later transition into one of those statuses resets the 30-day expiry.
- Halted Automatic Disposal and Automatically Disposed do not themselves start/reset tracking-link expiry.
- Every problem-sample table has read-only built-in Tracking Link and Tracking Link Expiry columns.

- Returning a problem sample to `Automatically Disposed` or `Halted Automatic Disposal` clears the active tracking-link expiry and makes the same persistent tracking link accessible again.

### Required role selection for new accounts
New staff accounts with no role are blocked by a non-dismissible role-selection modal until they explicitly choose Lab Technician or Customer Service. The modal has no close/cancel path, does not preselect a role, and saves through the existing `/api/auth/me/` role update endpoint. Existing accounts with a role are unaffected.

### Migration branch merge

The canonical migration graph includes `0045_alter_problemsample_acknowledgement_token` and the tracking-link branch, merged by `0047_merge_tracking_link_migration_branches`. This prevents migration conflicts when upgrading a working copy that retained the earlier 0045 token-field migration during ZIP overlay updates.

- Customer tracking options are status-aware: Automatically Disposed shows **Stop eventual disposal**, **Permit immediate disposal**, and **Ship back**; the exact customer-facing choice label is preserved in the response/history.
- Staff-facing Tracking Link values wrap within their grid column so long secure URLs do not overflow the problem-sample form.


### Customer tracking actions by follow-up status
- **Automatically Disposed:** Stop eventual disposal, Permit immediate disposal, Fill out requested information (if applicable), or Ship back.
- **Halted Automatic Disposal:** Permit immediate disposal, Fill out requested information (if applicable), or Ship back.
- **Fill out requested information (if applicable)** sets the problem sample to **To be back to testing**.
- Returning/staying in **Halted Automatic Disposal** keeps the current halted-state choices available on the tracking page, so a customer can later permit disposal, provide requested information, or request shipment back.


## Customer tracking signatures
Customers must type their name as a signature before submitting any tracking-page action. The signature is stored in History with that response.

- Customer **Fill out requested information (if applicable)** responses open a required multiline modal (up to 4000 characters); the submitted information and typed-name signature are saved with the History event before the row moves to **To be back to testing**.

### Next.js production prerendering
Pages/components that use `useSearchParams()` are rendered below React `Suspense` boundaries. This is required by current Next.js production builds and prevents CSR-bailout prerender errors on `/` and `/problems/new`.

## Current temporary staff authentication (supersedes earlier login-link notes)

Staff email magic-link/Brevo login is disabled. The current endpoints are `POST /api/auth/login/` for username/password sign-in and administrator-only `GET/POST /api/auth/accounts/` for account listing/creation. Accounts require First Name, Last Name, and a server-derived username; no email address is required. `UserProfile.is_admin` is the account-management permission. Existing Lab Technician/Customer Service values remain separate workflow roles.
