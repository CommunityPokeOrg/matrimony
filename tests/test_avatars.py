"""Tests for the avatar fetch/cache layer - Discord-free, like test_family."""

import asyncio
import base64

from matrimony.avatars import (
    AVATAR_FETCH_LIMIT,
    AVATAR_MAX_BYTES,
    AVATAR_PX,
    MISS,
    AvatarCache,
    avatar_map,
)


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


def uri(data: bytes = b"\x89PNG") -> str:
    return "data:image/png;base64," + base64.b64encode(data).decode()


class FakeAsset:
    """Stand-in for ``discord.Asset`` (``display_avatar.replace(...).read()``)."""

    def __init__(self, data: bytes = b"\x89PNG", exc: Exception | None = None) -> None:
        self.data = data
        self.exc = exc
        self.reads = 0
        self.replaces: list[tuple[int, str]] = []

    def replace(self, *, size: int, static_format: str):
        self.replaces.append((size, static_format))
        return self

    async def read(self) -> bytes:
        self.reads += 1
        if self.exc is not None:
            raise self.exc
        return self.data


class FakeUser:
    """Stand-in for ``discord.User`` / ``discord.Member``."""

    def __init__(self, uid: int, asset: FakeAsset | None = None) -> None:
        self.id = uid
        self.display_avatar = asset or FakeAsset()


class FakeGuild:
    """Stand-in for ``discord.Guild``; only the member cache is modelled."""

    def __init__(self, members: dict[int, FakeUser] | None = None) -> None:
        self._members = members or {}

    def get_member(self, uid: int) -> FakeUser | None:
        return self._members.get(uid)


class FakeBot:
    """Stand-in for ``MatrimonyBot``'s user cache + REST fetch."""

    def __init__(
        self,
        users: dict[int, FakeUser] | None = None,
        fetchable: dict[int, FakeUser] | None = None,
    ) -> None:
        self._users = users or {}
        self._fetchable = fetchable if fetchable is not None else self._users
        self.fetched: list[int] = []
        self.fetch_exc: Exception | None = None

    def get_user(self, uid: int) -> FakeUser | None:
        return self._users.get(uid)

    async def fetch_user(self, uid: int) -> FakeUser:
        self.fetched.append(uid)
        if self.fetch_exc is not None:
            raise self.fetch_exc
        if uid not in self._fetchable:
            raise OSError("unknown user")
        return self._fetchable[uid]


def member_bot(uids: list[int]) -> tuple[FakeBot, FakeGuild]:
    users = {uid: FakeUser(uid) for uid in uids}
    return FakeBot(users), FakeGuild(users)


class TestCacheMiss:
    def test_member_avatar_fetched_and_cached(self) -> None:
        bot, guild = member_bot([1])
        cache = AvatarCache()
        out = run(avatar_map(bot, guild, [1], cache))
        assert out == {1: uri()}
        assert guild.get_member(1).display_avatar.reads == 1
        # Second render reuses the cache - no new download.
        out = run(avatar_map(bot, guild, [1], cache))
        assert out == {1: uri()}
        assert guild.get_member(1).display_avatar.reads == 1

    def test_guild_member_preferred_over_rest_fetch(self) -> None:
        bot, guild = member_bot([1])
        run(avatar_map(bot, guild, [1], AvatarCache()))
        assert bot.fetched == []

    def test_avatar_requested_at_64px_png(self) -> None:
        bot, guild = member_bot([1])
        run(avatar_map(bot, guild, [1], AvatarCache()))
        asset = guild.get_member(1).display_avatar
        assert asset.replaces == [(AVATAR_PX, "png")]


class TestResolutionOrder:
    def test_user_not_in_guild_cache_uses_fetch_user(self) -> None:
        # Family graphs can name users outside the guild (or simply uncached
        # members); their global avatar still renders via the REST fallback.
        user = FakeUser(7)
        bot = FakeBot(fetchable={7: user})
        out = run(avatar_map(bot, FakeGuild(), [7], AvatarCache()))
        assert bot.fetched == [7]
        assert out == {7: uri()}

    def test_bot_user_cache_preferred_over_rest_fetch(self) -> None:
        bot, _ = member_bot([2])
        out = run(avatar_map(bot, None, [2], AvatarCache()))
        assert bot.fetched == []
        assert out == {2: uri()}

    def test_no_guild_still_resolves(self) -> None:
        bot, _ = member_bot([3])
        out = run(avatar_map(bot, None, [3], AvatarCache()))
        assert out == {3: uri()}


