from .automatic_disposal import transition_due_automatic_disposals


class AutomaticDisposalTransitionMiddleware:
    """Apply due automatic-disposal workflow transitions before each request.

    This keeps the persisted Status authoritative without requiring a separate
    worker process. A due row is transitioned on the next application request,
    before API views serialize or act on it.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        transition_due_automatic_disposals()
        return self.get_response(request)


class PurgeExpiredAcknowledgementCredentialsMiddleware:
    """Legacy pass-through middleware. Tracking links are no longer purged."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)
