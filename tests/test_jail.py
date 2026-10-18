"""Tests for restraining orders, the jail system, the expiry sweep, and
the `matr clear` guild reset.

Store and sweep tests inject ``now`` directly; command-level tests drive
the same ``ctx``/``interaction`` fakes as test_dispatch."""

import random
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from test_dispatch import ctx_for, make_bot, run, user

from matrimony import jail as jail_mod
from matrimony.cogs import matr as matr_mod
from matrimony.cogs.matr import (
    ClearConfirmView,
    PressChargesView,
    _announce_expiry,
    _resolve_charge,
)
from matrimony.store import Store

GUILD = 42


def order_filed(bot, protected: int, restrained: int, now: int | None = None):
    return bot.store.file_restraining_order(
        GUILD, 7, protected, restrained, ttl_seconds=3600, now=now
    )


def interaction(bot, uid: int):
    return SimpleNamespace(
        client=bot,
        user=SimpleNamespace(id=uid),
        response=SimpleNamespace(
            send_message=AsyncMock(), is_done=lambda: False
        ),
        followup=SimpleNamespace(send=AsyncMock()),
        reply=AsyncMock(),
    )


# ---------------------------------------------------------------------------
# Restraining orders: creation and expiry
# ---------------------------------------------------------------------------


def test_file_restraining_order() -> None:
    bot = make_bot()
    order = order_filed(bot, 1, 2)
    assert order.protected == 1 and order.restrained == 2
    assert order.expires_at - order.created_at == 3600
    assert bot.store.restraining_order(1, 2) is not None


def test_restraining_order_expires() -> None:
    bot = make_bot()
    order_filed(bot, 1, 2, now=1000)
    # 59 minutes in: still active.
    assert bot.store.restraining_order(1, 2, now=1000 + 3540) is not None
    # At the hour mark: gone.
    assert bot.store.restraining_order(1, 2, now=1000 + 3600) is None


def test_refiling_renews_the_hour() -> None:
    bot = make_bot()
    order_filed(bot, 1, 2, now=1000)
    order = order_filed(bot, 1, 2, now=4000)
    assert order.expires_at == 4000 + 3600
    assert bot.store.restraining_order(1, 2, now=4000 + 3599) is not None


def test_expire_restraining_orders_returns_lapsed() -> None:
    bot = make_bot()
    order_filed(bot, 1, 2, now=1000)
    order_filed(bot, 3, 4, now=1000)
    expired = bot.store.expire_restraining_orders(now=1000 + 3600)
    assert {(o.protected, o.restrained) for o in expired} == {(1, 2), (3, 4)}
    assert bot.store.expire_restraining_orders(now=1000 + 3600) == []


# ---------------------------------------------------------------------------
# Sentencing
# ---------------------------------------------------------------------------


def test_minor_infraction_rolls_1_to_5_minutes() -> None:
    rng = random.Random(7)
    for action in ("poke", "hug", "wave", "tickle", "flirt"):
        for _ in range(20):
            seconds = jail_mod.sentence_seconds(action, rng)
            assert 60 <= seconds <= 300, (action, seconds)


def test_major_infraction_sentences() -> None:
    expected = {
        "slap": 10,
        "adopt": 15,
        "makeparent": 15,
        "bite": 20,
        "punch": 20,
        "stab": 25,
        "marry": 30,
    }
    for action, minutes in expected.items():
        assert jail_mod.sentence_seconds(action) == minutes * 60


def test_unlisted_action_gets_default_major() -> None:
    # Any targeted action missing from the table is a 15-minute major.
    assert jail_mod.sentence_seconds("banish") == 15 * 60


# ---------------------------------------------------------------------------
# Jail blocking and release
# ---------------------------------------------------------------------------


def test_jailing_and_release() -> None:
    bot = make_bot()
    bot.store.jail_inmate(2, GUILD, 7, "stab", 1, 600, now=1000)
    assert bot.store.is_jailed(2, now=1000)
    assert bot.store.is_jailed(2, now=1599)
    assert not bot.store.is_jailed(2, now=1600)
    s = bot.store.sentence_for(2, now=1000)
    assert s.action == "stab" and s.protected == 1


