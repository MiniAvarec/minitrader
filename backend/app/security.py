"""Cross-cutting security primitives: rate limiter + ASGI middlewares."""
from __future__ import annotations

import hmac

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp


# Single shared limiter — endpoints import it to apply per-route rules.
# Key is the client IP (taken from X-Forwarded-For when ProxyHeaders is on).
limiter = Limiter(key_func=get_remote_address)


# 1 MiB. The biggest legitimate body is a strategy YAML (capped at 16 KiB by
# the column), so 1 MiB is comfortable headroom while protecting workers from
# accidental huge uploads.
MAX_BODY_BYTES = 1 * 1024 * 1024


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests whose Content-Length exceeds MAX_BODY_BYTES."""

    async def dispatch(self, request: Request, call_next):
        cl = request.headers.get("content-length")
        if cl is not None:
            try:
                if int(cl) > MAX_BODY_BYTES:
                    return JSONResponse(
                        {"detail": "request body too large"},
                        status_code=413,
                    )
            except ValueError:
                # Malformed header — let the downstream stack reject it.
                pass
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add baseline hardening headers to every response."""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        h = response.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "same-origin")
        # The Vite dev server inlines styles + scripts and uses ws:// for HMR,
        # so a strict CSP would break local dev. The reverse-proxy edge in
        # production should layer a CSP on top of this for HTML responses;
        # this header keeps the simple, broadly-safe defaults inside the app.
        h.setdefault("X-Permitted-Cross-Domain-Policies", "none")
        # HSTS is only meaningful over TLS — set unconditionally because the
        # edge proxy terminates HTTPS; if the client never reaches us over TLS
        # the header is harmless.
        h.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
        return response


def secrets_equal(a: str | None, b: str | None) -> bool:
    """Constant-time compare for shared secrets (avoids timing leaks)."""
    if not a or not b:
        return False
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


__all__ = [
    "limiter",
    "BodySizeLimitMiddleware",
    "SecurityHeadersMiddleware",
    "secrets_equal",
]
