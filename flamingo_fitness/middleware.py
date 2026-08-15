"""Per-request ``Secure`` cookie flag middleware.

``DEBUG=False`` is the production posture this app runs with, and it forces
``CSRF_COOKIE_SECURE`` / ``SESSION_COOKIE_SECURE`` to ``True``. That is correct
behind the HTTPS Cloudflare Tunnel but silently breaks the plain-HTTP LAN
install: browsers refuse to send ``Secure`` cookies over ``http://``, so the
login POST is denied by the CSRF check (403) and the dashboard never loads.

Django's ``HttpResponse.set_cookie`` only emits the ``Secure`` flag when the
setting is truthy - there is no request-aware mode (Django 5.x/6.x) - so we
rewrite the flags after the response is built to match the request scheme:

  * HTTPS request  -> ``Secure`` cookies (tunnel keeps working)
  * HTTP request   -> non-Secure cookies (LAN access keeps working)
"""

from django.conf import settings


class SchemeAwareSecureCookiesMiddleware:
    """Apply the Secure flag to the session + CSRF cookies per-request."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.cookie_names = (
            settings.SESSION_COOKIE_NAME,
            settings.CSRF_COOKIE_NAME,
        )

    def __call__(self, request):
        response = self.get_response(request)
        secure = request.is_secure()
        for name in self.cookie_names:
            if name in response.cookies:
                # SimpleCookie omits the flag for any falsy value.
                response.cookies[name]["secure"] = secure
        return response