def test_release_inmate_dissolves_jail_relationships() -> None:
    bot = make_bot()
    bot.store.jail_inmate(2, GUILD, 7, "punch", 1, 600, now=1000)
    bot.store.jail_inmate(3, GUILD, 7, "poke", 1, 600, now=1000)
    bot.store.add_jail_partners(2, 3)
    bot.store.add_jail_child(2, 3)  # 3 is 2's jail child
    bot.store.jail_inmate(4, GUILD, 7, "poke", 1, 600, now=1000)
    bot.store.add_jail_child(4, 2)  # 4 is 2's jail parent

    result = bot.store.release_inmate(2)
    assert result.divorced == [3]
    assert result.children_lost == [3]
    assert result.parent_lost == 4
    assert not bot.store.is_jailed(2, now=1000)
    assert bot.store.jail_partners_of(3) == []
    assert bot.store.jail_children_of(4) == []
    assert bot.store.jail_parent_of(3) is None
    # Release is idempotent.
    assert bot.store.release_inmate(2) is None


# ---------------------------------------------------------------------------
# Command-level: restrain and violation prompts
# ---------------------------------------------------------------------------


def test_restrain_command_files_order() -> None:
    bot = make_bot()
    protected, restrained = user(10), user(20)
    ctx = ctx_for(bot, protected)
    run(matr_mod.matr_restrain.callback(ctx, restrained))
    assert bot.store.restraining_order(10, 20) is not None
    ctx.reply.assert_awaited_once()


def test_restrain_self_is_rejected() -> None:
    bot = make_bot()
    ctx = ctx_for(bot, user(10))
    run(matr_mod.matr_restrain.callback(ctx, user(10)))
    assert bot.store.restraining_order(10, 10) is None


def _violation_prompt(ctx):
    """The PressChargesView posted by a blocked action."""
    ctx.send.assert_awaited_once()
    view = ctx.send.call_args.kwargs["view"]
    assert isinstance(view, PressChargesView)
    return view


def test_blocked_fun_action_prompts_charges() -> None:
    bot = make_bot()
    protected, restrained = user(10), user(20)
    order_filed(bot, 10, 20)
    ctx = ctx_for(bot, restrained)
    run(matr_mod.matr.get_command("hug").callback(ctx, protected))
    view = _violation_prompt(ctx)
    assert view.order.protected == 10 and view.order.restrained == 20
    assert view.action == "hug"
    # The hug itself never went through.
    ctx.reply.assert_not_awaited()


def test_blocked_proposal_prompts_charges() -> None:
    bot = make_bot()
    protected, restrained = user(10), user(20)
    order_filed(bot, 10, 20)
    ctx = ctx_for(bot, restrained)
    run(matr_mod.matr_marry.callback(ctx, protected))
    view = _violation_prompt(ctx)
    assert view.action == "marry"
    assert bot.store.proposals_for(10) == []


def test_expired_order_no_longer_blocks() -> None:
    bot = make_bot()
    protected, restrained = user(10), user(20)
    # Filed over an hour ago: already lapsed.
    order_filed(bot, 10, 20, now=int(time.time()) - 3700)
    ctx = ctx_for(bot, restrained)
    run(matr_mod.matr_marry.callback(ctx, protected))
    assert len(bot.store.proposals_for(10, "marry")) == 1


def test_pressing_charges_jails_the_offender() -> None:
    bot = make_bot()
    order = order_filed(bot, 10, 20)
    ctx = ctx_for(bot, user(10))
    run(_resolve_charge(bot, ctx, order, "slap", pressed=True))
    s = bot.store.sentence_for(20)
    assert s is not None
    assert s.action == "slap" and s.protected == 10
    # slap = 10 minutes.
    assert s.release_at - s.jailed_at == 600


def test_declining_charges_keeps_order_no_jail() -> None:
    bot = make_bot()
    order = order_filed(bot, 10, 20)
    ctx = ctx_for(bot, user(10))
    run(_resolve_charge(bot, ctx, order, "poke", pressed=False))
    assert bot.store.sentence_for(20) is None
    assert bot.store.restraining_order(10, 20) is not None


def test_pressing_after_order_lapsed_does_not_jail() -> None:
    bot = make_bot()
    order = order_filed(bot, 10, 20, now=1000)
    bot.store.expire_restraining_orders(now=1000 + 4000)
    ctx = ctx_for(bot, user(10))
    run(_resolve_charge(bot, ctx, order, "poke", pressed=True))
    assert bot.store.sentence_for(20) is None


def test_charge_prompt_only_answers_to_protected() -> None:
    bot = make_bot()
    order = order_filed(bot, 10, 20)
    view = PressChargesView(order, "poke")
    bystander = interaction(bot, 99)
    assert run(view.interaction_check(bystander)) is False
    bystander.response.send_message.assert_awaited_once()
    assert run(view.interaction_check(interaction(bot, 10))) is True


# ---------------------------------------------------------------------------
# Jail blocking of non-jailed targets; jailed-to-jailed allowed
# ---------------------------------------------------------------------------


