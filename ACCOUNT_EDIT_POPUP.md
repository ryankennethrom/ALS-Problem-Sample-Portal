# ALS Ticket Tracker — Staff account edit popup

## Application-level changes

- On Staff Accounts, **Edit Role / Email / Lab** now opens an accessible popup rather than showing an inline editing panel.
- The popup prepopulates the existing email, workflow role, and associated lab.
- Close using Cancel, the close (×) button, Escape, or the backdrop (unless a save is underway).
- Validation errors are displayed inside the popup; failed saves leave the editing form open.
- The existing PATCH endpoint and administrative permission checks are unchanged.

## Database-level changes

- No models, schema changes, or migrations added.
- Continue to run `python manage.py migrate` during deployment as usual.

## Verification

- Node frontend tests: 68 passed, including five new popup checks.
- All 85 frontend TypeScript files passed syntax parsing.
- Global CSS passed CSS parsing.
- All 215 backend Python files passed compilation.
- Full Django integration and live browser tests were not run.
