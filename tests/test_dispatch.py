"""Tests for command dispatch: bot-authored messages are processed (the
bot-marriage feature), only this bot's own messages are skipped, plus
end-to-end proposal flows driven through the command callbacks."""

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


def user(uid: int, *, bot: bool = False, name: str | None = None):
    return SimpleNamespace(
        id=uid,
        bot=bot,
        name=name or f"user{uid}",
        display_name=name or f"user{uid}",
        mention=f"<@{uid}>",
        guild_permissions=SimpleNamespace(manage_guild=False),
    )


def message(author, content: str = "!matr help", guild=None):
    return SimpleNamespace(
        author=author, content=content, guild=guild, channel=SimpleNamespace(id=1)
    )


def ctx_for(bot: MatrimonyBot, author, guild_id: int = 42):
    guild = SimpleNamespace(id=guild_id, get_member=lambda uid: None)
    return SimpleNamespace(
        bot=bot,
        author=author,
        guild=guild,
        channel=SimpleNamespace(id=7),
        prefix="!",
        reply=AsyncMock(),
        command=None,
    )


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Dispatch policy
# ---------------------------------------------------------------------------


def test_should_process_human() -> None:
    bot = make_bot()
    assert bot.should_process(message(user(1, bot=False))) is True


def test_should_process_other_bot() -> None:
    """Bot-authored command messages must be dispatched - this is the
    feature that lets other bots marry/adopt/be adopted."""
    bot = make_bot()
    assert bot.should_process(message(user(2, bot=True))) is True


def test_should_process_ignores_self() -> None:
    """Only THIS bot's own messages are skipped - enough to prevent
    self-command loops without a blanket author.bot exclusion."""
    bot = make_bot()
    assert bot.should_process(message(user(BOT_USER_ID, bot=True))) is False


def test_on_message_dispatches_bot_authors() -> None:
    bot = make_bot()
    bot.process_commands = AsyncMock()  # type: ignore[method-assign]
    run(bot.on_message(message(user(2, bot=True))))
    bot.process_commands.assert_awaited_once()


def test_on_message_skips_own() -> None:
    bot = make_bot()
    bot.process_commands = AsyncMock()  # type: ignore[method-assign]
    run(bot.on_message(message(user(BOT_USER_ID, bot=True))))
    bot.process_commands.assert_not_awaited()


# ---------------------------------------------------------------------------
# Proposal flows through command callbacks (bot + human authors)
# ---------------------------------------------------------------------------


def test_bot_proposes_to_bot_and_accepts() -> None:
    """Full bot-marries-bot flow driven through the marry/accept commands."""
    bot = make_bot()
    proposer = user(100, bot=True)
    target = user(200, bot=True)

    run(matr_mod.matr_marry.callback(ctx_for(bot, proposer), target))
    pending = bot.store.proposals_for(target.id, "marry")
    assert len(pending) == 1 and pending[0].proposer == proposer.id

    run(matr_mod.matr_accept.callback(ctx_for(bot, target), None))
    assert bot.store.partners_of(proposer.id) == [target.id]
    assert bot.store.proposals_for(target.id) == []


def test_human_proposes_to_bot_and_bot_accepts() -> None:
    bot = make_bot()
    human = user(300, bot=False)
    robot = user(400, bot=True)

    run(matr_mod.matr_marry.callback(ctx_for(bot, human), robot))
    run(matr_mod.matr_accept.callback(ctx_for(bot, robot), None))
    assert bot.store.partners_of(human.id) == [robot.id]


def test_bot_adopts_human() -> None:
    bot = make_bot()
    robot = user(500, bot=True)
    human = user(600, bot=False)

    run(matr_mod.matr_adopt.callback(ctx_for(bot, robot), human))
    run(matr_mod.matr_accept.callback(ctx_for(bot, human), None))
    assert bot.store.parent_of(human.id) == robot.id
    assert bot.store.children_of(robot.id) == [human.id]


def test_human_adopts_bot() -> None:
    bot = make_bot()
    human = user(700, bot=False)
    robot = user(800, bot=True)

    run(matr_mod.matr_adopt.callback(ctx_for(bot, human), robot))
    run(matr_mod.matr_accept.callback(ctx_for(bot, robot), None))
    assert bot.store.parent_of(robot.id) == human.id


def test_bot_makeparent_and_divorce() -> None:
    bot = make_bot()
    child_bot = user(900, bot=True)
    parent_human = user(901, bot=False)

    run(matr_mod.matr_makeparent.callback(ctx_for(bot, child_bot), parent_human))
    run(matr_mod.matr_accept.callback(ctx_for(bot, parent_human), None))
    assert bot.store.parent_of(child_bot.id) == parent_human.id

    # and a divorce path
    other = user(902, bot=True)
    run(matr_mod.matr_marry.callback(ctx_for(bot, child_bot), other))
    run(matr_mod.matr_accept.callback(ctx_for(bot, other), None))
    run(matr_mod.matr_divorce.callback(ctx_for(bot, child_bot), other))
    assert bot.store.partners_of(child_bot.id) == []


def test_proposal_declined_by_bot() -> None:
    bot = make_bot()
    proposer = user(111, bot=True)
    target = user(222, bot=True)
    run(matr_mod.matr_marry.callback(ctx_for(bot, proposer), target))
    run(matr_mod.matr_decline.callback(ctx_for(bot, target), None))
    assert bot.store.partners_of(proposer.id) == []
    assert bot.store.proposals_for(target.id) == []


# ---------------------------------------------------------------------------
# Prefix resolution
# ---------------------------------------------------------------------------


def test_custom_guild_prefix() -> None:
    bot = make_bot()
    bot.store.set_prefix(42, "?")
    guild = SimpleNamespace(id=42)
    msg = message(user(1), guild=guild)
    prefixes = run(bot._get_prefix(bot, msg))
    assert "?" in prefixes
    # DM/other guild falls back to default
    other = message(user(1), guild=SimpleNamespace(id=99))
    assert "!" in run(bot._get_prefix(bot, other))