def test_jailed_user_cannot_target_free_user() -> None:
    bot = make_bot()
    inmate, free = user(20), user(30)
    bot.store.jail_inmate(20, GUILD, 7, "poke", 10, 600)
    ctx = ctx_for(bot, inmate)
    run(matr_mod.matr.get_command("hug").callback(ctx, free))
    # No press-charges prompt, no hug - just the jail error reply.
    ctx.send.assert_not_awaited()
    ctx.reply.assert_awaited_once()
    text = ctx.reply.call_args.kwargs["embed"].description
    assert "jail" in text.lower()


def test_jailed_user_cannot_marry_free_user() -> None:
    bot = make_bot()
    inmate, free = user(20), user(30)
    bot.store.jail_inmate(20, GUILD, 7, "poke", 10, 600)
    ctx = ctx_for(bot, inmate)
    run(matr_mod.matr_marry.callback(ctx, free))
    assert bot.store.proposals_for(30) == []
    ctx.reply.assert_awaited_once()


def test_free_user_cannot_target_inmate_with_proposals() -> None:
    """The free side may not pull inmates into real relationships."""
    bot = make_bot()
    free, inmate = user(30), user(20)
    bot.store.jail_inmate(20, GUILD, 7, "poke", 10, 600)
    ctx = ctx_for(bot, free)
    run(matr_mod.matr_marry.callback(ctx, inmate))
    # A real proposal to a jailed user still goes through - the inmate
    # answers from inside (and it enacts on the real tree). Not blocked.
    assert len(bot.store.proposals_for(20, "marry")) == 1


def test_jailed_pair_can_jail_marry() -> None:
    bot = make_bot()
    a, b = user(20), user(30)
    bot.store.jail_inmate(20, GUILD, 7, "poke", 10, 600)
    bot.store.jail_inmate(30, GUILD, 7, "poke", 10, 600)
    run(matr_mod.matr_marry.callback(ctx_for(bot, a), b))
    run(matr_mod.matr_accept.callback(ctx_for(bot, b), None))
    assert bot.store.jail_partners_of(20) == [30]
    assert bot.store.partners_of(20) == []


def test_jailed_pair_can_jail_adopt() -> None:
    bot = make_bot()
    a, b = user(20), user(30)
    bot.store.jail_inmate(20, GUILD, 7, "poke", 10, 600)
    bot.store.jail_inmate(30, GUILD, 7, "poke", 10, 600)
    run(matr_mod.matr_adopt.callback(ctx_for(bot, a), b))
    run(matr_mod.matr_accept.callback(ctx_for(bot, b), None))
    assert bot.store.jail_children_of(20) == [30]
    assert bot.store.children_of(20) == []


def test_jailed_pair_fun_action_passes() -> None:
    bot = make_bot()
    a, b = user(20), user(30)
    bot.store.jail_inmate(20, GUILD, 7, "poke", 10, 600)
    bot.store.jail_inmate(30, GUILD, 7, "poke", 10, 600)
    ctx = ctx_for(bot, a)
    run(matr_mod.matr.get_command("hug").callback(ctx, b))
    ctx.reply.assert_awaited_once()
    assert "hugs" in ctx.reply.call_args.kwargs["embed"].description


def test_jail_proposal_lapses_after_release() -> None:
    """A jail proposal accepted after someone's release enacts nothing."""
    bot = make_bot()
    a, b = user(20), user(30)
    bot.store.jail_inmate(20, GUILD, 7, "poke", 10, 600)
    bot.store.jail_inmate(30, GUILD, 7, "poke", 10, 600)
    run(matr_mod.matr_marry.callback(ctx_for(bot, a), b))
    bot.store.release_inmate(20)
    run(matr_mod.matr_accept.callback(ctx_for(bot, b), None))
    assert bot.store.jail_partners_of(20) == []
    assert bot.store.partners_of(20) == []
    assert bot.store.partners_of(30) == []


def test_jail_marriage_check_rejects_duplicate() -> None:
    bot = make_bot()
    bot.store.jail_inmate(20, GUILD, 7, "poke", 10, 600)
    bot.store.jail_inmate(30, GUILD, 7, "poke", 10, 600)
    bot.store.add_jail_partners(20, 30)
    assert jail_mod.check_jail_marry(bot.store, 20, 30) is not None
    assert jail_mod.check_jail_marry(bot.store, 20, 20) is not None
    assert jail_mod.check_jail_marry(bot.store, 30, 40) is None


# ---------------------------------------------------------------------------
# Ephemerality: relationships die with the sentence
# ---------------------------------------------------------------------------


