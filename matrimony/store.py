"""SQLite storage layer for Matrimony.

Family relationships are *global* (cross-server), matching the original
MarriageBot design where family trees span every guild the bot is in.
Guild-scoped data is limited to per-guild settings (prefix, incest toggle),
the guild/channel a proposal was made in, and partner notices - the
"your partner married someone new" alerts existing partners can accept
(acknowledge) or answer with a divorce.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass

SCHEMA = """
CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id     INTEGER PRIMARY KEY,
    prefix       TEXT,
    allow_incest INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS partners (
    user_a    INTEGER NOT NULL,
    user_b    INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (user_a, user_b),
    CHECK (user_a < user_b)
);

CREATE TABLE IF NOT EXISTS children (
    child_id   INTEGER PRIMARY KEY,
    parent_id  INTEGER NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS proposals (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id   INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    proposer   INTEGER NOT NULL,
    target     INTEGER NOT NULL,
    kind       TEXT NOT NULL CHECK (kind IN ('marry', 'adopt', 'makeparent')),
    jail       INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    UNIQUE (proposer, target, kind)
);

CREATE TABLE IF NOT EXISTS blocks (
    blocker INTEGER NOT NULL,
    blocked INTEGER NOT NULL,
    PRIMARY KEY (blocker, blocked)
);

CREATE TABLE IF NOT EXISTS notices (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id   INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    user_id    INTEGER NOT NULL,
    spouse_id  INTEGER NOT NULL,
    other_id   INTEGER NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS restraining_orders (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id   INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    protected  INTEGER NOT NULL,
    restrained INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    UNIQUE (protected, restrained)
);

CREATE TABLE IF NOT EXISTS jail_sentences (
    inmate     INTEGER PRIMARY KEY,
    guild_id   INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    action     TEXT NOT NULL,
    protected  INTEGER NOT NULL,
    jailed_at  INTEGER NOT NULL,
    release_at INTEGER NOT NULL
);

-- Jail relationships are deliberately kept out of the permanent
-- partners/children tables: they are ephemeral and never survive a
-- release (see store.release_inmate).
CREATE TABLE IF NOT EXISTS jail_partners (
    user_a    INTEGER NOT NULL,
    user_b    INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (user_a, user_b),
    CHECK (user_a < user_b)
);

CREATE TABLE IF NOT EXISTS jail_children (
    child_id   INTEGER PRIMARY KEY,
    parent_id  INTEGER NOT NULL,
    created_at INTEGER NOT NULL
);
"""


@dataclass(frozen=True)
class Proposal:
    id: int
    guild_id: int
    channel_id: int
    proposer: int
    target: int
    kind: str  # 'marry' | 'adopt' | 'makeparent'
    jail: bool  # proposed between two inmates; enacts jail relationships
    created_at: int
    expires_at: int


@dataclass(frozen=True)
class RestrainingOrder:
    """A one-hour order stopping ``restrained`` from targeting
    ``protected`` with proposals and fun actions. ``channel_id`` is the
    channel it was filed in, used to announce its expiry."""

    id: int
    guild_id: int
    channel_id: int
    protected: int
    restrained: int
    created_at: int
    expires_at: int


@dataclass(frozen=True)
class JailSentence:
    """A custodial sentence for violating a restraining order.

    ``action`` is the attempted command that triggered it (drives the
    sentence length); ``protected`` is who pressed charges;
    ``channel_id`` is where the violation happened, reused for the
    release announcement."""

    inmate: int
    guild_id: int
    channel_id: int
    action: str
    protected: int
    jailed_at: int
    release_at: int


@dataclass(frozen=True)
class ReleaseResult:
    """Everything a release dissolved, for notifications.

    ``divorced`` are the inmate's jail partners; ``children_lost`` are
    jail children whose jail parent was released; ``parent_lost`` is the
    inmate's own jail parent, if any."""

    sentence: JailSentence
    divorced: list[int]
    children_lost: list[int]
    parent_lost: int | None


@dataclass(frozen=True)
class Notice:
    """A "your partner married someone new" notification.

    ``user_id`` is the existing partner being told; ``spouse_id`` is their
    partner who just formed another marriage; ``other_id`` is the new
    spouse. Notices never block anything: accepting simply acknowledges
    the arrangement, and the divorce option dissolves ``user_id``'s own
    marriage to ``spouse_id``.
    """

    id: int
    guild_id: int
    channel_id: int
    user_id: int
    spouse_id: int
    other_id: int
    created_at: int


class Store:
    """Synchronous SQLite store. All operations are sub-millisecond local
    queries; the cog layer may wrap them in ``asyncio.to_thread`` if desired,
    but for a bot of this scale direct calls are fine."""

    def __init__(self, path: str = ":memory:") -> None:
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._migrate()

    def _migrate(self) -> None:
        """Add columns introduced after the first schema version.

        ``CREATE TABLE IF NOT EXISTS`` leaves existing tables alone, so
        the ``proposals.jail`` flag (added for jail relationships) is
        back-filled here for databases created before it existed."""
        cols = {r[1] for r in self._rows("PRAGMA table_info(proposals)")}
        if "jail" not in cols:
            self._conn.execute(
                "ALTER TABLE proposals ADD COLUMN jail "
                "INTEGER NOT NULL DEFAULT 0"
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ------------------------------------------------------------------ util

    def _row(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        with self._lock:
            cur = self._conn.execute(sql, params)
            return cur.fetchone()

    def _rows(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            cur = self._conn.execute(sql, params)
            return cur.fetchall()

    def _exec(self, sql: str, params: tuple = ()) -> None:
        with self._lock:
            self._conn.execute(sql, params)
            self._conn.commit()

    # --------------------------------------------------------- guild settings

    def get_prefix(self, guild_id: int) -> str | None:
        row = self._row(
            "SELECT prefix FROM guild_settings WHERE guild_id = ?", (guild_id,)
        )
        return row[0] if row and row[0] else None

    def set_prefix(self, guild_id: int, prefix: str | None) -> None:
        self._exec(
            """INSERT INTO guild_settings (guild_id, prefix, allow_incest)
               VALUES (?, ?, 0)
               ON CONFLICT(guild_id) DO UPDATE SET prefix = excluded.prefix""",
            (guild_id, prefix),
        )

    def get_allow_incest(self, guild_id: int) -> bool:
        row = self._row(
            "SELECT allow_incest FROM guild_settings WHERE guild_id = ?",
            (guild_id,),
        )
        return bool(row[0]) if row else False

    def set_allow_incest(self, guild_id: int, allow: bool) -> None:
        self._exec(
            """INSERT INTO guild_settings (guild_id, prefix, allow_incest)
               VALUES (?, NULL, ?)
               ON CONFLICT(guild_id) DO UPDATE SET
                   allow_incest = excluded.allow_incest""",
            (guild_id, int(allow)),
        )

    # ------------------------------------------------------------- partners

    def add_partners(self, user_x: int, user_y: int) -> None:
        a, b = sorted((user_x, user_y))
        self._exec(
            "INSERT OR IGNORE INTO partners (user_a, user_b, created_at) "
            "VALUES (?, ?, ?)",
            (a, b, int(time.time())),
        )

    def remove_partners(self, user_x: int, user_y: int) -> bool:
        a, b = sorted((user_x, user_y))
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM partners WHERE user_a = ? AND user_b = ?", (a, b)
            )
            # Notices that presume this marriage still exists are now stale.
            self._conn.execute(
                "DELETE FROM notices WHERE (user_id = ? AND spouse_id = ?) "
                "OR (user_id = ? AND spouse_id = ?)",
                (user_x, user_y, user_y, user_x),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def partnership_since(self, user_x: int, user_y: int) -> int | None:
        """Unix timestamp the pair married, or None if not partners."""
        a, b = sorted((user_x, user_y))
        row = self._row(
            "SELECT created_at FROM partners WHERE user_a = ? AND user_b = ?",
            (a, b),
        )
        return row[0] if row else None

    def partners_of(self, user_id: int) -> list[int]:
        rows = self._rows(
            "SELECT user_a, user_b FROM partners WHERE user_a = ? OR user_b = ?",
            (user_id, user_id),
        )
        return [r[1] if r[0] == user_id else r[0] for r in rows]

    def all_partner_edges(self) -> list[tuple[int, int]]:
        return [tuple(r) for r in self._rows("SELECT user_a, user_b FROM partners")]

    # ------------------------------------------------------------- children

    def add_child(self, parent_id: int, child_id: int) -> bool:
        """Attach ``child_id`` under ``parent_id``. One parent per child
        (as in the original MarriageBot). Returns False if the child already
        has a parent."""
        with self._lock:
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO children (child_id, parent_id, created_at) "
                "VALUES (?, ?, ?)",
                (child_id, parent_id, int(time.time())),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def remove_child(self, child_id: int) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM children WHERE child_id = ?", (child_id,)
            )
            self._conn.commit()
            return cur.rowcount > 0

    def parent_of(self, child_id: int) -> int | None:
        row = self._row(
            "SELECT parent_id FROM children WHERE child_id = ?", (child_id,)
        )
        return row[0] if row else None

    def children_of(self, parent_id: int) -> list[int]:
        return [
            r[0]
            for r in self._rows(
                "SELECT child_id FROM children WHERE parent_id = ?", (parent_id,)
            )
        ]

    # ------------------------------------------------------------- proposals

    def create_proposal(
        self,
        guild_id: int,
        channel_id: int,
        proposer: int,
        target: int,
        kind: str,
        ttl_seconds: int,
        *,
        jail: bool = False,
    ) -> Proposal | None:
        """Create a proposal. Returns None if an identical open one exists."""
        now = int(time.time())
        self.expire_proposals(now)
        with self._lock:
            existing = self._row(
                "SELECT id FROM proposals WHERE proposer = ? AND target = ? "
                "AND kind = ? AND jail = ?",
                (proposer, target, kind, int(jail)),
            )
            if existing:
                return None
            cur = self._conn.execute(
                """INSERT INTO proposals
                   (guild_id, channel_id, proposer, target, kind, jail,
                    created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (guild_id, channel_id, proposer, target, kind, int(jail),
                 now, now + ttl_seconds),
            )
            self._conn.commit()
            pid = cur.lastrowid
        return Proposal(pid, guild_id, channel_id, proposer, target, kind,
                        jail, now, now + ttl_seconds)

    _PROPOSAL_COLS = (
        "id, guild_id, channel_id, proposer, target, kind, jail, "
        "created_at, expires_at"
    )

    def get_proposal(self, proposal_id: int) -> Proposal | None:
        row = self._row(
            f"SELECT {self._PROPOSAL_COLS} FROM proposals WHERE id = ?",
            (proposal_id,),
        )
        return Proposal(*row) if row else None

    def proposals_for(self, target: int, kind: str | None = None) -> list[Proposal]:
        self.expire_proposals()
        if kind is None:
            rows = self._rows(
                f"SELECT {self._PROPOSAL_COLS} FROM proposals WHERE target = ?",
                (target,),
            )
        else:
            rows = self._rows(
                f"SELECT {self._PROPOSAL_COLS} FROM proposals WHERE target = ? "
                "AND kind = ?",
                (target, kind),
            )
        return [Proposal(*r) for r in rows]

    def delete_proposal(self, proposal_id: int) -> None:
        self._exec("DELETE FROM proposals WHERE id = ?", (proposal_id,))

    def expire_proposals(self, now: int | None = None) -> int:
        now = int(time.time()) if now is None else now
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM proposals WHERE expires_at <= ?", (now,)
            )
            self._conn.commit()
            return cur.rowcount

    # --------------------------------------------------------------- notices

    def create_notice(
        self,
        guild_id: int,
        channel_id: int,
        user_id: int,
        spouse_id: int,
        other_id: int,
    ) -> Notice:
        now = int(time.time())
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO notices
                   (guild_id, channel_id, user_id, spouse_id, other_id,
                    created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (guild_id, channel_id, user_id, spouse_id, other_id, now),
            )
            self._conn.commit()
            nid = cur.lastrowid
        return Notice(nid, guild_id, channel_id, user_id, spouse_id,
                      other_id, now)

    def get_notice(self, notice_id: int) -> Notice | None:
        row = self._row(
            "SELECT id, guild_id, channel_id, user_id, spouse_id, other_id, "
            "created_at FROM notices WHERE id = ?",
            (notice_id,),
        )
        return Notice(*row) if row else None

    def notices_for(self, user_id: int) -> list[Notice]:
        rows = self._rows(
            "SELECT id, guild_id, channel_id, user_id, spouse_id, other_id, "
            "created_at FROM notices WHERE user_id = ?",
            (user_id,),
        )
        return [Notice(*r) for r in rows]

    def delete_notice(self, notice_id: int) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM notices WHERE id = ?", (notice_id,)
            )
            self._conn.commit()
            return cur.rowcount > 0

    # ----------------------------------------------------------------- blocks

    def add_block(self, blocker: int, blocked: int) -> None:
        self._exec(
            "INSERT OR IGNORE INTO blocks (blocker, blocked) VALUES (?, ?)",
            (blocker, blocked),
        )

    def remove_block(self, blocker: int, blocked: int) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM blocks WHERE blocker = ? AND blocked = ?",
                (blocker, blocked),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def is_blocked(self, blocker: int, blocked: int) -> bool:
        return bool(
            self._row(
                "SELECT 1 FROM blocks WHERE blocker = ? AND blocked = ?",
                (blocker, blocked),
            )
        )

    def blocked_users(self, blocker: int) -> list[int]:
        return [
            r[0]
            for r in self._rows(
                "SELECT blocked FROM blocks WHERE blocker = ?", (blocker,)
            )
        ]

    # --------------------------------------------------- restraining orders

    _ORDER_COLS = (
        "id, guild_id, channel_id, protected, restrained, "
        "created_at, expires_at"
    )

    def file_restraining_order(
        self,
        guild_id: int,
        channel_id: int,
        protected: int,
        restrained: int,
        *,
        ttl_seconds: int,
        now: int | None = None,
    ) -> RestrainingOrder:
        """File (or renew) a restraining order. Re-filing an active order
        refreshes its expiry back to the full duration."""
        now = int(time.time()) if now is None else now
        expires_at = now + ttl_seconds
        with self._lock:
            self._conn.execute(
                """INSERT INTO restraining_orders
                   (guild_id, channel_id, protected, restrained,
                    created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(protected, restrained) DO UPDATE SET
                       guild_id = excluded.guild_id,
                       channel_id = excluded.channel_id,
                       expires_at = excluded.expires_at""",
                (guild_id, channel_id, protected, restrained,
                 now, expires_at),
            )
            self._conn.commit()
        row = self._row(
            f"SELECT {self._ORDER_COLS} FROM restraining_orders "
            "WHERE protected = ? AND restrained = ?",
            (protected, restrained),
        )
        return RestrainingOrder(*row)

    def restraining_order(
        self, protected: int, restrained: int, now: int | None = None
    ) -> RestrainingOrder | None:
        """The active order protecting ``protected`` from ``restrained``,
        or None (expired orders are pruned on read)."""
        now = int(time.time()) if now is None else now
        self.expire_restraining_orders(now)
        row = self._row(
            f"SELECT {self._ORDER_COLS} FROM restraining_orders "
            "WHERE protected = ? AND restrained = ?",
            (protected, restrained),
        )
        return RestrainingOrder(*row) if row else None

    def expire_restraining_orders(
        self, now: int | None = None
    ) -> list[RestrainingOrder]:
        """Delete orders past their expiry and return them (for the
        "order lapsed" announcements)."""
        now = int(time.time()) if now is None else now
        with self._lock:
            rows = self._rows(
                f"SELECT {self._ORDER_COLS} FROM restraining_orders "
                "WHERE expires_at <= ?",
                (now,),
            )
            self._conn.execute(
                "DELETE FROM restraining_orders WHERE expires_at <= ?", (now,)
            )
            self._conn.commit()
        return [RestrainingOrder(*r) for r in rows]

    # ----------------------------------------------------------------- jail

    def jail_inmate(
        self,
        inmate: int,
        guild_id: int,
        channel_id: int,
        action: str,
        protected: int,
        sentence_seconds: int,
        *,
        now: int | None = None,
    ) -> JailSentence:
        """Sentence ``inmate``. Re-jailing someone already inside restarts
        the clock from ``now`` for the new sentence."""
        now = int(time.time()) if now is None else now
        release_at = now + sentence_seconds
        self._exec(
            """INSERT INTO jail_sentences
               (inmate, guild_id, channel_id, action, protected,
                jailed_at, release_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(inmate) DO UPDATE SET
                   guild_id = excluded.guild_id,
                   channel_id = excluded.channel_id,
                   action = excluded.action,
                   protected = excluded.protected,
                   jailed_at = excluded.jailed_at,
                   release_at = excluded.release_at""",
            (inmate, guild_id, channel_id, action, protected,
             now, release_at),
        )
        return JailSentence(
            inmate, guild_id, channel_id, action, protected, now, release_at
        )

    _SENTENCE_COLS = (
        "inmate, guild_id, channel_id, action, protected, "
        "jailed_at, release_at"
    )

    def sentence_for(
        self, user_id: int, now: int | None = None
    ) -> JailSentence | None:
        """The active sentence for ``user_id``, or None. Expired-but-unswept
        sentences are treated as already served."""
        now = int(time.time()) if now is None else now
        row = self._row(
            f"SELECT {self._SENTENCE_COLS} FROM jail_sentences "
            "WHERE inmate = ? AND release_at > ?",
            (user_id, now),
        )
        return JailSentence(*row) if row else None

    def is_jailed(self, user_id: int, now: int | None = None) -> bool:
        return self.sentence_for(user_id, now) is not None

    def sentences_due(self, now: int | None = None) -> list[JailSentence]:
        """Sentences whose release time has passed, still awaiting the
        sweep that frees them."""
        now = int(time.time()) if now is None else now
        return [
            JailSentence(*r)
            for r in self._rows(
                f"SELECT {self._SENTENCE_COLS} FROM jail_sentences "
                "WHERE release_at <= ?",
                (now,),
            )
        ]

    # ----------------------------------------------------- jail relationships

    def add_jail_partners(self, user_x: int, user_y: int) -> None:
        a, b = sorted((user_x, user_y))
        self._exec(
            "INSERT OR IGNORE INTO jail_partners (user_a, user_b, created_at) "
            "VALUES (?, ?, ?)",
            (a, b, int(time.time())),
        )

    def jail_partners_of(self, user_id: int) -> list[int]:
        rows = self._rows(
            "SELECT user_a, user_b FROM jail_partners "
            "WHERE user_a = ? OR user_b = ?",
            (user_id, user_id),
        )
        return [r[1] if r[0] == user_id else r[0] for r in rows]

    def add_jail_child(self, parent_id: int, child_id: int) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO jail_children "
                "(child_id, parent_id, created_at) VALUES (?, ?, ?)",
                (child_id, parent_id, int(time.time())),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def jail_parent_of(self, child_id: int) -> int | None:
        row = self._row(
            "SELECT parent_id FROM jail_children WHERE child_id = ?",
            (child_id,),
        )
        return row[0] if row else None

    def jail_children_of(self, parent_id: int) -> list[int]:
        return [
            r[0]
            for r in self._rows(
                "SELECT child_id FROM jail_children WHERE parent_id = ?",
                (parent_id,),
            )
        ]

    def release_inmate(self, inmate: int) -> ReleaseResult | None:
        """Free ``inmate``: delete the sentence and dissolve every jail
        relationship they hold (jail marriages are divorced, jail
        adoptions abandoned in both directions). Returns what was
        dissolved so callers can notify, or None if they weren't inside."""
        with self._lock:
            row = self._row(
                f"SELECT {self._SENTENCE_COLS} FROM jail_sentences "
                "WHERE inmate = ?",
                (inmate,),
            )
            if row is None:
                return None
            sentence = JailSentence(*row)
            self._conn.execute(
                "DELETE FROM jail_sentences WHERE inmate = ?", (inmate,)
            )
            divorced = self.jail_partners_of(inmate)
            for partner in divorced:
                x, y = sorted((inmate, partner))
                self._conn.execute(
                    "DELETE FROM jail_partners WHERE user_a = ? AND user_b = ?",
                    (x, y),
                )
            children_lost = self.jail_children_of(inmate)
            self._conn.execute(
                "DELETE FROM jail_children WHERE parent_id = ?", (inmate,)
            )
            parent_lost = self.jail_parent_of(inmate)
            self._conn.execute(
                "DELETE FROM jail_children WHERE child_id = ?", (inmate,)
            )
            self._conn.commit()
        return ReleaseResult(sentence, divorced, children_lost, parent_lost)

    # ------------------------------------------------------------------ clear

    def clear_guild(self, guild_id: int) -> dict[str, int]:
        """Reset this guild's state: its settings row, proposals and
        notices filed here, restraining orders filed here, and jail
        sentences handed down here (inmates are released and their jail
        relationships dissolved).

        Deliberately NOT cleared: partners/children (the family tree is
        global across guilds - it isn't guild state) and personal block
        lists (also global). Returns per-table deletion counts."""
        counts: dict[str, int] = {}

        def _delete(table: str) -> int:
            with self._lock:
                cur = self._conn.execute(
                    f"DELETE FROM {table} WHERE guild_id = ?", (guild_id,)
                )
                self._conn.commit()
                return cur.rowcount

        counts["guild_settings"] = _delete("guild_settings")
        counts["proposals"] = _delete("proposals")
        counts["notices"] = _delete("notices")
        counts["restraining_orders"] = _delete("restraining_orders")
        sentences = [
            JailSentence(*r)
            for r in self._rows(
                f"SELECT {self._SENTENCE_COLS} FROM jail_sentences "
                "WHERE guild_id = ?",
                (guild_id,),
            )
        ]
        counts["jail_sentences"] = 0
        counts["jail_partners"] = 0
        counts["jail_children"] = 0
        for s in sentences:
            result = self.release_inmate(s.inmate)
            if result is None:
                continue
            counts["jail_sentences"] += 1
            counts["jail_partners"] += len(result.divorced)
            counts["jail_children"] += (
                len(result.children_lost)
                + (1 if result.parent_lost is not None else 0)
            )
        return counts

    # ------------------------------------------------------------------ misc

    def family_size(self, user_id: int) -> int:
        """Total number of distinct users reachable through partner/parent
        edges (i.e. everyone in the user's tree, excluding themselves)."""
        seen = {user_id}
        frontier = [user_id]
        while frontier:
            current = frontier.pop()
            neighbours = (
                self.partners_of(current)
                + self.children_of(current)
                + ([self.parent_of(current)] if self.parent_of(current) else [])
            )
            for n in neighbours:
                if n not in seen:
                    seen.add(n)
                    frontier.append(n)
        return len(seen) - 1

    def stats(self) -> dict[str, int]:
        def count(table: str) -> int:
            return self._row(f"SELECT COUNT(*) FROM {table}")[0]

        return {
            "marriages": count("partners"),
            "parent_child_links": count("children"),
            "open_proposals": count("proposals"),
            "partner_notices": count("notices"),
            "blocks": count("blocks"),
            "restraining_orders": count("restraining_orders"),
            "inmates": count("jail_sentences"),
            "guild_settings": count("guild_settings"),
        }
