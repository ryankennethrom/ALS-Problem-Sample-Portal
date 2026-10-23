# Outlook Webmail as the browser's mailto handler

This version of ALS Ticket Tracker uses ordinary `mailto:` links for
staff-generated emails. To, Cc, Subject, and Body are included in the link when
the encoded link is short enough. The application **does not** send the email.

## Configure Outlook Webmail

1. Open https://outlook.office.com/mail/ and sign in with your approved ALS account.
2. In Chrome, open `chrome://settings/handlers` or, in Edge, open
   `edge://settings/content/handlers`. Allow sites to request permission to
   handle protocols, including email links.
3. If Outlook offers to handle email links (in its page or in the address bar),
   allow it. If the option is not offered, you might need ALS IT to set a
   browser policy or provide an approved Outlook webmail handler.
4. Test with an email containing To, Cc, Subject and Body. Confirm that the
   draft opens in the intended ALS Outlook Webmail account and that Cc appears.
5. If a desktop app or the wrong account opens, correct the browser/OS handler
   or ask IT for help before sending customer emails.

For managed Microsoft Edge installations, IT can consult Microsoft's policy:
https://learn.microsoft.com/en-us/deployedge/microsoft-edge-browser-policies/registeredprotocolhandlers

Note: Mailto registration is a browser/OS setting, **not** something the
tracker can force for a user. Some browser/Outlook configurations may still
ignore fields. The tracker always provides a copyable complete draft.

## Very long emails

The tracker uses a conservative limit of **1500 encoded characters** for the
entire mailto link, including recipients, Cc, Subject, Body and URL encoding.
If the link is longer, the app pauses and shows the complete draft for copying
before launching a shortened link; it never silently discards content from
that preview. This limit is a precaution, not a published universal Microsoft
email or URL limit.

## Sending and history

The app only prepares a draft. Staff must verify To, Cc, Subject and Body,
send it themselves, and confirm "I sent the email" in the tracker afterward.
The backend and database were not changed for this update.
