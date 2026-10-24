# ALS Ticket Tracker — optional Microsoft 365 delegated mail

## Details for ALS IT / Security

- **Application name:** ALS Ticket Tracker
- **Application type:** Internal Web application, single Microsoft Entra tenant
- **API:** Microsoft Graph v1.0
- **Delegated permission:** `Mail.Send`
- **OAuth flow:** Authorization Code + PKCE (S256). Confidential Web client; backend uses an app secret to exchange the authorization code. Request OIDC `openid profile email` and `offline_access` for user verification and refresh. These are protocol scopes, not additional Microsoft Graph permissions.
- **Redirect URI type:** **Web**
- **Production redirect URI:** `https://als-problem-sample-portal.vercel.app/auth/callback` (domain was found in a previous tracker backup; verify that this is still the production deployment before sending to IT)
- **Local redirect URI:** `http://localhost:3000/auth/callback` (for localhost testing, register separately with IT)
- **Platform:** Next.js frontend deployed on Vercel; Django backend on Railway; PostgreSQL database.
- **Purpose:** Send ticket/customer/mention/system emails directly as the **signed-in, consenting staff member**. Graph requests `POST /me/sendMail` with `Mail.Send` delegated. There is no broad application-level Mail.Send permission.

## What IT must return

- Microsoft Entra tenant (directory) ID
- Application (client) ID
- Client secret (or request an approved certificate-based deployment adaptation)
- Admin consent / permitted staff-user access as required by tenant policies
- Confirm both redirect URIs registered as `Web`, exact match including scheme and path

## Configuration

Configure Railway Django environment variables:

- `FRONTEND_URL=https://als-problem-sample-portal.vercel.app` (if this remains the correct production deployment; no trailing slash)
- `MS_GRAPH_TENANT_ID=...`
- `MS_GRAPH_CLIENT_ID=...`
- `MS_GRAPH_CLIENT_SECRET=...` (backend only; never NEXT_PUBLIC)
- `MS_GRAPH_FERNET_KEY=...` (backend only, generated using Fernet.generate_key; **retain it** for token decryption across deployments)

On WSL use `FRONTEND_URL=http://localhost:3000` and register `http://localhost:3000/auth/callback` if testing locally. Set Next.js `BACKEND_API_URL` to your local Django `/api` endpoint (existing proxy configuration).

Run `python manage.py migrate` before `runserver`. This adds the `microsoft_graph` app's tables. Under **My Account**, click **Connect Microsoft 365**, sign into the same ALS email assigned by the admin, grant permitted scopes, and return to `/auth/callback`. The callback endpoint is reachable before IT config but cannot complete token exchange until valid IT credentials are installed.

## Security and email semantics

- Microsoft's login is optional. Existing tracker login, password, and role/lab enforcement remain unchanged.
- The OAuth state, session binding, PKCE verifier, nonce and Microsoft ID token are validated. Only the assigned ALS Microsoft email can link.
- Encrypted access and refresh tokens are stored server-side, never browser localStorage, never sent to the frontend.
- Individual staff can disconnect from My Account.
- `Mail.Send` delegated sends with staff identity and records in their Sent Items.
- Graph response `202 Accepted` means **accepted for processing**, not guaranteed delivery. The email workflow labels this as Email Sent/accepted and does not assume final delivery.
- If a Graph request times out, the send may still have happened. Check Sent Items and avoid blindly retrying. Server keeps an idempotency audit per request key.
- Email drafts that use `mailto:` remain available for staff not connected to Microsoft 365.
- SMTP or Graph mail won't function before ALS IT app registration, permissions, and credentials are configured.

## Testing

1. Use staging deployment or local testing account with IT-approved configuration.
2. Confirm callback returns successfully after login. Test invalid/expired state, wrong Microsoft email, or mismatched session (must reject).
3. Test To and CC, including Distributor CC rules; verify Graph `202` and mailbox Sent Items.
4. Confirm existing email sending still works for staff without Microsoft connection.
5. Create test ticket with Graph connected: after acceptance the ticket is finalized; after Graph failure it is not falsely marked sent.
6. Test monthly reports and Back to Testing notifications with an authorized Lab user.
