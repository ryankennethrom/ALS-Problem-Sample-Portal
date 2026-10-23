# ALS Ticket Tracker — Historical Backup Upgrade / Natural User Keys Fix

## Symptom

`POST /api/admin/backup-restore/restore/` returns HTTP 400 for **Restore and Upgrade Older Full Backup**. The backend logs:

```
Isolated backup upgrade failed. No live data was changed.
load historical JSON fixture: DeserializationError at python.py:188
```

## Cause addressed

Older Django JSON backups write `auth.user` records without numeric primary keys (`natural_primary=True`) and write references to those accounts using username-based natural keys (`natural_foreign=True`). Django's historical migration-state models do not preserve all behavior of the live models; natural-key lookup of the historical User model can therefore fail during `loaddata`.

Before loading, the **isolated staging worker only** now normalizes the backup's user records into stable numeric IDs and translates foreign keys / many-to-many fields known (from the historical migration-state schema) to target `auth.User`. It never rewrites arbitrary JSON arrays or changes the original backup file. Missing and duplicate references are rejected instead of silently dropped.

## Data safety

- Only the isolated temporary staging fixture is transformed; the source `.tar.gz` is untouched.
- Staging migration and loading must succeed before the application attempts to replace the live database.
- Existing backup inspection and migration-ancestry checks remain in place.
- A rollback of database changes cannot guarantee rollback of external media storage. Take a full backup beforehand and use a staging DB for the first restore.
- The upgrade worker now includes chained **exception types** in safe error logs, but never prints fixture contents, passwords, emails, or raw DB errors.

## Installation

1. Back up the current database and media before installing or testing.
2. Install the new ZIP, run `python manage.py migrate`, restart the Django backend.
3. In Lab: All → Backup & Restore, inspect the **old original** Full Backup and choose **Restore and Upgrade**, not Regular Full Restore.
4. Use a disposable staging/local database for the first end-to-end test.
5. Verify staff accounts, ticket ownership, container IDs, lab associations, media, and counts before attempting a production restore.

## Verification executed in the build environment

- 7 pure-Python historical-user normalization tests passed.
- 60 frontend regression tests passed.
- A structural transformation against the provided older fixture retained all 21,212 records; it normalized 9 natural-key users and 85 user references without altering unrelated fields.
- Python syntax compilation and archive integrity passed.

**Not verified:** live Django/PostgreSQL fixture deserialization and restoration. This patch addresses a plausible cause of the observed `DeserializationError`, but no claim of fully successful restoration should be made until a full staging test passes.
