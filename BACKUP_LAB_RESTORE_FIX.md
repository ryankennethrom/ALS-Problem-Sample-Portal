# Full Backup / Restore: missing laboratory records fix

## Root cause

The Multi-Lab release added the `accounts.Lab` model, but the explicit
`dumpdata` model list in `backend/problem_samples/backup_restore.py` still
included only `accounts.userprofile`, not `accounts.lab`. Thus a backup
could contain `lab_id=1` on a user profile, ticket, email template, or
container without containing the referenced lab row. On restore, the
PostgreSQL foreign key check failed with:

    accounts_userprofile_lab_id ... Key (lab_id)=(1) is not present in table "accounts_lab"

## Corrections

- Include `accounts.lab` BEFORE `accounts.userprofile` in all future
  database and full backups. The same export list is used by the isolated
  Restore-and-Upgrade worker, so upgraded fixtures also include labs.
- Validate that the generated backup contains at least one Lab, and all
  included references to Lab resolve to an included Lab row.
- Validate the fixture AGAIN before Full Restore or Database Restore runs
  `flush`, returning a clear error for incomplete/old archives.

## Updating and testing

1. Install this project update, including the backend.
2. Run `python manage.py migrate` before starting Django.
3. While your current database is still intact, download a **NEW Full Backup**.
4. Verify the new archive contains Lab records with the local check below.
5. Restore the new archive into an isolated **staging** database first, and
   verify users, containers and tickets. Do not test destructive restoration
   on production until a staging restore has succeeded.

Inspect an archive's serialized Lab records:

    tar -xOzf your-full-backup.tar.gz database.json | python3 -c 'import json,sys; a=json.load(sys.stdin); print("Labs:",[(x["pk"],x["fields"].get("code"),x["fields"].get("name")) for x in a if x["model"]=="accounts.lab"])'

If that prints `Labs: []`, the archive was made with the broken exporter.
Updating the application does **not** rewrite older backup files.

## Previously downloaded backups

An incomplete same-version archive cannot safely be restored without its
missing lab information. If the original application database still exists,
install this fix and download a fresh backup. Otherwise, recover the exact
lab records from another trusted backup or an authorized administrator's
records, and repair the archive on a copy before attempting a staging restore.
Never invent a lab reference or bypass the foreign-key checks.

## Verification

The new `problem_samples.test_backup_lab_integrity` tests are Django
SimpleTestCase tests and do not require PostgreSQL test database creation:

    python manage.py test problem_samples.test_backup_lab_integrity -v 2

An actual end-to-end PostgreSQL restore is still required for production
confidence.
