"""Tests for the webhook rate limiter. Pure — injected clock, no DB, no sleep."""

from src.api.middleware.rate_limit import RateLimiter


def test_allows_up_to_the_limit():
    rl = RateLimiter(limit=3, window=60)
    assert [rl.check("a", now=t)[0] for t in (0, 1, 2)] == [True, True, True]


def test_blocks_over_the_limit_within_window():
    rl = RateLimiter(limit=3, window=60)
    for t in (0, 1, 2):
        rl.check("a", now=t)
    allowed, retry_after = rl.check("a", now=3)
    assert allowed is False
    assert retry_after > 0


def test_retry_after_counts_down_to_window_expiry():
    rl = RateLimiter(limit=1, window=60)
    rl.check("a", now=0)                 # first hit at t=0, expires at t=60
    allowed, retry_after = rl.check("a", now=10)
    assert allowed is False
    assert round(retry_after) == 50      # 60 - 10


def test_window_slides_and_frees_capacity():
    rl = RateLimiter(limit=2, window=60)
    rl.check("a", now=0)
    rl.check("a", now=1)
    assert rl.check("a", now=30)[0] is False   # still full
    # The t=0 hit ages out after t=60; capacity returns.
    assert rl.check("a", now=61)[0] is True


def test_blocked_attempt_does_not_extend_the_window():
    rl = RateLimiter(limit=1, window=60)
    rl.check("a", now=0)
    rl.check("a", now=5)                 # blocked — must NOT be recorded
    # Oldest hit is still t=0, so at t=61 the key is free again.
    assert rl.check("a", now=61)[0] is True


def test_keys_are_independent():
    rl = RateLimiter(limit=1, window=60)
    assert rl.check("a", now=0)[0] is True
    assert rl.check("b", now=0)[0] is True   # different citizen, own budget
    assert rl.check("a", now=1)[0] is False


def test_reset_clears_state():
    rl = RateLimiter(limit=1, window=60)
    rl.check("a", now=0)
    rl.reset("a")
    assert rl.check("a", now=1)[0] is True


def test_sweep_drops_fully_expired_keys():
    rl = RateLimiter(limit=5, window=60)
    rl.check("a", now=0)
    rl.check("b", now=0)
    # By t=100 both 60s windows have fully expired.
    assert rl.sweep(now=100) == 2
    assert rl.check("a", now=100)[0] is True   # fresh capacity, no leak


def test_sweep_keeps_active_keys():
    rl = RateLimiter(limit=5, window=60)
    rl.check("a", now=0)     # expires at t=60
    rl.check("b", now=59)    # still inside its window at t=60
    assert rl.sweep(now=60) == 1               # only "a" is stale; "b" survives
