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
        secure = bool(
            request.is_secure()
            or request.scheme == "https"
            or request.META.get("wsgi.url_scheme") == "https"
            or request.META.get("HTTP_X_FORWARDED_PROTO") == "https"
        )
        for name in self.cookie_names:
            if name in response.cookies:
                # SimpleCookie omits the flag for any falsy value.
                response.cookies[name]["secure"] = secure
        return response


class SecurityHeadersMiddleware:
    """Production security hardening headers (CSP, Referrer-Policy, Permissions-Policy)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        # Content-Security-Policy (Allow self, CDNs for icons/fonts/charts, and avatar APIs)
        csp = (
            "default-src 'self' https: data: blob: 'unsafe-inline' 'unsafe-eval'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.tailwindcss.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
            "style-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://cdnjs.cloudflare.com https://fonts.googleapis.com; "
            "font-src 'self' data: https://cdnjs.cloudflare.com https://fonts.gstatic.com; "
            "img-src 'self' data: blob: https: http:; "
            "connect-src 'self' https: http: https://fit.randalls.cc; "
            "frame-ancestors 'self'; "
            "base-uri 'self';"
        )
        response.headers.setdefault("Content-Security-Policy", csp)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        return response