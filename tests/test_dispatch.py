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
    # No Fluxpoint key: GIF lookups short-circuit instead of hitting the API.
    bot = MatrimonyBot(Config(database_path=":memory:", fluxpoint_api_key=""))
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
        send=AsyncMock(),
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
# Polyamory: existing partners get an accept/divorce notice on a new marriage
# ---------------------------------------------------------------------------


def _triangle(bot) -> tuple:
    """a proposes to b, who is already married to c; b accepts."""
    a, b, c = user(1101), user(1102), user(1103)
    bot.store.add_partners(b.id, c.id)
    run(matr_mod.matr_marry.callback(ctx_for(bot, a), b))
    run(matr_mod.matr_accept.callback(ctx_for(bot, b), None))
    return a, b, c


def test_new_marriage_notifies_existing_partners() -> None:
    """The marriage forms immediately on the target's accept; the existing
    partner is merely notified - their answer never blocks it."""
    bot = make_bot()
    a, b, c = _triangle(bot)
    assert sorted(bot.store.partners_of(b.id)) == sorted([a.id, c.id])
    notices = bot.store.notices_for(c.id)
    assert len(notices) == 1
    assert notices[0].spouse_id == b.id
    assert notices[0].other_id == a.id
    # The newlyweds themselves get no notice.
    assert bot.store.notices_for(a.id) == []
    assert bot.store.notices_for(b.id) == []


def test_proposers_partners_also_notified() -> None:
    """Partners of the proposer are notified too, not just the target's."""
    bot = make_bot()
    a, b, d = user(1104), user(1105), user(1106)
    bot.store.add_partners(a.id, d.id)
    run(matr_mod.matr_marry.callback(ctx_for(bot, a), b))
    run(matr_mod.matr_accept.callback(ctx_for(bot, b), None))
    notices = bot.store.notices_for(d.id)
    assert len(notices) == 1
    assert notices[0].spouse_id == a.id
    assert notices[0].other_id == b.id


def test_no_notices_for_first_marriage() -> None:
    """The single-partner flow is unchanged: no notices when nobody was
    already married."""
    bot = make_bot()
    a, b = user(1107), user(1108)
    run(matr_mod.matr_marry.callback(ctx_for(bot, a), b))
    run(matr_mod.matr_accept.callback(ctx_for(bot, b), None))
    assert bot.store.partners_of(a.id) == [b.id]
    assert bot.store._row("SELECT COUNT(*) FROM notices")[0] == 0


def test_notice_accept_acknowledges() -> None:
    """`!matr accept` on a notice is acknowledgement only: the existing
    marriage and the new one both stay."""
    bot = make_bot()
    a, b, c = _triangle(bot)
    run(matr_mod.matr_accept.callback(ctx_for(bot, c), None))
    assert bot.store.notices_for(c.id) == []
    assert c.id in bot.store.partners_of(b.id)
    assert a.id in bot.store.partners_of(b.id)


def test_notice_divorce_via_text_command() -> None:
    """The notice's divorce option maps onto the normal `divorce` command."""
    bot = make_bot()
    a, b, c = _triangle(bot)
    run(matr_mod.matr_divorce.callback(ctx_for(bot, c), b))
    assert bot.store.partners_of(c.id) == []
    assert bot.store.partners_of(b.id) == [a.id]
    # The notice is cleared once the underlying marriage is gone.
    assert bot.store.notices_for(c.id) == []


def test_notice_divorce_via_button_path() -> None:
    """Same path the Divorce button in PartnerNoticeView calls."""
    bot = make_bot()
    a, b, c = _triangle(bot)
    notice = bot.store.notices_for(c.id)[0]
    run(
        matr_mod._resolve_notice(
            bot, ctx_for(bot, c), notice.id, accepted=False
        )
    )
    assert bot.store.partners_of(c.id) == []
    assert bot.store.partners_of(b.id) == [a.id]
    assert bot.store.notices_for(c.id) == []


