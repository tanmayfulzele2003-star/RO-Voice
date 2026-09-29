"""Minimal in-memory sliding-window rate limiter.

Single-process, in-memory by design: this app runs as one FastAPI process,
so there's no need for a shared store like Redis. If the app is ever scaled
to multiple processes/instances, this stops being effective and would need a
shared backend.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

_history: dict[str, deque[float]] = defaultdict(deque)


def check_rate_limit(key: str, max_requests: int, window_seconds: float) -> bool:
    """Returns True if another request under `key` is allowed right now."""
    now = time.monotonic()
    history = _history[key]
    while history and now - history[0] > window_seconds:
        history.popleft()
    if len(history) >= max_requests:
        return False
    history.append(now)
    return True
