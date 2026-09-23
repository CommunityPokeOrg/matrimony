"""SQLite storage layer for Matrimony.

Family relationships are *global* (cross-server), matching the original
MarriageBot design where family trees span every guild the bot is in.
Guild-scoped data is limited to per-guild settings (prefix, incest toggle)
and the guild/channel a proposal was made in.
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
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    UNIQUE (proposer, target, kind)
);

CREATE TABLE IF NOT EXISTS blocks (
    blocker INTEGER NOT NULL,
    blocked INTEGER NOT NULL,
    PRIMARY KEY (blocker, blocked)
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
    created_at: int
    expires_at: int


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
            self._conn.commit()
            return cur.rowcount > 0

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
    ) -> Proposal | None:
        """Create a proposal. Returns None if an identical open one exists."""
        now = int(time.time())
        self.expire_proposals(now)
        with self._lock:
            existing = self._row(
                "SELECT id FROM proposals WHERE proposer = ? AND target = ? "
                "AND kind = ?",
                (proposer, target, kind),
            )
            if existing:
                return None
            cur = self._conn.execute(
                """INSERT INTO proposals
                   (guild_id, channel_id, proposer, target, kind,
                    created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (guild_id, channel_id, proposer, target, kind, now,
                 now + ttl_seconds),
            )
            self._conn.commit()
            pid = cur.lastrowid
        return Proposal(pid, guild_id, channel_id, proposer, target, kind,
                        now, now + ttl_seconds)

    def get_proposal(self, proposal_id: int) -> Proposal | None:
        row = self._row(
            "SELECT id, guild_id, channel_id, proposer, target, kind, "
            "created_at, expires_at FROM proposals WHERE id = ?",
            (proposal_id,),
        )
        return Proposal(*row) if row else None

    def proposals_for(self, target: int, kind: str | None = None) -> list[Proposal]:
        self.expire_proposals()
        if kind is None:
            rows = self._rows(
                "SELECT id, guild_id, channel_id, proposer, target, kind, "
                "created_at, expires_at FROM proposals WHERE target = ?",
                (target,),
            )
        else:
            rows = self._rows(
                "SELECT id, guild_id, channel_id, proposer, target, kind, "
                "created_at, expires_at FROM proposals WHERE target = ? "
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
            "blocks": count("blocks"),
            "guild_settings": count("guild_settings"),
        }