def test_notice_survives_unanswered() -> None:
    """No answer is required: an ignored notice never undoes the marriage."""
    bot = make_bot()
    a, b, c = _triangle(bot)
    assert c.id in bot.store.partners_of(b.id)
    assert a.id in bot.store.partners_of(b.id)


def test_forcemarry_notifies_existing_partners() -> None:
    """Force-marriages notify existing partners the same way."""
    bot = make_bot()
    admin, a, b, c = user(1201), user(1202), user(1203), user(1204)
    bot.store.add_partners(a.id, c.id)
    run(matr_mod.matr_forcemarry.callback(ctx_for(bot, admin), a, b))
    assert b.id in bot.store.partners_of(a.id)
    notices = bot.store.notices_for(c.id)
    assert len(notices) == 1
    assert notices[0].spouse_id == a.id
    assert notices[0].other_id == b.id


def test_decline_with_only_a_notice_hints_at_divorce() -> None:
    """`decline` still applies to proposals only; with just a notice pending
    it points the user at `divorce` and leaves everything intact."""
    bot = make_bot()
    a, b, c = _triangle(bot)
    ctx = ctx_for(bot, c)
    run(matr_mod.matr_decline.callback(ctx, None))
    assert c.id in bot.store.partners_of(b.id)
    assert len(bot.store.notices_for(c.id)) == 1


# ---------------------------------------------------------------------------
# End-to-end dispatch through process_commands (real parser, fake message)
# ---------------------------------------------------------------------------


def wire_message(bot, author, content: str, guild_id: int = 42):
    """A message fake enough to run through the real command parser."""
    return SimpleNamespace(
        id=1,
        author=author,
        content=content,
        guild=SimpleNamespace(id=guild_id, get_member=lambda uid: None),
        channel=SimpleNamespace(id=7),
        to_message_reference_dict=lambda: {"message_id": 1},
        attachments=[],
        _state=bot._connection,
    )


def stub_send(bot) -> AsyncMock:
    """Intercept the HTTP layer so replies don't hit the network."""
    bot._connection.http.send_message = AsyncMock(return_value={"id": "2"})
    # Skip real discord.Message construction for the sent reply.
    bot._connection.create_message = (
        lambda channel, data: SimpleNamespace(id=int(data.get("id", 0)))
    )
    return bot._connection.http.send_message


def test_process_commands_dispatches_bot_author_end_to_end() -> None:
    """Regression: discord.py's built-in process_commands silently drops
    every message whose author is a bot. Ours must reach the command and
    produce a reply - this is what lets other bots use ``!matr``."""
    bot = make_bot()
    send = stub_send(bot)
    msg = wire_message(bot, user(2, bot=True), "!matr help")
    run(bot.process_commands(msg))
    send.assert_awaited_once()


def test_process_commands_human_author_end_to_end() -> None:
    bot = make_bot()
    send = stub_send(bot)
    msg = wire_message(bot, user(1), "!matr help")
    run(bot.process_commands(msg))
    send.assert_awaited_once()


def test_process_commands_skips_own_messages() -> None:
    """The self-command loop guard still applies."""
    bot = make_bot()
    send = stub_send(bot)
    msg = wire_message(bot, user(BOT_USER_ID, bot=True), "!matr help")
    run(bot.process_commands(msg))
    send.assert_not_awaited()


def test_process_commands_ignores_non_command() -> None:
    bot = make_bot()
    send = stub_send(bot)
    msg = wire_message(bot, user(1), "just chatting")
    run(bot.process_commands(msg))
    send.assert_not_awaited()


# ---------------------------------------------------------------------------
# Lenient parsing: whitespace, extra text, mentions
# ---------------------------------------------------------------------------


def test_whitespace_after_prefix() -> None:
    bot = make_bot()
    send = stub_send(bot)
    msg = wire_message(bot, user(1), "!  matr help")
    run(bot.process_commands(msg))
    send.assert_awaited_once()


