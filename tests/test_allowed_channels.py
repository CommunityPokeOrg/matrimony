"""Per-guild channel restrictions: MATRIMONY_ALLOWED_CHANNELS /
MATRIMONY_ALLOWED_CHANNELS_FILE parsing, and the dispatch gate that
silently ignores commands outside a guild's allowed channels."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from matrimony.bot import MatrimonyBot
from matrimony.cogs.matr import MatrCog
from matrimony.config import Config

BOT_USER_ID = 999999


def make_bot(**config_kwargs) -> MatrimonyBot:
    bot = MatrimonyBot(Config(database_path=":memory:", **config_kwargs))
    MatrCog(bot)
    # Pretend we're logged in as this user id
    bot._connection.user = SimpleNamespace(id=BOT_USER_ID)  # type: ignore[attr-defined]
    return bot


def wire_message(
    bot,
    author,
    content: str = "!matr help",
    guild_id: int | None = 42,
    channel_id: int = 7,
):
    """A message fake enough to run through the real command parser."""
    guild = (
        None
        if guild_id is None
        else SimpleNamespace(id=guild_id, get_member=lambda uid: None)
    )
    return SimpleNamespace(
        id=1,
        author=author,
        content=content,
        guild=guild,
        channel=SimpleNamespace(id=channel_id),
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


def user(uid: int):
    return SimpleNamespace(id=uid, bot=False, name=f"user{uid}")


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Configuration parsing
# ---------------------------------------------------------------------------


def test_no_env_no_restrictions() -> None:
    assert Config.from_env({}).allowed_channels == {}


def test_inline_json() -> None:
    config = Config.from_env(
        {
            "MATRIMONY_ALLOWED_CHANNELS": '{"42": ["7", "8"], "99": []}',
        }
    )
    assert config.allowed_channels == {42: frozenset({7, 8}), 99: frozenset()}


def test_inline_json_numeric_ids() -> None:
    config = Config.from_env(
        {"MATRIMONY_ALLOWED_CHANNELS": '{"42": [7, 8]}'}
    )
    assert config.allowed_channels == {42: frozenset({7, 8})}


def test_invalid_json_warns_and_unrestricts(caplog) -> None:
    config = Config.from_env(
        {"MATRIMONY_ALLOWED_CHANNELS": "not json"}
    )
    assert config.allowed_channels == {}
    assert "MATRIMONY_ALLOWED_CHANNELS" in caplog.text


def test_non_object_json_warns(caplog) -> None:
    config = Config.from_env({"MATRIMONY_ALLOWED_CHANNELS": '["7"]'})
    assert config.allowed_channels == {}
    assert "MATRIMONY_ALLOWED_CHANNELS" in caplog.text


def test_non_list_values_warn(caplog) -> None:
    config = Config.from_env(
        {"MATRIMONY_ALLOWED_CHANNELS": '{"42": "7"}'}
    )
    assert config.allowed_channels == {}
    assert "MATRIMONY_ALLOWED_CHANNELS" in caplog.text


def test_non_numeric_ids_warn(caplog) -> None:
    config = Config.from_env(
        {"MATRIMONY_ALLOWED_CHANNELS": '{"42": ["seven"]}'}
    )
    assert config.allowed_channels == {}
    assert "MATRIMONY_ALLOWED_CHANNELS" in caplog.text


def test_file_config(tmp_path) -> None:
    path = tmp_path / "channels.json"
    path.write_text('{"42": ["7"]}')
    config = Config.from_env(
        {"MATRIMONY_ALLOWED_CHANNELS_FILE": str(path)}
    )
    assert config.allowed_channels == {42: frozenset({7})}


def test_file_missing_warns_and_unrestricts(caplog, tmp_path) -> None:
    config = Config.from_env(
        {
            "MATRIMONY_ALLOWED_CHANNELS_FILE": str(
                tmp_path / "does-not-exist.json"
            )
        }
    )
    assert config.allowed_channels == {}
    assert "MATRIMONY_ALLOWED_CHANNELS_FILE" in caplog.text


def test_inline_beats_file(tmp_path) -> None:
    path = tmp_path / "channels.json"
    path.write_text('{"42": ["7"]}')
    config = Config.from_env(
        {
            "MATRIMONY_ALLOWED_CHANNELS": '{"1": ["2"]}',
            "MATRIMONY_ALLOWED_CHANNELS_FILE": str(path),
        }
    )
    assert config.allowed_channels == {1: frozenset({2})}


# ---------------------------------------------------------------------------
# Dispatch gate
# ---------------------------------------------------------------------------


def test_command_in_allowed_channel_dispatches() -> None:
    bot = make_bot(allowed_channels={42: frozenset({7})})
    send = stub_send(bot)
    msg = wire_message(bot, user(1), channel_id=7)
    run(bot.process_commands(msg))
    send.assert_awaited_once()


def test_command_in_disallowed_channel_ignored() -> None:
    bot = make_bot(allowed_channels={42: frozenset({7})})
    send = stub_send(bot)
    msg = wire_message(bot, user(1), channel_id=8)
    run(bot.process_commands(msg))
    send.assert_not_awaited()


def test_unlisted_guild_unrestricted() -> None:
    bot = make_bot(allowed_channels={99: frozenset({7})})
    send = stub_send(bot)
    msg = wire_message(bot, user(1), guild_id=42, channel_id=1)
    run(bot.process_commands(msg))
    send.assert_awaited_once()


def test_empty_allow_list_blocks_guild() -> None:
    bot = make_bot(allowed_channels={42: frozenset()})
    send = stub_send(bot)
    msg = wire_message(bot, user(1), channel_id=7)
    run(bot.process_commands(msg))
    send.assert_not_awaited()


def test_dms_never_restricted() -> None:
    bot = make_bot(allowed_channels={42: frozenset({7})})
    send = stub_send(bot)
    msg = wire_message(bot, user(1), guild_id=None)
    run(bot.process_commands(msg))
    send.assert_awaited_once()


def test_restriction_via_env_end_to_end() -> None:
    config = Config.from_env(
        {
            "MATRIMONY_DB_PATH": ":memory:",
            "MATRIMONY_ALLOWED_CHANNELS": '{"42": ["7"]}',
        }
    )
    bot = MatrimonyBot(config)
    MatrCog(bot)
    bot._connection.user = SimpleNamespace(id=BOT_USER_ID)  # type: ignore[attr-defined]
    send = stub_send(bot)
    run(bot.process_commands(wire_message(bot, user(1), channel_id=7)))
    send.assert_awaited_once()
    send.reset_mock()
    run(bot.process_commands(wire_message(bot, user(1), channel_id=8)))
    send.assert_not_awaited()