class TestFailures:
    def test_read_error_falls_back_to_initial_disc(self) -> None:
        asset = FakeAsset(exc=OSError("cdn down"))
        bot = FakeBot({1: FakeUser(1, asset)})
        guild = FakeGuild({1: FakeUser(1, asset)})
        out = run(avatar_map(bot, guild, [1], AvatarCache()))
        # No data URI means the node renders the initial-letter disc.
        assert out == {}

    def test_unknown_user_falls_back(self) -> None:
        bot = FakeBot()
        out = run(avatar_map(bot, FakeGuild(), [99], AvatarCache()))
        assert out == {}
        assert bot.fetched == [99]

    def test_failures_are_cached_briefly(self) -> None:
        asset = FakeAsset(exc=OSError("cdn down"))
        bot = FakeBot({1: FakeUser(1, asset)})
        guild = FakeGuild({1: FakeUser(1, asset)})
        cache = AvatarCache()
        run(avatar_map(bot, guild, [1], cache))
        assert cache.lookup(1) is None
        run(avatar_map(bot, guild, [1], cache))
        assert asset.reads == 1

    def test_empty_download_is_not_cached_as_success(self) -> None:
        asset = FakeAsset(data=b"")
        bot = FakeBot({1: FakeUser(1, asset)})
        guild = FakeGuild({1: FakeUser(1, asset)})
        cache = AvatarCache()
        out = run(avatar_map(bot, guild, [1], cache))
        assert out == {}
        assert cache.lookup(1) is None


class TestBounds:
    def test_oversized_image_dropped(self) -> None:
        big = FakeAsset(data=b"x" * (AVATAR_MAX_BYTES + 1))
        bot = FakeBot({1: FakeUser(1, big)})
        guild = FakeGuild({1: FakeUser(1, big)})
        out = run(avatar_map(bot, guild, [1], AvatarCache()))
        assert out == {}

    def test_exactly_max_bytes_kept(self) -> None:
        asset = FakeAsset(data=b"x" * AVATAR_MAX_BYTES)
        bot = FakeBot({1: FakeUser(1, asset)})
        guild = FakeGuild({1: FakeUser(1, asset)})
        out = run(avatar_map(bot, guild, [1], AvatarCache()))
        assert out == {1: uri(b"x" * AVATAR_MAX_BYTES)}

    def test_fetch_list_capped(self) -> None:
        uids = list(range(1, AVATAR_FETCH_LIMIT + 11))
        bot, guild = member_bot(uids)
        out = run(avatar_map(bot, guild, uids, AvatarCache()))
        assert len(out) == AVATAR_FETCH_LIMIT
        assert set(out) == set(uids[:AVATAR_FETCH_LIMIT])

    def test_cache_bounded(self) -> None:
        cache = AvatarCache(max_entries=3)
        for uid in range(1, 5):
            cache.store(uid, uri())
        assert len(cache) == 3
        assert cache.lookup(1) is MISS  # oldest evicted
        assert cache.lookup(4) == uri()

    def test_lookup_refreshes_recency(self) -> None:
        cache = AvatarCache(max_entries=2)
        cache.store(1, uri())
        cache.store(2, uri())
        assert cache.lookup(1) == uri()  # 1 is now newest
        cache.store(3, uri())
        assert cache.lookup(2) is MISS
        assert cache.lookup(1) == uri()


class TestTTL:
    def test_expired_entry_refetches(self) -> None:
        t = [0.0]
        cache = AvatarCache(ttl=100.0, now=lambda: t[0])
        bot, guild = member_bot([1])
        run(avatar_map(bot, guild, [1], cache))
        t[0] = 101.0
        assert cache.lookup(1) is MISS
        run(avatar_map(bot, guild, [1], cache))
        assert guild.get_member(1).display_avatar.reads == 2

    def test_failure_ttl_shorter_than_hit_ttl(self) -> None:
        t = [0.0]
        cache = AvatarCache(ttl=1000.0, failure_ttl=10.0, now=lambda: t[0])
        cache.store(1, uri())
        cache.store(2, None)
        t[0] = 500.0
        assert cache.lookup(1) == uri()
        assert cache.lookup(2) is MISS
