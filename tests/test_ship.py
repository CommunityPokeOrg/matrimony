"""Tests for the drifting ship percentage and the per-channel activity window."""

import itertools
import time
from unittest.mock import AsyncMock, patch

from test_dispatch import (
    BOT_USER_ID,
    ctx_for,
    make_bot,
    message,
    run,
    user,
)

from matrimony.cogs import matr as matr_mod
from matrimony.ship import (
    SHIP_ACTIVITY_NUDGE,
    SHIP_BUCKET_SECONDS,
    ChannelActivity,
    ship_score,
)

NOW = 1_700_000_000.0


# ---------------------------------------------------------------------------
# ship_score
# ---------------------------------------------------------------------------


def test_deterministic_at_fixed_time() -> None:
    """Same pair, same bucket, same count -> same score, every time."""
    a = ship_score(111, 222, now=NOW, message_count=3)
    b = ship_score(111, 222, now=NOW, message_count=3)
    assert a == b


def test_pair_order_is_symmetric() -> None:
    assert ship_score(1, 2, now=NOW, message_count=0) == ship_score(
        2, 1, now=NOW, message_count=0
    )


def test_constant_within_a_bucket() -> None:
    """Every instant inside the same 5-minute bucket yields the same score."""
    start = NOW - (NOW % SHIP_BUCKET_SECONDS)
    scores = {
        ship_score(5, 6, now=start + off, message_count=4)
        for off in (0.0, 1.0, 150.0, SHIP_BUCKET_SECONDS - 1.0)
    }
    assert len(scores) == 1


def test_smooth_drift_across_buckets() -> None:
    """Consecutive buckets differ by at most a point, and the score does
    actually move over time."""
    scores = [
        ship_score(42, 99, now=NOW + i * SHIP_BUCKET_SECONDS, message_count=0)
        for i in range(200)
    ]
    for prev, cur in itertools.pairwise(scores):
        assert abs(cur - prev) <= 1
    assert len(set(scores)) > 1


def test_message_count_nudges_the_score() -> None:
    quiet = ship_score(7, 8, now=NOW, message_count=0)
    busy = ship_score(7, 8, now=NOW, message_count=50)
    assert quiet != busy
    assert abs(busy - quiet) <= SHIP_ACTIVITY_NUDGE


def test_count_nudge_is_bounded() -> None:
    """Thousands of messages nudge no harder than a few dozen."""
    few = ship_score(7, 8, now=NOW, message_count=SHIP_ACTIVITY_NUDGE)
    many = ship_score(7, 8, now=NOW, message_count=1_000_000)
    assert few == many


def test_score_always_clamped() -> None:
    """No pair/bucket/count combination escapes [0, 100] — and the clamp
    actually engages at both ends for extreme pairs."""
    seen = set()
    for a in range(1, 400):
        for b in range(a + 1, a + 25):
            for count in (0, 1_000_000):
                for offset in (0, 33_000_000, 66_000_000):
                    s = ship_score(a, b, now=NOW + offset, message_count=count)
                    assert 0 <= s <= 100
                    seen.add(s)
    assert 0 in seen
    assert 100 in seen


# ---------------------------------------------------------------------------
# ChannelActivity
# ---------------------------------------------------------------------------


def test_activity_counts_recent_messages() -> None:
    act = ChannelActivity(window_seconds=600.0)
    act.note(1, 0.0)
    act.note(1, 30.0)
    act.note(2, 0.0)  # different channel: isolated
    assert act.count(1, 60.0) == 2
    assert act.count(2, 60.0) == 1
    assert act.count(3, 60.0) == 0


def test_activity_prunes_old_messages() -> None:
    act = ChannelActivity(window_seconds=600.0)
    act.note(1, 0.0)
    act.note(1, 30.0)
    act.note(1, 100.0)
    assert act.count(1, 599.0) == 3
    assert act.count(1, 630.0) == 1  # t=0 and t=30 aged out
    assert act.count(1, 701.0) == 0  # t=100 aged out too


def test_activity_drops_empty_channels() -> None:
    act = ChannelActivity(window_seconds=600.0)
    act.note(1, 0.0)
    assert act.count(1, 1e9) == 0
    assert 1 not in act._channels


def test_activity_is_bounded_per_channel() -> None:
    act = ChannelActivity(window_seconds=600.0, max_per_channel=16)
    for i in range(100):
        act.note(1, float(i))
    assert act.count(1, 100.0) == 16


# ---------------------------------------------------------------------------
# Wiring: on_message feeds the window, ship consumes it
# ---------------------------------------------------------------------------


def test_on_message_records_human_and_bot_authors() -> None:
    """Bot-authored chatter counts toward channel busyness too."""
    bot = make_bot()
    bot.process_commands = AsyncMock()  # type: ignore[method-assign]
    run(bot.on_message(message(user(1))))
    run(bot.on_message(message(user(2, bot=True))))
    assert bot.channel_activity.count(1, time.time()) == 2


def test_on_message_counts_own_replies_but_skips_dispatch() -> None:
    """Our own messages still count as channel activity (they're chatter
    too) even though they're never dispatched as commands."""
    bot = make_bot()
    bot.process_commands = AsyncMock()  # type: ignore[method-assign]
    run(bot.on_message(message(user(BOT_USER_ID, bot=True))))
    bot.process_commands.assert_not_awaited()
    assert bot.channel_activity.count(1, time.time()) == 1


def test_ship_command_replies_with_percentage() -> None:
    bot = make_bot()
    ctx = ctx_for(bot, user(1))
    run(matr_mod.matr_ship.callback(ctx, user(2), user(3)))
    text = ctx.reply.call_args.kwargs["embed"].description
    assert text.startswith("<@2> x <@3>: **")
    assert "%** :heart:" in text


def test_ship_command_uses_channel_activity() -> None:
    """The command feeds the channel's rolling message count into the
    score (verified by pinning the clock)."""
    bot = make_bot()
    ctx = ctx_for(bot, user(1))
    t = time.time()
    for _ in range(50):
        bot.channel_activity.note(7, t)  # ctx channel id is 7
    with patch.object(matr_mod.time, "time", lambda: t):
        run(matr_mod.matr_ship.callback(ctx, user(2), user(3)))
    text = ctx.reply.call_args.kwargs["embed"].description
    shown = int(text.split("**")[1].rstrip("%"))
    assert shown == ship_score(2, 3, now=t, message_count=50)
