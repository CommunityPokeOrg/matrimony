"""Tests for the unknown-subcommand quips and the help embed's wisdom line."""

import random
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

from matrimony import quips
from matrimony.cogs.matr import MatrCog, _help_embed

_HELP_QUIPS = quips.HELP
_UNKNOWN_QUIPS = quips.UNKNOWN


def _sent_payload(send: AsyncMock) -> dict:
    """The payload of the last stubbed http.send_message call."""
    params = send.call_args.kwargs["params"]
    return params.payload if hasattr(params, "payload") else params


def _content_quip(payload: dict) -> str:
    """The `-# <quip>` subtext that makes up a reply's content."""
    return payload["content"].removeprefix("-# ")


def _wisdom_lines(description: str) -> list[str]:
    """Subtext lines (`-# `) in an embed description."""
    return [
        line for line in description.splitlines() if line.startswith("-# ")
    ]


# ---------------------------------------------------------------------------
# Help embed wisdom line
# ---------------------------------------------------------------------------


def test_help_embed_under_discord_description_limit() -> None:
    emb = _help_embed("!", "matr")
    assert len(emb.description) <= 4096


def test_help_embed_has_exactly_one_wisdom_line_at_the_bottom() -> None:
    emb = _help_embed("!", "matr")
    assert "**Marital wisdom**" in emb.description
    # The commands live in fields now, so the quip closes the description.
    lines = _wisdom_lines(emb.description)
    assert emb.description.rstrip().endswith(lines[-1])
    assert len(lines) == 1
    # The line is one quip from the pool, and only that quip made it in.
    assert lines[0].removeprefix("-# ") in _HELP_QUIPS
    assert sum(q in emb.description for q in _HELP_QUIPS) == 1


def test_help_embed_wisdom_pick_is_seedable() -> None:
    """An injected RNG makes the chosen quip deterministic."""
    expected = random.Random(1234).choice(_HELP_QUIPS)
    emb = _help_embed("!", "matr", rng=random.Random(1234))
    assert f"-# {expected}" in emb.description


def test_help_embed_different_seeds_can_pick_different_quips() -> None:
    picks = {
        _wisdom_lines(
            _help_embed("!", "matr", rng=random.Random(seed)).description
        )[0]
        for seed in range(10)
    }
    assert len(picks) > 1


def test_help_embed_quips_pool_stays_large() -> None:
    """The source pool keeps its full set of quips for random picks."""
    assert len(_HELP_QUIPS) >= 25


def test_help_embed_keeps_command_listing() -> None:
    """Each area gets its own field instead of one wall of text."""
    emb = _help_embed("!", "matr")
    names = [field.name for field in emb.fields]
    for section in ("Love", "Parentage", "Trees", "Fun", "Meta"):
        assert section in names, f"missing help section: {section}"
    for field in emb.fields:
        assert len(field.value) <= 1024, f"field too long: {field.name}"
    assert len(emb.fields) <= 25


def test_bare_matr_and_help_each_get_one_wisdom_line() -> None:
    """`!matr` and `!matr help` share the random wisdom behaviour."""
    for command in ("!matr", "!matr help"):
        bot = make_bot()
        send = stub_send(bot)
        run(bot.process_commands(wire_message(bot, user(1), command)))
        description = _sent_payload(send)["embeds"][0]["description"]
        lines = _wisdom_lines(description)
        assert len(lines) == 1
        assert lines[0].removeprefix("-# ") in _HELP_QUIPS


# ---------------------------------------------------------------------------
# `!matr help bot` - bot-specific submenu
# ---------------------------------------------------------------------------


def test_help_bot_shows_bot_submenu() -> None:
    bot = make_bot()
    send = stub_send(bot)
    run(bot.process_commands(wire_message(bot, user(1), "!matr help bot")))
    send.assert_awaited_once()
    embed = _sent_payload(send)["embeds"][0]
    assert "bot" in embed["title"].lower()
    # Bot-specific guidance, not the generic command listing.
    assert "any line" in embed["description"]
    assert "bot accounts are first-class" in embed["description"]
    assert "**Love**" not in embed["description"]
    # Still ends with the usual wisdom subtext.
    lines = _wisdom_lines(embed["description"])
    assert len(lines) == 1
    assert lines[0].removeprefix("-# ") in _HELP_QUIPS


def test_help_bot_topic_is_case_insensitive() -> None:
    bot = make_bot()
    send = stub_send(bot)
    run(bot.process_commands(wire_message(bot, user(1), "!matr help BOT")))
    embed = _sent_payload(send)["embeds"][0]
    assert "bot" in embed["title"].lower()


def test_help_with_other_topic_falls_back_to_full_list() -> None:
    """An unrecognized `help <topic>` shows the normal help embed."""
    bot = make_bot()
    send = stub_send(bot)
    run(bot.process_commands(wire_message(bot, user(1), "!matr help trees")))
    embed = _sent_payload(send)["embeds"][0]
    assert "MarriageBot-style" in embed["description"]
    assert any(field["name"] == "Trees" for field in embed["fields"])


def test_help_bot_mention_advertised() -> None:
    """The bot submenu tells users the mention form exists."""
    from matrimony.cogs.matr import _bot_help_embed

    emb = _bot_help_embed("!", "matr")
    assert "@Matrimony" in emb.description


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
    assert payload["content"].startswith("-# ")
    assert _content_quip(payload) in _UNKNOWN_QUIPS
    assert "MarriageBot-style" in payload["embeds"][0]["description"]


def test_unknown_subcommand_with_extra_words_still_quips() -> None:
    bot = make_bot()
    send = stub_send(bot)
    run(
        bot.process_commands(
            wire_message(bot, user(1), "!matr blorp and some more words")
        )
    )
    payload = _sent_payload(send)
    assert payload["content"].startswith("-# ")
    assert _content_quip(payload) in _UNKNOWN_QUIPS


def test_unknown_quips_rotate() -> None:
    seen = {quips.quip("unknown") for _ in range(len(_UNKNOWN_QUIPS))}
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
    payload = _sent_payload(send)
    assert payload["content"].startswith("-# ")
    assert _content_quip(payload) in _UNKNOWN_QUIPS


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
    content = ctx.reply.call_args.kwargs["content"]
    assert content.startswith("-# ")
    assert content.removeprefix("-# ") in _UNKNOWN_QUIPS
