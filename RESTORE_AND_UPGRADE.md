# Restore and Upgrade an older Full Backup

## What the feature does

As an administrator in **Lab: All**, go to **Backup & Restore → Restore and Upgrade Older Full Backup**. Upload an older `.tar.gz` Full Backup, then select **Check backup compatibility**. The application reads its manifest, checks the checksum and migration graph, and shows the exact number of unapplied migrations relative to the backup. It refuses backups newer than the running database, incompatible/divergent migration histories, missing migration files, or already-matching schemas (use regular restore for those).

The upgrade process **does not load historical data into the current live schema**. It creates an isolated PostgreSQL database (or a random private schema if CREATEDB is unavailable), migrates to the old schema, loads the historical JSON fixture using historical Django models, applies all remaining migrations, then exports an upgraded fixture. Only after successfully creating that fixture does it transactionally replace the active application's business records and finally restore the archived media.

## Mandatory precautions

1. **Do not try this first on production.** Use a staging copy of the application and database first. Restore backups containing sensitive customer data only on ALS-approved infrastructure.
2. Make and download a **fresh Full Backup of the current system** and verify that you can retain and access it. The old backup **replaces** all current database data and media, so newer work will be lost.
3. Schedule a maintenance window; no other employees/customers should use the application during the operation. The backup/restore file lock does not suspend all ordinary API writes.
4. The PostgreSQL connection role needs either `CREATEDB` or permission to create a private schema in the current database. This feature never grants privileges automatically. If both permissions are missing, the new option is disabled before restore. Use a separately authorized database environment or seek approval from IT. The existing test-database CREATEDB limitation may apply here too.
5. Ensure disk space for both the temporary staging database and upgraded JSON fixture, and enough media storage. Old migration files must remain in the deployed source tree.
6. **Media files are not transactional**: if a disk error occurs after the upgraded database is loaded, some files can have been changed. The fresh current Full Backup is your recovery plan. A failed or timed-out server request must be investigated before retrying.
7. A sufficiently large backup may exceed your deployment's HTTP timeout. For a large production recovery, run the process with an operations-managed maintenance window and long-running worker rather than a short HTTP request.

## Steps

1. Deploy matching updated **backend** and **frontend** versions.
2. Back up the current system and put it into a maintenance window.
3. Apply the existing schema migrations on the current app: `python manage.py migrate`.
4. In **Lab: All → Backup & Restore**, select **Restore and Upgrade Older Full Backup**, choose the old Full Backup, and click **Check backup compatibility**.
5. If compatible and the staging DB permission check passes, confirm the safety checkbox and type `UPGRADE AND RESTORE FULL BACKUP`.
6. After it completes, sign in again and check tickets, users, lab assignments, containers, and image attachments. Compare totals with the backup/source.

## Database permission example (local development only)

Ask a PostgreSQL administrator to grant `CREATEDB` to the dedicated local test role *only after* reviewing the security implications. Do not grant this permission casually to the shared production role.

```sql
ALTER ROLE problem_sample_tracker CREATEDB;
```

On a managed Railway database, this permission may be unavailable or prohibited. The application can use a separate private schema when database-level `CREATE` is available; otherwise stage the upgrade on an approved PostgreSQL instance.

## Limitations

- Supports **upgrades only**, not downgrades or divergent migration branches.
- Uses Django JSON fixture format (backup format v1). PostgreSQL physical backups / arbitrary `.sql` or ZIP files are not accepted.
- This feature was syntax- and static-tested in the build environment, but **not integration-tested with a working PostgreSQL instance**. Run a full end-to-end staging recovery before treating it as production-ready.

## Staging worker troubleshooting (October 2026 update)

The worker now patches `django.core.serializers.python.Deserializer._get_model_from_node`
(rather than the nonexistent module-level `_get_model`) while reading a historical
JSON fixture. The patch is scoped to the isolated process and restored on errors.

If an upgrade still fails, the backend's `Backup restore rejected ...` message
will include a safe execution phase, exception type, and source file/line, for
example `load historical JSON fixture: ValueError at fields.py:123`.
This does **not** mean any live data was changed. Do not repeatedly retry a
production restore until the failure is understood. Create a fresh independent
Full Backup and verify restoration using a disposable local/staging database.
