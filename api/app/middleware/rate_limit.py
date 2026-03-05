"""In-memory sliding-window rate limiter middleware.

Provides per-IP rate limiting using an in-memory token bucket.  This is
intentionally simple — no Redis dependency — and suitable for a
single-process deployment behind a reverse proxy (Nginx).

Two limits are enforced:
- **Global**: applied to all endpoints (generous, prevents abuse)
- **Auth**: tighter limit on ``/auth/login`` to slow brute-force attacks

Configuration is via ``app.config.settings``:
- ``rate_limit_rpm``: requests per minute per IP (default 120)
- ``rate_limit_auth_rpm``: auth requests per minute per IP (default 10)
"""

import logging
import time
from collections import defaultdict

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Token bucket (per-IP, sliding window)
# ---------------------------------------------------------------------------

# {ip: [(timestamp, ...), ...]}  — stores request timestamps within the window
_buckets: dict[str, list[float]] = defaultdict(list)
_WINDOW_SECONDS = 60.0

# Cleanup stale entries every N requests to avoid unbounded memory growth
_CLEANUP_INTERVAL = 500
_request_counter = 0


def _get_client_ip(request: Request) -> str:
    """Extract client IP, respecting X-Forwarded-For from Nginx."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _prune_window(bucket: list[float], now: float) -> list[float]:
    """Remove timestamps older than the sliding window."""
    cutoff = now - _WINDOW_SECONDS
    return [t for t in bucket if t > cutoff]


def _maybe_cleanup() -> None:
    """Periodically prune all buckets to prevent memory leaks."""
    global _request_counter
    _request_counter += 1
    if _request_counter % _CLEANUP_INTERVAL != 0:
        return
    now = time.monotonic()
    empty_keys = []
    for ip, bucket in _buckets.items():
        _buckets[ip] = _prune_window(bucket, now)
        if not _buckets[ip]:
            empty_keys.append(ip)
    for ip in empty_keys:
        del _buckets[ip]


class RateLimitMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that enforces per-IP rate limits."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Skip health checks and docs
        path = request.url.path
        if path in ("/health", "/", "/docs", "/openapi.json", "/redoc"):
            return await call_next(request)

        client_ip = _get_client_ip(request)
        now = time.monotonic()

        # Choose limit based on path
        is_auth = path.startswith("/auth/login")
        rpm_limit = settings.rate_limit_auth_rpm if is_auth else settings.rate_limit_rpm

        # Prune + check
        bucket_key = f"{client_ip}:auth" if is_auth else client_ip
        _buckets[bucket_key] = _prune_window(_buckets[bucket_key], now)

        if len(_buckets[bucket_key]) >= rpm_limit:
            logger.warning(
                "Rate limit exceeded for %s on %s (%d/%d rpm)",
                client_ip, path, len(_buckets[bucket_key]), rpm_limit,
            )
            retry_after = int(_WINDOW_SECONDS - (now - _buckets[bucket_key][0])) + 1
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please try again later."},
                headers={"Retry-After": str(retry_after)},
            )

        _buckets[bucket_key].append(now)
        _maybe_cleanup()

        return await call_next(request)
