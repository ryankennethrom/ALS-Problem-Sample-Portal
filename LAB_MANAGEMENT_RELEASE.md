# Lab management and sidebar usability update

## Changes

- Lab Settings → Lab: All: administrators can create a lab, rename it, and delete it if unused.
- Lab code is immutable; renaming a lab does not affect identifiers such as `EDM PC-00001`.
- Deleting is refused when any related ORM record references the lab, including staff profiles, tickets, containers, reporting records, prepared tickets, timing records, and lab-specific email templates. The API returns HTTP 409 with reference counts. The last remaining lab is not deletable.
- `GET /api/auth/labs/` now includes `can_delete` and `references` for admins, without changing staff's normal lab listing.
- `PATCH /api/auth/labs/<id>/` changes the lab's name; `DELETE` removes an unused lab. Both are administrator-only.
- Improved dark sidebar lab selector. Lab list refreshes after add/rename/delete.
- Sidebar navigation uses the remaining viewport height and scrolls independently on mobile and desktop. Logout stays visible in the footer, even with many expanded sections.

## Application and database changes

Application: Django API and Next.js sidebar/settings UI changes.
Database: no new schema fields or migrations. Existing Lab model and relationships are reused. Continue running `python manage.py migrate` on deployment.

## Validation

- `cd frontend && node --test tests/*.test.cjs`
- `cd frontend && npm run test:lab-management`
- `cd backend && python manage.py test accounts.test_lab_management`

Django integration tests need Django and a test PostgreSQL database. They were added but could not execute in this packaging environment because Django was unavailable.