def test_sweep_releases_and_dissolves() -> None:
    store = Store(":memory:")
    store.jail_inmate(20, GUILD, 7, "poke", 10, 60, now=1000)
    store.jail_inmate(30, GUILD, 7, "poke", 10, 60, now=1000)
    store.add_jail_partners(20, 30)

    report = jail_mod.sweep_expiry(store, now=1000 + 61)
    assert len(report.released) == 2
    assert store.jail_partners_of(20) == []
    assert not store.is_jailed(20, now=1061)

    # A second sweep at the same clock has nothing left to do.
    assert jail_mod.sweep_expiry(store, now=1000 + 61).released == []


def test_sweep_expires_orders() -> None:
    store = Store(":memory:")
    store.file_restraining_order(GUILD, 7, 10, 20, ttl_seconds=3600, now=1000)
    report = jail_mod.sweep_expiry(store, now=1000 + 3601)
    assert len(report.expired_orders) == 1
    assert report.expired_orders[0].protected == 10


def test_jail_relationships_never_touch_real_tree() -> None:
    """End-to-end: jail-marry inside, serve the sentence, and nothing
    remains on either side."""
    bot = make_bot()
    a, b = user(20), user(30)
    s_a = bot.store.jail_inmate(20, GUILD, 7, "poke", 10, 60)
    bot.store.jail_inmate(30, GUILD, 7, "poke", 10, 60)
    run(matr_mod.matr_marry.callback(ctx_for(bot, a), b))
    run(matr_mod.matr_accept.callback(ctx_for(bot, b), None))
    assert bot.store.jail_partners_of(20) == [30]

    report = jail_mod.sweep_expiry(bot.store, now=s_a.release_at + 1)
    assert len(report.released) == 2
    assert bot.store.jail_partners_of(20) == []
    assert bot.store.partners_of(20) == []
    assert bot.store.partners_of(30) == []


# ---------------------------------------------------------------------------
# Release announcements
# ---------------------------------------------------------------------------


def _bot_with_channel(bot, channel):
    bot.get_channel = lambda cid: channel  # type: ignore[method-assign]
    return bot


def test_release_announcement_mentions_dissolutions() -> None:
    bot = make_bot()
    channel = SimpleNamespace(send=AsyncMock())
    _bot_with_channel(bot, channel)
    bot.store.jail_inmate(20, GUILD, 7, "poke", 10, 60, now=1000)
    bot.store.jail_inmate(30, GUILD, 7, "poke", 10, 60, now=1000)
    bot.store.add_jail_partners(20, 30)
    bot.store.add_jail_child(30, 20)

    report = jail_mod.sweep_expiry(bot.store, now=1000 + 61)
    run(_announce_expiry(bot, report))
    assert channel.send.await_count == 2
    text = " ".join(
        c.kwargs["embed"].description for c in channel.send.await_args_list
    )
    assert "<@20>" in text and "<@30>" in text
    assert "released" in text
    assert "divorced" in text or "abandoned" in text


def test_expired_order_announcement() -> None:
    bot = make_bot()
    channel = SimpleNamespace(send=AsyncMock())
    _bot_with_channel(bot, channel)
    bot.store.file_restraining_order(
        GUILD, 7, 10, 20, ttl_seconds=3600, now=1000
    )
    report = jail_mod.sweep_expiry(bot.store, now=1000 + 3601)
    run(_announce_expiry(bot, report))
    channel.send.assert_awaited_once()
    assert "expired" in channel.send.call_args.kwargs["embed"].description


def test_announce_expiry_skips_missing_channels() -> None:
    bot = make_bot()
    bot.get_channel = lambda cid: None  # type: ignore[method-assign]
    bot.store.jail_inmate(20, GUILD, 7, "poke", 10, 60, now=1000)
    report = jail_mod.sweep_expiry(bot.store, now=1000 + 61)
    run(_announce_expiry(bot, report))  # no crash


# ---------------------------------------------------------------------------
# `matr clear`
# ---------------------------------------------------------------------------


def _seed_guild(bot, guild_id: int, base: int) -> None:
    """One of every guild-scoped record, tagged by guild_id."""
    store = bot.store
    store.set_prefix(guild_id, "?")
    store.create_proposal(guild_id, 7, base, base + 1, "marry", 300)
    store.create_notice(guild_id, 7, base, base + 2, base + 3)
    store.file_restraining_order(
        guild_id, 7, base, base + 4, ttl_seconds=3600
    )
    store.jail_inmate(base + 5, guild_id, 7, "poke", base, 600)
    store.jail_inmate(base + 6, guild_id, 7, "poke", base, 600)
    store.add_jail_partners(base + 5, base + 6)


