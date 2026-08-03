"""Request logging and security middleware helpers."""

from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-ms"] = f"{(time.perf_counter() - started) * 1000:.1f}"
        return response


class LoginRateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory rate limit for /auth/login."""

    def __init__(self, app, limit_per_minute: int = 10) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self.limit = limit_per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path.endswith("/auth/login") and request.method == "POST":
            ip = request.client.host if request.client else "unknown"
            now = time.time()
            bucket = self._hits[ip]
            while bucket and now - bucket[0] > 60:
                bucket.popleft()
            if len(bucket) >= self.limit:
                return Response(
                    content='{"error":{"code":"RATE_LIMITED","message":"Too many login attempts"}}',
                    status_code=429,
                    media_type="application/json",
                )
            bucket.append(now)
        return await call_next(request)
