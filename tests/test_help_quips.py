"""Tests for the unknown-subcommand quips and the help embed's quip section."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from discord.ext import commands
from test_dispatch import (
    BOT_USER_ID,
    make_bot,
    run,
    stub_send,
    user,
    wire_message,
)

from matrimony.cogs import matr as matr_mod
from matrimony.cogs.matr import (
    _HELP_QUIPS,
    _UNKNOWN_QUIPS,
    MatrCog,
    _help_embed,
)


def _sent_payload(send: AsyncMock) -> dict:
    """The payload of the last stubbed http.send_message call."""
    params = send.call_args.kwargs["params"]
    return params.payload if hasattr(params, "payload") else params


# ---------------------------------------------------------------------------
# Help embed quips section
# ---------------------------------------------------------------------------


def test_help_embed_under_discord_description_limit() -> None:
    emb = _help_embed("!", "matr")
    assert len(emb.description) <= 4096


def test_help_embed_has_a_long_quips_section_at_the_bottom() -> None:
    emb = _help_embed("!", "matr")
    assert "**Marital wisdom**" in emb.description
    # The section is at the bottom of the description.
    assert emb.description.rindex("**Marital wisdom**") > (
        emb.description.rindex("**Meta**")
    )
    # Every quip made it in (it's a long list).
    assert len(_HELP_QUIPS) >= 25
    for quip in _HELP_QUIPS:
        assert quip in emb.description


def test_help_embed_keeps_command_listing() -> None:
    emb = _help_embed("!", "matr")
    for section in ("**Love**", "**Parentage**", "**Trees**", "**Fun**", "**Meta**"):
        assert section in emb.description


# ---------------------------------------------------------------------------
# Unknown subcommands -> funny quip
# ---------------------------------------------------------------------------


def test_unknown_subcommand_gets_a_quip() -> None:
    """`!matr blorp` replies with a rotating quip (plus the help embed)."""
    bot = make_bot()
    send = stub_send(bot)
    run(bot.process_commands(wire_message(bot, user(1), "!matr blorp")))
    send.assert_awaited_once()
    payload = _sent_payload(send)
    assert payload["content"] in _UNKNOWN_QUIPS
    assert "MarriageBot-style" in payload["embeds"][0]["description"]


def test_unknown_subcommand_with_extra_words_still_quips() -> None:
    bot = make_bot()
    send = stub_send(bot)
    run(
        bot.process_commands(
            wire_message(bot, user(1), "!matr blorp and some more words")
        )
    )
    assert _sent_payload(send)["content"] in _UNKNOWN_QUIPS


def test_unknown_quips_rotate() -> None:
    seen = {matr_mod._quip("unknown") for _ in range(len(_UNKNOWN_QUIPS))}
    assert seen == set(_UNKNOWN_QUIPS)


def test_known_subcommand_does_not_quip() -> None:
    """`!matr stats` runs normally - no quip content, no help embed."""
    bot = make_bot()
    send = stub_send(bot)
    run(bot.process_commands(wire_message(bot, user(1), "!matr stats")))
    payload = _sent_payload(send)
    assert payload.get("content") in (None, "")
    assert "Guilds" in payload["embeds"][0]["description"]


def test_bare_matr_shows_help_without_quip() -> None:
    bot = make_bot()
    send = stub_send(bot)
    run(bot.process_commands(wire_message(bot, user(1), "!matr")))
    payload = _sent_payload(send)
    assert payload.get("content") in (None, "")
    assert "MarriageBot-style" in payload["embeds"][0]["description"]


def test_unknown_subcommand_ignored_from_ourselves() -> None:
    """The bot's own messages never trigger the quip (self-loop guard)."""
    bot = make_bot()
    send = stub_send(bot)
    run(
        bot.process_commands(
            wire_message(bot, user(BOT_USER_ID, bot=True), "!matr blorp")
        )
    )
    send.assert_not_awaited()


def test_unknown_subcommand_from_bot_author_still_quips() -> None:
    """Other bots are first-class users - their typos get quips too."""
    bot = make_bot()
    send = stub_send(bot)
    run(
        bot.process_commands(
            wire_message(bot, user(2, bot=True), "!matr blorp")
        )
    )
    assert _sent_payload(send)["content"] in _UNKNOWN_QUIPS


def test_command_not_found_handler_also_quips() -> None:
    """Direct exercise of the CommandNotFound branch (in case discord.py
    ever routes `!matr <unknown>` there instead of the group callback)."""
    bot = make_bot()
    ctx = SimpleNamespace(
        bot=bot,
        prefix="!",
        message=SimpleNamespace(content="!matr blorp"),
        reply=AsyncMock(),
    )
    # The handler only needs self.bot - no need to re-register the cog.
    run(
        MatrCog.on_command_error(
            SimpleNamespace(bot=bot), ctx, commands.CommandNotFound()
        )
    )
    ctx.reply.assert_awaited_once()
    assert ctx.reply.call_args.kwargs["content"] in _UNKNOWN_QUIPS
