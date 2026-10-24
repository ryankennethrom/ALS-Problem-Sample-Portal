# Lab Selector Redesign

## Application-level changes

- Replaced the native sidebar lab `<select>` with a styled menu for administrators. Each option displays the lab name, a short code, and a visual indication of the currently selected lab. The "All Labs" option remains administrator-only.
- The selector supports click/touch and keyboard navigation (Arrow Up/Down, Home/End, Escape, Tab), and closes when clicking outside. When the sidebar is collapsed, activating the selector first expands the sidebar so the menu is not clipped.
- Non-admin staff see their assigned lab as a non-interactive, read-only card. When the app loads their account, any previous lab selection is replaced with their assigned lab. Backend scoping already rejects non-admin requests for other labs or Lab: All.
- This change does not modify the Lab Settings management page or staff lab assignments.

## Database-level changes

None. No new migrations were added. Always run `python manage.py migrate` during installation to apply any migrations already present.

## Verification

- Frontend Node regression tests: 73 passed.
- TypeScript/TSX syntax: 83 files parsed successfully.
- CSS syntax: passed.
- Backend Python syntax: 215 files parsed successfully.
- Django cross-lab regression tests were added, but not executed here because Django is not installed in the execution environment.
- Live browser rendering / accessibility testing was not performed.
