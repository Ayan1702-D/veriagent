"""Simple process-local sliding-window rate limiting middleware."""

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response


class InMemoryRateLimitMiddleware(BaseHTTPMiddleware):
    """Limit requests per client IP within a sliding time window."""

    def __init__(self, app: object, limit: int, window_seconds: float) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._limit = limit
        self._window = window_seconds
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    async def dispatch(self, request: Request, call_next: Callable[[Request], object]) -> Response:
        """Allow the request or return the standard 429 error envelope."""
        client_ip = request.client.host if request.client is not None else "unknown"
        now = time.monotonic()
        with self._lock:
            history = self._requests[client_ip]
            cutoff = now - self._window
            while history and history[0] <= cutoff:
                history.popleft()
            if len(history) >= self._limit:
                retry_after = max(1, int(self._window - (now - history[0])))
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": {
                            "code": "rate_limit_exceeded",
                            "message": "Too many requests",
                        }
                    },
                    headers={"Retry-After": str(retry_after)},
                )
            history.append(now)

        response = await call_next(request)  # type: ignore[misc]
        return response  # type: ignore[no-any-return]