def test_whitespace_between_group_and_subcommand() -> None:
    bot = make_bot()
    send = stub_send(bot)
    msg = wire_message(bot, user(1), "!matr    help")
    run(bot.process_commands(msg))
    send.assert_awaited_once()


def test_surrounding_whitespace() -> None:
    bot = make_bot()
    send = stub_send(bot)
    msg = wire_message(bot, user(1), "   !matr help   ")
    run(bot.process_commands(msg))
    send.assert_awaited_once()


def test_extra_text_after_arguments() -> None:
    bot = make_bot()
    send = stub_send(bot)
    msg = wire_message(bot, user(1), "!matr help and some trailing text")
    run(bot.process_commands(msg))
    send.assert_awaited_once()


def test_mention_prefix() -> None:
    bot = make_bot()
    send = stub_send(bot)
    msg = wire_message(bot, user(1), f"<@{BOT_USER_ID}> matr help")
    run(bot.process_commands(msg))
    send.assert_awaited_once()


def test_mention_prefix_from_bot_author() -> None:
    bot = make_bot()
    send = stub_send(bot)
    msg = wire_message(bot, user(3, bot=True), f"<@{BOT_USER_ID}> matr help")
    run(bot.process_commands(msg))
    send.assert_awaited_once()


# ---------------------------------------------------------------------------
# Commands on a later line of the message
# ---------------------------------------------------------------------------


def test_command_on_second_line() -> None:
    """Chatter before the command is fine: the prefix just has to start
    a line of its own."""
    bot = make_bot()
    send = stub_send(bot)
    msg = wire_message(bot, user(1), "hey everyone\n!matr help")
    run(bot.process_commands(msg))
    send.assert_awaited_once()


def test_command_on_later_line_after_several_lines() -> None:
    bot = make_bot()
    send = stub_send(bot)
    msg = wire_message(
        bot, user(1), "line one\nline two\nline three\n!matr stats"
    )
    run(bot.process_commands(msg))
    send.assert_awaited_once()


def test_command_line_allows_leading_whitespace() -> None:
    bot = make_bot()
    send = stub_send(bot)
    msg = wire_message(bot, user(1), "chatter\n   !matr help")
    run(bot.process_commands(msg))
    send.assert_awaited_once()


def test_trailing_lines_after_command_are_ignored() -> None:
    """Only the command line is parsed - text below it isn't read as
    arguments."""
    bot = make_bot()
    send = stub_send(bot)
    msg = wire_message(bot, user(1), "!matr partners\nand some chatter")
    run(bot.process_commands(msg))
    send.assert_awaited_once()


def test_mention_command_on_second_line() -> None:
    bot = make_bot()
    send = stub_send(bot)
    msg = wire_message(
        bot, user(1), f"listen up\n<@{BOT_USER_ID}> matr help"
    )
    run(bot.process_commands(msg))
    send.assert_awaited_once()


def test_mid_line_command_is_not_recognized() -> None:
    """The prefix must open a line - `say !matr help now` is chatter."""
    bot = make_bot()
    send = stub_send(bot)
    msg = wire_message(bot, user(1), "say !matr help now")
    run(bot.process_commands(msg))
    send.assert_not_awaited()


def test_multiline_message_without_command_ignored() -> None:
    bot = make_bot()
    send = stub_send(bot)
    msg = wire_message(bot, user(1), "hello\nhow are you\ntalk later")
    run(bot.process_commands(msg))
    send.assert_not_awaited()


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


def test_custom_guild_prefix_end_to_end() -> None:
    bot = make_bot()
    send = stub_send(bot)
    bot.store.set_prefix(42, "?")
    msg = wire_message(bot, user(1), "?matr help", guild_id=42)
    run(bot.process_commands(msg))
    send.assert_awaited_once()


def test_case_insensitive_command() -> None:
    bot = make_bot()
    send = stub_send(bot)
    msg = wire_message(bot, user(1), "!MATR HELP")
    run(bot.process_commands(msg))
    send.assert_awaited_once()
