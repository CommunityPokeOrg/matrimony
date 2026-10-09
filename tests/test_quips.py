"""Tests for the paternity-denial Easter egg: detection rules and the
reply behaviour of the ``on_message`` listener helper."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from matrimony.bot import MatrimonyBot
from matrimony.cogs import matr as matr_mod
from matrimony.cogs.matr import MatrCog
from matrimony.config import Config

BOT_USER_ID = 999999


def make_bot() -> MatrimonyBot:
    bot = MatrimonyBot(Config(database_path=":memory:"))
    MatrCog(bot)
    # Pretend we're logged in as this user id
    bot._connection.user = SimpleNamespace(id=BOT_USER_ID)  # type: ignore[attr-defined]
    return bot


def user(uid: int, *, bot: bool = False):
    return SimpleNamespace(
        id=uid,
        bot=bot,
        name=f"user{uid}",
        display_name=f"user{uid}",
        mention=f"<@{uid}>",
    )


def message(author, content: str, guild=None):
    return SimpleNamespace(
        author=author,
        content=content,
        guild=guild,
        reply=AsyncMock(),
    )


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Accusation detection
# ---------------------------------------------------------------------------


def test_detects_paternity_accusations() -> None:
    """Claims that the bot fathered a child must trigger the quip."""
    cases = [
        f"<@{BOT_USER_ID}> got me pregnant",
        f"<@!{BOT_USER_ID}> got me pregnant",
        "@Matrimony is the father of my child",
        "the bot impregnated me, i swear",
        "does the bot pay child support??",
        "MATRIMONY IS MY BABY DADDY",
        "bot paternity test when",
        "the bot knocked me up",
    ]
    for text in cases:
        assert matr_mod._paternity_accusation(text, BOT_USER_ID), text


def test_ignores_non_accusations() -> None:
    """Needs BOTH a bot reference and a paternity keyword."""
    cases = [
        "i'm pregnant!!!",  # keyword but no bot reference
        "the bot is my friend",  # bot reference but no keyword
        "child support laws are confusing",  # keyword but no bot reference
        "my cat is the baby daddy",  # no bot reference
        "<@12345> got me pregnant",  # mentioning a DIFFERENT user
        "!matr adopt @someone",
        "just chatting",
    ]
    for text in cases:
        assert not matr_mod._paternity_accusation(text, BOT_USER_ID), text


# ---------------------------------------------------------------------------
# Reply behaviour
# ---------------------------------------------------------------------------


def test_easter_egg_replies_to_accusation() -> None:
    bot = make_bot()
    msg = message(user(1), f"<@{BOT_USER_ID}> you got me pregnant")
    run(matr_mod._maybe_paternity_quip(bot, msg))
    msg.reply.assert_awaited_once()
    embed = msg.reply.await_args.kwargs["embed"]
    # Whatever quip was picked, it must be one of ours (with the prefix
    # and command name filled in).
    filled = {
        q.format(prefix="!", cmd=bot.config.command_name)
        for q in matr_mod._PATERNITY_QUIPS
    }
    assert embed.description in filled


def test_easter_egg_uses_guild_prefix_in_quip() -> None:
    """The `children` quip cites the guild's configured prefix."""
    bot = make_bot()
    bot.store.set_prefix(42, "?")
    guild = SimpleNamespace(id=42)
    msg = message(user(1), "the bot got me pregnant", guild=guild)
    run(matr_mod._maybe_paternity_quip(bot, msg))
    embed = msg.reply.await_args.kwargs["embed"]
    filled = {
        q.format(prefix="?", cmd=bot.config.command_name)
        for q in matr_mod._PATERNITY_QUIPS
    }
    assert embed.description in filled


def test_easter_egg_ignores_normal_messages() -> None:
    bot = make_bot()
    msg = message(user(1), "just chatting")
    run(matr_mod._maybe_paternity_quip(bot, msg))
    msg.reply.assert_not_awaited()


def test_easter_egg_skips_own_messages() -> None:
    """The self-loop guard applies to the Easter egg too."""
    bot = make_bot()
    msg = message(user(BOT_USER_ID, bot=True), "the bot got me pregnant")
    run(matr_mod._maybe_paternity_quip(bot, msg))
    msg.reply.assert_not_awaited()
