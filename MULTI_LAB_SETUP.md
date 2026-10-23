# Multi-lab rollout guide

## Scope

This version introduces explicit Lab ownership for tickets, containers, pending ticket preparations, system emails, and creation-time reporting. An Edmonton (`EDM`) lab is seeded during migrations. All existing tickets and containers are assigned to Edmonton, retaining their data. Existing physical container numeric IDs are preserved as Edmonton-specific IDs (`EDM PC-00001`), and new labs start independent sequences (e.g., `CGY PC-00001`). Old bare `PC-...` identifiers are resolved as Edmonton for backward compatibility.

Each ticket table has a protected built-in `Lab` column. It is automatically populated by the server from the selected lab; staff cannot override it through ticket data. New and edited tickets must have a lab. For admins, `Lab: All` is an oversight view. Select an individual lab before creating or modifying a ticket or container.

## Administrator rollout (important)

1. **Take a verified backup of the production PostgreSQL database and media before deployment.** This release includes structural migrations and updates existing container/ticket ownership.
2. Deploy the backend and frontend from the same release. Run `python manage.py migrate` before accepting staff requests.
3. Sign in with an existing administrator account. If it has no lab, choose its lab in the first-login `Lab setup` page.
4. Switch the sidebar dropdown to **Lab: All**. Under **Lab Settings**, create any additional labs using stable uppercase codes, e.g., `CGY`.
5. Under **Staff Accounts** while viewing `Lab: All`, assign each existing account to its lab. Unassigned non-admin staff cannot sign in; this is deliberate. Check and correct roles/emails as needed.
6. Switch to each lab to edit its email template and configure **@Lab** and **@CustomerService** routing: either staff addresses of the appropriate role in that lab or explicit email addresses.
7. Verify one test ticket and one new container in each lab, then check Dashboard, Customer Service, Shipping, Testing, and Tickets scoping.

## Navigation and permissions

- Sidebar `Lab: Edmonton` / other labs / `Lab: All` (administrator only). Staff are restricted to their assigned lab, including direct API requests.
- Dashboard, Customer Service, To be shipped, To be back to testing, Tickets, containers, and System Emails honor the selected lab.
- Manage Tables, Delete Old & Finished Tickets, and Backup & Restore are available only to admins viewing **Lab: All**.
- Staff Accounts lists only accounts in the selected lab; `Lab: All` shows all staff, including unassigned accounts.
- Admin users may select their own lab at setup. Regular staff must be assigned a lab by an admin prior to login.

## Database migrations

- `accounts.0007_lab`
- `problem_samples.0089_multi_lab`
- `problem_samples.0090_system_email_lab`
- `problem_samples.0091_timing_lab`
- `problem_samples.0092_prepared_lab`

These migrations retain historical tickets and assign their lab to Edmonton; legacy notification recipients are preserved. **Do not run `makemigrations` to replace the bundled migration sequence during rollout.**

## Checks and limitations

- Existing Node-based frontend regression tests and static TS/Python parsing passed in the build environment.
- Django/PostgreSQL integration tests were added but could **not** be executed in the build environment because Django and the test database were unavailable. Run `python manage.py test problem_samples.test_multi_lab` using an isolated, appropriately permissioned test database before deploying to production.
- After deployment, validate your configured email templates and Outlook draft recipients at each lab. Emails are still opened in the user's mail application and require staff confirmation.
- **The Lab All view is for oversight/maintenance, not ticket edits.** Choose a specific lab to create/edit content.
