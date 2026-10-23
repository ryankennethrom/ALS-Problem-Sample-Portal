# Administrator-managed account email and workflow roles

## What changed

- On **Staff Accounts → Create Account**, administrators must supply a first name, last name, unique `@alsglobal.com` email address, and either Lab or Customer Service workflow role.
- Administrators can update existing users via **Edit Role / Email** in the Accounts table, including users created before this change and their own profile. Administrator access is managed separately with the existing Make Admin/Remove Admin action.
- **My Account** displays the assigned role and email as read-only. Staff cannot update them with API requests (`PATCH /api/auth/me/` is rejected).
- Existing accounts with missing information are not silently changed. Staff see an instruction to contact an administrator. Administrators with incomplete information can still access Staff Accounts to complete their configuration.
- Changing email preserves appropriate Group-column defaults that referred to the old address, while changing roles clears incompatible Group-column defaults.

## Database changes

None. Existing Django User.email and UserProfile.role fields are reused. No new migrations are included.

## Verification

All frontend Node regression tests (45) passed, including five new account-management checks. All backend Python modules compile and frontend TypeScript files parse. Django integration tests were updated/added but were not run because the testing environment has no Django installation. Run them in an appropriately configured isolated test database:

```
cd backend
python manage.py test accounts --verbosity 2
```

## Deployment

Always run `python manage.py migrate` after updating backend code, even for updates without new migrations, then restart backend and frontend.
