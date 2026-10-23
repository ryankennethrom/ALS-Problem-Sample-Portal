# Fill existing with — Add Column

Use **Settings → Tables → [table] → Add Column** to configure:

- **Default value**: pre-populates this field on tickets created after the column exists. Does not modify older tickets.
- **Fill existing with**: sets this column on tickets already present in the table, once when adding the column. Does not become a default for new tickets.

Both can be set independently. Either can be left empty for an optional column. If a required column is added to a table with existing tickets, **Fill existing with** must be provided to keep the older tickets complete, even if a Default value is set for future tickets.

Both inputs are validated against the column type, including Choice options, numeric values, email addresses, and staff groups. Boolean **No** and the number **0** are valid existing-ticket fill values.

Automatic/read-only types (Fixed Value, Date (Today), Row Creator, Recent Row Modifier) keep their existing automatic population behavior and don't offer a separate one-time fill input.

The backfill runs in the same transaction as column creation. The one-time value is not stored on the column definition; existing ticket values are saved in `ProblemSample.custom_values`. No new model fields or database schema migration are needed.

The `fill_existing_with` API key is accepted only on POST `/api/problem-columns/` and is not returned in column definitions or usable in PATCH requests.

## Tests

Frontend: `cd frontend && node --test tests/*.test.cjs`

Django (requires a local PostgreSQL test database with CREATEDB permission): `cd backend && python manage.py test problem_samples.test_fill_existing_column`
