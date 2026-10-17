"""Tests for bot-directed quips and the /matr slash command tree."""

from test_dispatch import BOT_USER_ID, ctx_for, make_bot, run, user

from matrimony.cogs import matr as matr_mod
from matrimony.cogs.matr import _BOT_QUIPS, _quip


def _reply_text(ctx) -> str:
    ctx.reply.assert_awaited_once()
    return ctx.reply.call_args.kwargs["embed"].description


def _bot_user():
    return user(BOT_USER_ID, bot=True)


# ---------------------------------------------------------------------------
# Quips
# ---------------------------------------------------------------------------


def test_fun_command_at_bot_appends_subtext_quip() -> None:
    bot = make_bot()
    ctx = ctx_for(bot, user(1))
    run(matr_mod.matr.get_command("hug").callback(ctx, _bot_user()))
    text = _reply_text(ctx)
    lines = text.split("\n")
    assert len(lines) == 2
    assert "hugs" in lines[0]
    assert lines[1].startswith("-# ")
    assert lines[1][3:] in _BOT_QUIPS["hug"]


def test_fun_command_at_normal_user_has_no_quip() -> None:
    bot = make_bot()
    ctx = ctx_for(bot, user(1))
    run(matr_mod.matr.get_command("hug").callback(ctx, user(2)))
    assert "-#" not in _reply_text(ctx)


def test_quips_rotate_through_the_set() -> None:
    kind = "tickle"
    seen = {_quip(kind) for _ in range(len(_BOT_QUIPS[kind]))}
    assert seen == set(_BOT_QUIPS[kind])


def test_marry_at_bot_is_declined_with_quip() -> None:
    bot = make_bot()
    ctx = ctx_for(bot, user(1))
    run(matr_mod.matr_marry.callback(ctx, _bot_user()))
    text = _reply_text(ctx)
    lines = text.split("\n")
    assert "declines" in lines[0]
    assert lines[1].startswith("-# ")
    assert lines[1][3:] in _BOT_QUIPS["marry"]
    # The bot never became a proposal target.
    assert bot.store.proposals_for(BOT_USER_ID) == []


def test_adopt_at_bot_is_declined_with_quip() -> None:
    bot = make_bot()
    ctx = ctx_for(bot, user(1))
    run(matr_mod.matr_adopt.callback(ctx, _bot_user()))
    text = _reply_text(ctx)
    assert "declines" in text
    assert text.split("\n")[1][3:] in _BOT_QUIPS["adopt"]
    assert bot.store.proposals_for(BOT_USER_ID) == []


def test_ship_including_bot_gets_quip() -> None:
    bot = make_bot()
    ctx = ctx_for(bot, user(1))
    run(matr_mod.matr_ship.callback(ctx, _bot_user(), user(2)))
    text = _reply_text(ctx)
    assert text.split("\n")[1][3:] in _BOT_QUIPS["ship"]


# ---------------------------------------------------------------------------
# New fun commands
# ---------------------------------------------------------------------------


def test_flirt_sends_a_pickup_line() -> None:
    bot = make_bot()
    ctx = ctx_for(bot, user(1))
    run(matr_mod.matr_flirt.callback(ctx, user(2)))
    text = _reply_text(ctx)
    assert "to <@2>" in text
    assert any(line in text for line in matr_mod._PICKUP_LINES)


def test_date_suggests_an_idea() -> None:
    bot = make_bot()
    ctx = ctx_for(bot, user(1))
    run(matr_mod.matr_date.callback(ctx, user(2)))
    text = _reply_text(ctx)
    assert "takes <@2>" in text
    assert any(idea in text for idea in matr_mod._DATE_IDEAS)


def test_anniversary_unmarried_is_rejected() -> None:
    bot = make_bot()
    ctx = ctx_for(bot, user(1))
    run(matr_mod.matr_anniversary.callback(ctx, None))
    assert "not married" in _reply_text(ctx)


def test_anniversary_reports_duration() -> None:
    bot = make_bot()
    bot.store.add_partners(1, 2)
    ctx = ctx_for(bot, user(1))
    run(matr_mod.matr_anniversary.callback(ctx, user(2)))
    text = _reply_text(ctx)
    assert "married for" in text
    assert "<@2>" in text


def test_anniversary_picks_the_only_partner() -> None:
    bot = make_bot()
    bot.store.add_partners(1, 2)
    ctx = ctx_for(bot, user(1))
    run(matr_mod.matr_anniversary.callback(ctx, None))
    assert "<@2>" in _reply_text(ctx)


def test_anniversary_ambiguous_without_argument() -> None:
    bot = make_bot()
    bot.store.add_partners(1, 2)
    bot.store.add_partners(1, 3)
    ctx = ctx_for(bot, user(1))
    run(matr_mod.matr_anniversary.callback(ctx, None))
    assert "multiple partners" in _reply_text(ctx)


# ---------------------------------------------------------------------------
# Slash command tree
# ---------------------------------------------------------------------------


def test_slash_tree_layout() -> None:
    bot = make_bot()
    group = bot.tree.get_command("matr")
    assert group is not None

    direct = [c.name for c in group.commands]
    for name in (
        "marry",
        "divorce",
        "accept",
        "decline",
        "partners",
        "anniversary",
        "adopt",
        "block",
    ):
        assert name in direct

    subs = {c.name: c for c in group.commands if hasattr(c, "commands")}
    assert set(subs) == {"fun", "admin", "meta"}
    assert len(group.commands) <= 25
    assert len(subs["fun"].commands) == 18
    assert len(subs["admin"].commands) == 6
    assert len(subs["meta"].commands) == 4

    # Slash command names must be lowercase and within 32 chars.
    for command in group.walk_commands():
        assert command.name == command.name.lower()
        assert len(command.name) <= 32


def test_slash_tree_covers_every_prefix_command() -> None:
    bot = make_bot()
    group = bot.tree.get_command("matr")
    slash_names = {c.name for c in group.walk_commands()}
    for prefix_cmd in matr_mod.matr.walk_commands():
        assert prefix_cmd.name in slash_names, prefix_cmd.name


def test_slash_marry_is_guild_only() -> None:
    bot = make_bot()
    marry = bot.tree.get_command("matr").get_command("marry")
    assert marry.guild_only is True


def test_slash_force_commands_require_manage_guild() -> None:
    bot = make_bot()
    admin = bot.tree.get_command("matr").get_command("admin")
    for name in ("forcemarry", "forcedivorce", "forceadopt", "forceemancipate"):
        perms = admin.get_command(name).default_permissions
        assert perms is not None and perms.manage_guild


def test_prefix_commands_still_registered() -> None:
    bot = make_bot()
    prefix_group = bot.get_command("matr")
    names = {c.name for c in prefix_group.walk_commands()}
    for name in ("hug", "forcemarry", "help", "flirt", "date", "anniversary"):
        assert name in names
