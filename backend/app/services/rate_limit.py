from __future__ import annotations

import time
from collections import deque

# In-process sliding-window counters, keyed by whatever the caller is limiting on.
#
# Deliberately in memory rather than in Mongo: this runs on every request, and a
# database round trip per request would cost more than the endpoints it protects.
# The trade is that the window is per-process - it empties on restart, and two API
# replicas each get their own allowance. With one container that is exact; with N
# containers the effective limit is N times the configured number. If this service
# is ever scaled out and the ceilings need to be precise, this is the one module to
# move behind a shared store.
_WINDOWS: dict[str, deque[float]] = {}

# Keys are unbounded in principle - one per IP, one per user - so idle buckets are
# swept periodically. Without this, a caller cycling through addresses would grow
# the dictionary forever.
_SWEEP_EVERY_SECONDS = 300.0
_MAX_IDLE_SECONDS = 3_600.0
_last_sweep = 0.0


class RateLimitError(Exception):
    """Raised when a caller exceeds a window.

    Handled centrally by an exception handler in main.py, so no router has to
    catch it and no new endpoint can forget to.
    """

    status_code = 429

    def __init__(self, message: str, retry_after: int) -> None:
        super().__init__(message)
        self.message = message
        self.retry_after = retry_after


def _sweep(now: float) -> None:
    global _last_sweep
    if now - _last_sweep < _SWEEP_EVERY_SECONDS:
        return
    _last_sweep = now
    stale = [key for key, hits in _WINDOWS.items() if not hits or now - hits[-1] > _MAX_IDLE_SECONDS]
    for key in stale:
        del _WINDOWS[key]


def check(*, key: str, limit: int, window_seconds: int, message: str) -> None:
    """Record one hit against `key`, or raise if the window is already full.

    The window slides: timestamps older than `window_seconds` are dropped on each
    call, so a caller who waits out their oldest hit gets an allowance back
    gradually rather than all at once on a fixed boundary.
    """
    now = time.monotonic()
    _sweep(now)

    hits = _WINDOWS.setdefault(key, deque())
    cutoff = now - window_seconds
    while hits and hits[0] <= cutoff:
        hits.popleft()

    if len(hits) >= limit:
        # The oldest hit is what has to age out before there is room again.
        retry_after = max(int(hits[0] + window_seconds - now) + 1, 1)
        raise RateLimitError(message, retry_after=retry_after)

    hits.append(now)


def reset() -> None:
    """Clear every window. For tests and local experimentation only."""
    _WINDOWS.clear()
