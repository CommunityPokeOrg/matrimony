"""Avatar fetching and caching for the family-tree renderer.

Tree images inline avatars as base64 ``data:`` URIs so the rendered document
stays self-contained - a remote ``http`` reference would need resolving by
whatever rasterizes or displays it. This module fetches those bytes with
bounded size and concurrency, and caches them per user id so repeated
``tree`` / ``fulltree`` renders do not hit Discord's CDN again.

Fetching prefers the guild member cache (``display_avatar`` picks up server
avatars); users missing from it - not in this server, or simply uncached -
are resolved through ``bot.fetch_user`` so their global avatar still
renders.
"""

from __future__ import annotations

import asyncio
import base64
import time
from collections import OrderedDict
from collections.abc import Callable

import discord

# A 64px PNG per person, fetched with bounded concurrency and only for the
# first few dozen nodes, so a huge tree cannot turn into a hundred HTTP
# requests before the image is even built.
AVATAR_PX = 64
AVATAR_FETCH_LIMIT = 60
AVATAR_CONCURRENCY = 8
AVATAR_MAX_BYTES = 32 * 1024

# Cache sizing: comfortably covers a busy server's trees; entries are
# evicted oldest-first and avatars change rarely, so a long TTL is fine.
# Failed lookups are remembered for much less - a user may upload a PFP at
# any moment, and a transient CDN error should not be sticky.
AVATAR_CACHE_MAX = 512
AVATAR_TTL = 3600.0
AVATAR_FAILURE_TTL = 300.0


class _Miss:
    """Sentinel returned by ``AvatarCache.lookup`` for uncached ids."""


MISS = _Miss()


class AvatarCache:
    """Bounded TTL cache mapping user ids to avatar ``data:`` URIs.

    ``lookup`` returns the cached ``data:`` URI, ``None`` for a remembered
    failure (also cached, but for ``failure_ttl`` instead of ``ttl``), or
    ``MISS`` when the id is not cached. Entries are re-inserted on hit and
    evicted oldest-first past ``max_entries`` (LRU). ``now`` is injectable
    so tests can travel through time.
    """

    def __init__(
        self,
        *,
        ttl: float = AVATAR_TTL,
        failure_ttl: float = AVATAR_FAILURE_TTL,
        max_entries: int = AVATAR_CACHE_MAX,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl
        self._failure_ttl = failure_ttl
        self._max_entries = max_entries
        self._now = now
        self._entries: OrderedDict[int, tuple[float, str | None]] = OrderedDict()

    def lookup(self, uid: int) -> str | None | _Miss:
        """Cached URI, ``None`` (remembered failure), or ``MISS``."""
        entry = self._entries.pop(uid, None)
        if entry is None:
            return MISS
        expires, uri = entry
        if expires <= self._now():
            return MISS
        self._entries[uid] = entry
        return uri

    def store(self, uid: int, uri: str | None) -> None:
        """Cache a fetched URI, or ``None`` to remember a failed fetch."""
        ttl = self._ttl if uri is not None else self._failure_ttl
        self._entries.pop(uid, None)
        self._entries[uid] = (self._now() + ttl, uri)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    def __len__(self) -> int:
        return len(self._entries)


async def avatar_map(
    bot: discord.Client,
    guild: discord.Guild | None,
    ids: list[int],
    cache: AvatarCache,
) -> dict[int, str]:
    """Resolve each user id to a ``data:`` URI, using and filling ``cache``.

    Anything that fails to fetch - unknown user, HTTP error, oversized
    image - is left out of the result, and the tree node falls back to an
    initial disc.
    """
    out: dict[int, str] = {}
    todo: list[int] = []
    for uid in ids[:AVATAR_FETCH_LIMIT]:
        if uid in out or uid in todo:
            continue
        cached = cache.lookup(uid)
        if cached is MISS:
            todo.append(uid)
        elif cached is not None:
            out[uid] = cached
    if not todo:
        return out

    limit = asyncio.Semaphore(AVATAR_CONCURRENCY)

    async def one(uid: int) -> None:
        async with limit:
            uri = await _fetch_avatar(bot, guild, uid)
        cache.store(uid, uri)
        if uri is not None:
            out[uid] = uri

    await asyncio.gather(*(one(uid) for uid in todo))
    return out


async def _fetch_avatar(
    bot: discord.Client, guild: discord.Guild | None, uid: int
) -> str | None:
    """Download ``uid``'s 64px avatar as a ``data:`` URI, or ``None``.

    Resolution order: guild member cache (server avatar), the bot's user
    cache, then a REST fetch - the last of which also covers users who are
    not in this guild at all.
    """
    user = guild.get_member(uid) if guild is not None else None
    if user is None:
        user = bot.get_user(uid)
    if user is None:
        try:
            user = await bot.fetch_user(uid)
        except (discord.HTTPException, OSError):
            return None
    try:
        data = await user.display_avatar.replace(
            size=AVATAR_PX, static_format="png"
        ).read()
    except (discord.HTTPException, OSError):
        return None
    if not data or len(data) > AVATAR_MAX_BYTES:
        return None
    return "data:image/png;base64," + base64.b64encode(data).decode()
