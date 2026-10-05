"""Fluxpoint GIF client and GIF attachments on the action commands.

The client's HTTP layer is a fake session injected in place of aiohttp, and
command tests stub ``bot.gifs.fetch_url`` - no real network traffic.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from matrimony.bot import MatrimonyBot
from matrimony.cogs import matr as matr_mod
from matrimony.cogs.matr import MatrCog
from matrimony.config import DEFAULT_FLUXPOINT_API_KEY, Config
from matrimony.gifs import GIF_TYPES, FluxpointClient

GIF_URL = "https://img.fluxpoint.dev/123.gif"
PAYLOAD = {
    "success": True,
    "code": 200,
    "message": "",
    "id": "123",
    "file": GIF_URL,
}


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Fake aiohttp session/response
# ---------------------------------------------------------------------------


class FakeResp:
    def __init__(self, status: int = 200, data=None, json_error=None):
        self.status = status
        self._data = PAYLOAD if data is None else data
        self._json_error = json_error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def json(self, content_type=None):
        if self._json_error is not None:
            raise self._json_error
        return self._data


class FakeSession:
    """Duck-typed stand-in for aiohttp.ClientSession."""

    closed = False

    def __init__(self, resp=None, exc=None):
        self._resp = resp or FakeResp()
        self._exc = exc
        self.requests = []

    def get(self, url, headers=None, timeout=None):
        self.requests.append((url, headers))
        if self._exc is not None:
            raise self._exc
        return self._resp


def make_bot(config: Config | None = None) -> MatrimonyBot:
    bot = MatrimonyBot(config or Config(database_path=":memory:"))
    MatrCog(bot)
    return bot


def user(uid: int):
    return SimpleNamespace(
        id=uid,
        bot=False,
        name=f"user{uid}",
        display_name=f"user{uid}",
        mention=f"<@{uid}>",
        guild_permissions=SimpleNamespace(manage_guild=False),
    )


def ctx_for(bot: MatrimonyBot, author):
    return SimpleNamespace(
        bot=bot,
        author=author,
        guild=SimpleNamespace(id=42, get_member=lambda uid: None),
        channel=SimpleNamespace(id=7),
        prefix="!",
        reply=AsyncMock(),
        command=None,
    )


def last_embed(ctx) -> object:
    return ctx.reply.await_args.kwargs["embed"]


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def test_default_fluxpoint_key() -> None:
    assert Config().fluxpoint_api_key == DEFAULT_FLUXPOINT_API_KEY


def test_fluxpoint_key_env_override() -> None:
    cfg = Config.from_env({"FLUXPOINT_API_KEY": "FP-test-abc"})
    assert cfg.fluxpoint_api_key == "FP-test-abc"


def test_fluxpoint_key_env_empty_disables() -> None:
    cfg = Config.from_env({"FLUXPOINT_API_KEY": ""})
    assert cfg.fluxpoint_api_key == ""


# ---------------------------------------------------------------------------
# FluxpointClient.fetch_url
# ---------------------------------------------------------------------------


def test_fetch_url_success() -> None:
    session = FakeSession()
    client = FluxpointClient("KEY", session=session)
    assert run(client.fetch_url("hug")) == GIF_URL
    url, headers = session.requests[0]
    assert url == "https://api.fluxpoint.dev/sfw/gif/hug"
    assert headers["Authorization"] == "KEY"


def test_fetch_url_no_key_makes_no_request() -> None:
    session = FakeSession()
    client = FluxpointClient("", session=session)
    assert run(client.fetch_url("hug")) is None
    assert session.requests == []


def test_fetch_url_http_error() -> None:
    client = FluxpointClient("KEY", session=FakeSession(resp=FakeResp(500)))
    assert run(client.fetch_url("hug")) is None


def test_fetch_url_timeout() -> None:
    client = FluxpointClient(
        "KEY", session=FakeSession(exc=asyncio.TimeoutError())
    )
    assert run(client.fetch_url("hug")) is None


def test_fetch_url_bad_json() -> None:
    resp = FakeResp(json_error=ValueError("not json"))
    client = FluxpointClient("KEY", session=FakeSession(resp=resp))
    assert run(client.fetch_url("hug")) is None


def test_fetch_url_non_dict_payload() -> None:
    client = FluxpointClient("KEY", session=FakeSession(resp=FakeResp(data=[])))
    assert run(client.fetch_url("hug")) is None


def test_fetch_url_unsuccessful_payload() -> None:
    resp = FakeResp(data={"success": False, "code": 403, "message": "denied"})
    client = FluxpointClient("KEY", session=FakeSession(resp=resp))
    assert run(client.fetch_url("hug")) is None


def test_fetch_url_missing_file_field() -> None:
    resp = FakeResp(data={"success": True, "code": 200, "message": "", "id": "1"})
    client = FluxpointClient("KEY", session=FakeSession(resp=resp))
    assert run(client.fetch_url("hug")) is None


# ---------------------------------------------------------------------------
# GIFs attached to action commands
# ---------------------------------------------------------------------------


def stub_gifs(bot: MatrimonyBot, url: str | None = GIF_URL) -> AsyncMock:
    bot.gifs.fetch_url = AsyncMock(return_value=url)  # type: ignore[method-assign]
    return bot.gifs.fetch_url


def test_fun_command_embeds_gif() -> None:
    bot = make_bot()
    fetch = stub_gifs(bot)
    ctx = ctx_for(bot, user(1))
    hug = next(c for c in matr_mod.matr.commands if c.name == "hug")
    run(hug.callback(ctx, user(2)))
    fetch.assert_awaited_once_with("hug")
    assert last_embed(ctx).image.url == GIF_URL


def test_stab_uses_punch_endpoint() -> None:
    """Fluxpoint has no 'stab' GIF - the punch endpoint is the mapped fit."""
    bot = make_bot()
    fetch = stub_gifs(bot)
    ctx = ctx_for(bot, user(1))
    stab = next(c for c in matr_mod.matr.commands if c.name == "stab")
    run(stab.callback(ctx, user(2)))
    fetch.assert_awaited_once_with("punch")
    assert last_embed(ctx).image.url == GIF_URL


def test_fun_command_works_when_gif_unavailable() -> None:
    """A failed fetch must not break the action: reply still goes out,
    just without an image."""
    bot = make_bot()
    stub_gifs(bot, url=None)
    ctx = ctx_for(bot, user(1))
    kiss = next(c for c in matr_mod.matr.commands if c.name == "kiss")
    run(kiss.callback(ctx, user(2)))
    emb = last_embed(ctx)
    assert emb.image.url is None
    assert "kisses" in emb.description


def test_ship_attaches_gif() -> None:
    bot = make_bot()
    fetch = stub_gifs(bot)
    ctx = ctx_for(bot, user(1))
    run(matr_mod.matr_ship.callback(ctx, user(2), user(3)))
    fetch.assert_awaited_once_with("handhold")
    assert last_embed(ctx).image.url == GIF_URL


def test_marriage_completion_attaches_gif() -> None:
    bot = make_bot()
    fetch = stub_gifs(bot)
    a, b = user(10), user(11)
    run(matr_mod.matr_marry.callback(ctx_for(bot, a), b))
    ctx_b = ctx_for(bot, b)
    run(matr_mod.matr_accept.callback(ctx_b, None))
    fetch.assert_awaited_with("kiss")
    assert last_embed(ctx_b).image.url == GIF_URL


def test_divorce_attaches_gif() -> None:
    bot = make_bot()
    fetch = stub_gifs(bot)
    a, b = user(20), user(21)
    run(matr_mod.matr_marry.callback(ctx_for(bot, a), b))
    run(matr_mod.matr_accept.callback(ctx_for(bot, b), None))
    ctx_a = ctx_for(bot, a)
    run(matr_mod.matr_divorce.callback(ctx_a, b))
    fetch.assert_awaited_with("cry")
    assert last_embed(ctx_a).image.url == GIF_URL


def test_proposal_still_works_when_gif_unavailable() -> None:
    bot = make_bot()
    stub_gifs(bot, url=None)
    a, b = user(30), user(31)
    run(matr_mod.matr_marry.callback(ctx_for(bot, a), b))
    ctx_b = ctx_for(bot, b)
    run(matr_mod.matr_accept.callback(ctx_b, None))
    assert bot.store.partners_of(a.id) == [b.id]
    assert last_embed(ctx_b).image.url is None


# ---------------------------------------------------------------------------
# Action command coverage
# ---------------------------------------------------------------------------


def test_fun_commands_all_registered() -> None:
    """Every entry in _FUN_VERBS becomes a real ``matr`` subcommand."""
    names = {c.name for c in matr_mod.matr.commands}
    assert set(matr_mod._FUN_VERBS) <= names


def test_fun_gif_types_are_documented_endpoints() -> None:
    """Every command's GIF type must be a real Fluxpoint endpoint - a typo
    here would silently produce GIF-less replies in production."""
    for name, (_, _, gif_type) in matr_mod._FUN_VERBS.items():
        assert gif_type in GIF_TYPES, name


def test_every_fun_command_fetches_and_embeds_its_gif() -> None:
    """Each action command hits its mapped endpoint and embeds the URL."""
    for name, (verb, _, gif_type) in matr_mod._FUN_VERBS.items():
        bot = make_bot()
        fetch = stub_gifs(bot)
        ctx = ctx_for(bot, user(1))
        cmd = next(c for c in matr_mod.matr.commands if c.name == name)
        run(cmd.callback(ctx, user(2)))
        fetch.assert_awaited_once_with(gif_type)
        embed = last_embed(ctx)
        assert embed.image.url == GIF_URL, name
        assert verb in embed.description, name
