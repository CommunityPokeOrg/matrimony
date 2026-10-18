"""Drifting ship-percentage scoring and per-channel message activity.

``matr ship`` used to be a fixed hash of the two user ids, so it never
changed. The score is now a pure function of three inputs:

- the sorted pair of user ids (stable anchor, per-pair drift shape),
- a slowly changing time component (a per-pair sinusoid over ~24h, so the
  value drifts smoothly between 5-minute buckets instead of jumping),
- the rolling count of messages in the channel over the last 10 minutes
  (busier channels nudge the value a little, direction depends on the pair).

Everything is deterministic: the same inputs in the same time bucket always
give the same answer, and the function is pure so tests can inject the
clock and the message count. The result is clamped to 0-100.
"""

from __future__ import annotations

import hashlib
import math
from collections import deque

SHIP_BUCKET_SECONDS = 300.0
"""Length of a time bucket. The score is constant inside one bucket."""

SHIP_DRIFT_PERIOD_SECONDS = 24.0 * 3600.0
"""Period of the sinusoidal drift. Slower = gentler wandering."""

SHIP_ACTIVITY_WINDOW_SECONDS = 600.0
"""How long a message stays in a channel's rolling activity window."""

SHIP_ACTIVITY_NUDGE = 10
"""Maximum absolute nudge applied by channel activity."""

SHIP_ACTIVITY_MAX_PER_CHANNEL = 256
"""Bound on stored timestamps per channel (oldest are dropped)."""

_TAU = 2.0 * math.pi


def ship_score(
    user_a: int, user_b: int, *, now: float, message_count: int
) -> int:
    """Deterministic, slowly drifting ship percentage in ``[0, 100]``.

    ``now`` is seconds since the epoch (any monotonic epoch works as long
    as callers are consistent); ``message_count`` is the number of recent
    messages in the channel. Same pair + same bucket + same count always
    yields the same score; adjacent buckets differ by at most a point or
    two so the percentage wanders rather than jumps.
    """
    lo, hi = sorted((int(user_a), int(user_b)))
    digest = hashlib.sha256(f"matrimony-ship:{lo}:{hi}".encode()).digest()
    base = 15 + digest[0] * 70 // 256  # stable anchor in [15, 84]
    amplitude = 5 + digest[1] * 15 // 256  # drift amplitude in [5, 19]
    phase = (digest[2] | digest[3] << 8) / 65536.0 * _TAU
    bucket = int(now // SHIP_BUCKET_SECONDS)
    drift = amplitude * math.sin(
        phase + _TAU * bucket * SHIP_BUCKET_SECONDS / SHIP_DRIFT_PERIOD_SECONDS
    )
    direction = -1.0 if digest[4] & 1 else 1.0
    nudge = direction * min(max(int(message_count), 0), SHIP_ACTIVITY_NUDGE)
    return max(0, min(100, round(base + drift + nudge)))


class ChannelActivity:
    """In-memory rolling window of per-channel message timestamps.

    One small deque per channel, pruned to the last ``window_seconds``
    (and hard-bounded per channel) — recording and counting are both a
    handful of pointer operations, so it stays cheap on busy channels.
    """

    def __init__(
        self,
        window_seconds: float = SHIP_ACTIVITY_WINDOW_SECONDS,
        max_per_channel: int = SHIP_ACTIVITY_MAX_PER_CHANNEL,
    ) -> None:
        self._window = window_seconds
        self._channels: dict[int, deque[float]] = {}
        self._max = max_per_channel

    def _prune(self, dq: deque[float], now: float) -> None:
        cutoff = now - self._window
        while dq and dq[0] <= cutoff:
            dq.popleft()

    def note(self, channel_id: int, when: float) -> None:
        """Record that a message was sent in ``channel_id`` at ``when``."""
        dq = self._channels.get(channel_id)
        if dq is None:
            dq = self._channels[channel_id] = deque(maxlen=self._max)
        dq.append(when)
        self._prune(dq, when)

    def count(self, channel_id: int, now: float) -> int:
        """Messages seen in ``channel_id`` within the window ending ``now``."""
        dq = self._channels.get(channel_id)
        if not dq:
            return 0
        self._prune(dq, now)
        if not dq:
            # Empty channels are dropped so the map can't grow forever.
            del self._channels[channel_id]
            return 0
        return len(dq)
