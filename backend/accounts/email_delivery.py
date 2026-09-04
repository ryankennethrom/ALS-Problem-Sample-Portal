import json
from urllib import error, request

from django.conf import settings


class EmailDeliveryError(RuntimeError):
    """Raised when a transactional email cannot be delivered."""


def _brevo_config():
    api_key = str(getattr(settings, 'BREVO_API_KEY', '') or '').strip()
    sender_email = str(getattr(settings, 'BREVO_SENDER_EMAIL', '') or '').strip()
    sender_name = str(getattr(settings, 'BREVO_SENDER_NAME', '') or '').strip()
    api_url = str(
        getattr(settings, 'BREVO_API_URL', 'https://api.brevo.com/v3/smtp/email')
        or 'https://api.brevo.com/v3/smtp/email'
    ).strip()

    missing = []
    if not api_key:
        missing.append('BREVO_API_KEY')
    if not sender_email:
        missing.append('BREVO_SENDER_EMAIL')
    if missing:
        raise EmailDeliveryError(
            'Brevo email delivery is not configured. Missing: ' + ', '.join(missing) + '.'
        )

    return api_key, sender_email, sender_name, api_url


def send_brevo_email(*, to_email, subject, text_content, html_content=None):
    """Send one transactional email through Brevo's HTTPS API."""
    api_key, sender_email, sender_name, api_url = _brevo_config()

    sender = {'email': sender_email}
    if sender_name:
        sender['name'] = sender_name

    payload = {
        'sender': sender,
        'to': [{'email': str(to_email).strip()}],
        'subject': subject,
    }
    # Brevo accepts one inline body type per request. Prefer HTML for the
    # sign-in button, otherwise fall back to plain text.
    if html_content:
        payload['htmlContent'] = html_content
    else:
        payload['textContent'] = text_content

    body = json.dumps(payload).encode('utf-8')
    req = request.Request(
        api_url,
        data=body,
        method='POST',
        headers={
            'accept': 'application/json',
            'api-key': api_key,
            'content-type': 'application/json',
        },
    )

    try:
        with request.urlopen(req, timeout=15) as response:
            response_body = response.read().decode('utf-8', errors='replace')
            if response.status < 200 or response.status >= 300:
                raise EmailDeliveryError(
                    f'Brevo returned HTTP {response.status}: {response_body[:500]}'
                )
            try:
                return json.loads(response_body) if response_body else {}
            except json.JSONDecodeError:
                return {'raw_response': response_body}
    except error.HTTPError as exc:
        response_body = exc.read().decode('utf-8', errors='replace')
        raise EmailDeliveryError(
            f'Brevo returned HTTP {exc.code}: {response_body[:500]}'
        ) from exc
    except error.URLError as exc:
        raise EmailDeliveryError(f'Could not reach Brevo: {exc.reason}') from exc
    except TimeoutError as exc:
        raise EmailDeliveryError('Brevo request timed out.') from exc
