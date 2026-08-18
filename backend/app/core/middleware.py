from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("mwb_audit.http")


class SecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, login_limit: int = 10, window_seconds: int = 300):
        super().__init__(app)
        self.login_limit = login_limit
        self.window_seconds = window_seconds
        self.attempts: dict[str, deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))[:80]
        client = request.client.host if request.client else "unknown"
        is_login = request.url.path == "/api/auth/login" and request.method == "POST"
        if is_login:
            now = time.monotonic()
            with self.lock:
                attempts = self.attempts[client]
                while attempts and attempts[0] < now - self.window_seconds:
                    attempts.popleft()
                if len(attempts) >= self.login_limit:
                    return JSONResponse(
                        status_code=429,
                        content={"detail": "Too many login attempts. Try again later."},
                        headers={"Retry-After": str(self.window_seconds)},
                    )
        started = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "Unhandled request error request_id=%s path=%s", request_id, request.url.path
            )
            return JSONResponse(
                status_code=500, content={"detail": "An unexpected server error occurred"}
            )
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        )
        if is_login:
            with self.lock:
                if response.status_code == 401:
                    self.attempts[client].append(time.monotonic())
                elif response.status_code < 400:
                    self.attempts.pop(client, None)
        logger.info(
            "%s %s status=%s duration_ms=%d request_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            (time.monotonic() - started) * 1000,
            request_id,
        )
        return response
