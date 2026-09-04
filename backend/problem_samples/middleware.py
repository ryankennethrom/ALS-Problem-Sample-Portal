class PurgeExpiredAcknowledgementCredentialsMiddleware:
    """Legacy pass-through middleware. Tracking links are no longer purged."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)