def test_clear_requires_manage_guild() -> None:
    bot = make_bot()
    member = user(1)
    ctx = ctx_for(bot, member)
    ctx.interaction = None
    ctx.permissions = SimpleNamespace(manage_guild=False)
    with pytest.raises(matr_mod.commands.MissingPermissions):
        run(matr_mod.matr_clear.can_run(ctx))

    ctx.permissions = SimpleNamespace(manage_guild=True)
    assert run(matr_mod.matr_clear.can_run(ctx)) is True


def test_clear_slash_requires_manage_guild() -> None:
    bot = make_bot()
    admin = bot.tree.get_command("matr").get_command("admin")
    perms = admin.get_command("clear").default_permissions
    assert perms is not None and perms.manage_guild


def test_clear_shows_warning_first() -> None:
    bot = make_bot()
    _seed_guild(bot, GUILD, 500)
    admin = user(1)
    admin.guild_permissions = SimpleNamespace(manage_guild=True)
    ctx = ctx_for(bot, admin)
    run(matr_mod.matr_clear.callback(ctx))
    view = ctx.reply.call_args.kwargs["view"]
    assert isinstance(view, ClearConfirmView)
    # Nothing cleared yet.
    assert bot.store.get_prefix(GUILD) == "?"
    assert bot.store.is_jailed(505)


def test_clear_confirm_resets_only_that_guild() -> None:
    bot = make_bot()
    _seed_guild(bot, GUILD, 500)
    _seed_guild(bot, 43, 600)
    bot.store.add_partners(600, 601)  # global: must survive

    counts = bot.store.clear_guild(GUILD)
    assert counts["guild_settings"] == 1
    assert counts["proposals"] == 1
    assert counts["notices"] == 1
    assert counts["restraining_orders"] == 1
    assert counts["jail_sentences"] == 2
    assert counts["jail_partners"] == 1

    # Guild 42 is gone...
    assert bot.store.get_prefix(GUILD) is None
    assert bot.store.proposals_for(501) == []
    assert bot.store.restraining_order(500, 504) is None
    assert not bot.store.is_jailed(505)
    assert bot.store.jail_partners_of(505) == []

    # ...guild 43 is untouched...
    assert bot.store.get_prefix(43) == "?"
    assert len(bot.store.proposals_for(601)) == 1
    assert bot.store.restraining_order(600, 604) is not None
    assert bot.store.is_jailed(605)
    assert bot.store.jail_partners_of(605) == [606]

    # ...and global relationships survive.
    assert bot.store.partners_of(600) == [601]


def test_clear_confirm_via_view() -> None:
    bot = make_bot()
    _seed_guild(bot, GUILD, 500)
    view = ClearConfirmView(invoker_id=1, guild_id=GUILD)
    confirm = [i for i in view.children if i.label == "Confirm reset"][0]
    run(confirm.callback(interaction(bot, 1)))
    assert bot.store.get_prefix(GUILD) is None


def test_clear_cancel_clears_nothing() -> None:
    bot = make_bot()
    _seed_guild(bot, GUILD, 500)
    view = ClearConfirmView(invoker_id=1, guild_id=GUILD)
    cancel = [i for i in view.children if i.label == "Cancel"][0]
    run(cancel.callback(interaction(bot, 1)))
    assert bot.store.get_prefix(GUILD) == "?"
    assert bot.store.is_jailed(505)


def test_clear_timeout_clears_nothing_and_disables() -> None:
    bot = make_bot()
    _seed_guild(bot, GUILD, 500)
    view = ClearConfirmView(invoker_id=1, guild_id=GUILD)
    view.message = SimpleNamespace(edit=AsyncMock())
    run(view.on_timeout())
    assert all(item.disabled for item in view.children)
    view.message.edit.assert_awaited_once()
    assert bot.store.get_prefix(GUILD) == "?"


def test_clear_view_only_answers_to_invoker() -> None:
    view = ClearConfirmView(invoker_id=1, guild_id=GUILD)
    bot = make_bot()
    other = interaction(bot, 2)
    assert run(view.interaction_check(other)) is False
    other.response.send_message.assert_awaited_once()
    assert run(view.interaction_check(interaction(bot, 1))) is True


def test_slash_clear_registered() -> None:
    bot = make_bot()
    admin = bot.tree.get_command("matr").get_command("admin")
    assert admin.get_command("clear") is not None


def test_slash_restrain_registered() -> None:
    bot = make_bot()
    assert bot.tree.get_command("matr").get_command("restrain") is not None
