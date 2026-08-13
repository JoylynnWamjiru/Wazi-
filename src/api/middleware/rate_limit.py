"""In-memory sliding-window rate limiting for the WhatsApp webhook.

Protects the pipeline and the DeepSeek budget from a single number (or bot)
flooding requests. Keyed by the **hashed** wa_id, so it throttles per citizen
rather than per Africa's Talking IP (all citizens share AT's small IP set, so
per-IP limiting there would throttle everyone at once).

Sliding window, not a fixed bucket: a burst that straddles a window boundary
still counts. State is a per-key deque of hit timestamps, pruned on each check.
In-process (no Redis) — fine for the single-worker MVP; swap for a shared store
if we scale to multiple workers.

`now` is injectable so the logic is unit-testable without sleeping.
"""

import os
import threading
import time
from collections import defaultdict, deque

# Per citizen (hashed wa_id): at most LIMIT messages per WINDOW seconds.
LIMIT = int(os.getenv("WEBHOOK_RATE_LIMIT", "10"))
WINDOW_SECONDS = int(os.getenv("WEBHOOK_RATE_WINDOW_SECONDS", "60"))

# Drop fully-expired keys every this many allowed checks, to bound memory.
_SWEEP_EVERY = 1000


class RateLimiter:
    """Sliding-window limiter: ``limit`` events per ``window`` seconds per key."""

    def __init__(self, limit: int = LIMIT, window: int = WINDOW_SECONDS) -> None:
        self.limit = limit
        self.window = window
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._checks_since_sweep = 0

    def check(self, key: str, now: float | None = None) -> tuple[bool, float]:
        """Record an attempt for ``key``. Return ``(allowed, retry_after)``.

        ``retry_after`` is seconds until the oldest hit in the window expires
        (0.0 when allowed). The attempt is only recorded when allowed, so a
        blocked caller doesn't push its own retry window further out.
        """
        now = time.monotonic() if now is None else now
        cutoff = now - self.window

        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= cutoff:
                hits.popleft()

            if len(hits) >= self.limit:
                retry_after = hits[0] + self.window - now
                return False, max(0.0, retry_after)

            hits.append(now)
            # Periodically sweep fully-expired keys so the dict doesn't grow
            # one entry per unique citizen ever seen.
            self._checks_since_sweep += 1
            if self._checks_since_sweep >= _SWEEP_EVERY:
                self._sweep_locked(now)
                self._checks_since_sweep = 0
            return True, 0.0

    def reset(self, key: str | None = None) -> None:
        """Clear state for one key, or all keys. Testing / admin use."""
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)

    def sweep(self, now: float | None = None) -> int:
        """Drop keys whose entire window has expired. Returns count removed.

        Bounds memory: without this, one deque per unique citizen ever seen
        would linger forever. Runs automatically every ``_SWEEP_EVERY`` allowed
        checks; also callable manually (admin / tests).
        """
        now = time.monotonic() if now is None else now
        with self._lock:
            return self._sweep_locked(now)

    def _sweep_locked(self, now: float) -> int:
        """Sweep implementation; the caller must already hold ``self._lock``."""
        cutoff = now - self.window
        stale = [k for k, d in self._hits.items() if not d or d[-1] <= cutoff]
        for k in stale:
            del self._hits[k]
        return len(stale)


# Module-level singletons used by the webhook.
webhook_limiter = RateLimiter()

# At most one "you're rate limited" reply per window per citizen, so a flood of
# blocked messages can't amplify into a flood of outbound WhatsApp sends.
block_notice_limiter = RateLimiter(limit=1, window=WINDOW_SECONDS)
