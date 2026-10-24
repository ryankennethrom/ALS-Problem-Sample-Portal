# Microsoft Entra App Registration Request — ALS Ticket Tracker

Application Name: ALS Ticket Tracker
Application Type: Web Application (Internal Use Only; single-tenant Microsoft Entra ID)
Target API: Microsoft Graph API v1.0
Required API Permissions: Mail.Send (Delegated)
Authentication Flow: OAuth 2.0 Authorization Code Flow with PKCE (S256)
Microsoft Entra Platform / Redirect URI Type: Web
Production Redirect URI: https://als-problem-sample-portal.vercel.app/auth/callback
Local Development Redirect URI (optional): http://localhost:3000/auth/callback

Purpose: Allow users of ALS Ticket Tracker to optionally connect their company Microsoft 365 account and send customer tracking emails, staff updates, and monthly reports from their own company mailbox. The existing tracker login remains available and unchanged. The application does not request application-wide Mail.Send privileges.

OIDC/OAuth scopes used in addition to Mail.Send: openid, profile, email, offline_access (for identity verification and refresh).

Deployment: Next.js frontend on Vercel, Django backend on Railway. The Django backend performs the code exchange and Microsoft Graph API requests; client secrets and OAuth tokens are not exposed in the browser.

Requested Actions from IT:
1. Register the application as a Web app in the ALS Microsoft Entra tenant (single tenant).
2. Assign delegated Microsoft Graph Mail.Send and grant required consent per organization policy.
3. Register the exact production redirect URI above; register localhost redirect only if approved for development.
4. Supply Tenant (directory) ID, Application (client) ID, and an approved confidential-client credential to the developer via a secure channel. The current implementation expects a client secret. Do not include it in email threads or frontend settings.
5. Confirm any requirements restricting application users / permitted staff accounts and Mail.Send for F3 licensing.

IMPORTANT: Confirm the Vercel domain above is still the actual production frontend address before submitting. The hostname was found in the user's October 23 backup and has not been confirmed via a live deployment check.
