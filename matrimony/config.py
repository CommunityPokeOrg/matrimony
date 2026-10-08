"""Environment-driven configuration for Matrimony."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("matrimony")

# Fluxpoint's shared public-tier key: the API provider ships it for bots to
# use as a default (see https://fluxpoint.dev). Override with FLUXPOINT_API_KEY.
DEFAULT_FLUXPOINT_API_KEY = "FP-Public-naEjca70OhKMtq67WpzaN8Gs"


def _parse_allowed_channels(raw: str, source: str) -> dict[int, frozenset[int]]:
    """Parse a JSON object mapping guild ids to lists of channel ids.

    Any malformed input (bad JSON, non-object top level, non-list values,
    non-numeric ids) logs a warning and yields no restrictions, so a typo
    can never lock every guild out of the bot."""
    try:
        data = json.loads(raw)
    except ValueError:
        log.warning("%s is not valid JSON; ignoring it", source)
        return {}
    if not isinstance(data, dict):
        log.warning(
            "%s must be a JSON object mapping guild ids to channel id "
            "lists; ignoring it",
            source,
        )
        return {}
    try:
        out: dict[int, frozenset[int]] = {}
        for guild_id, channel_ids in data.items():
            if not isinstance(channel_ids, list):
                raise TypeError(f"{guild_id!r} is not a channel id list")
            out[int(guild_id)] = frozenset(int(c) for c in channel_ids)
    except (TypeError, ValueError):
        log.warning(
            "%s must map guild ids to lists of channel ids; ignoring it",
            source,
        )
        return {}
    return out


def _allowed_channels_from_env(env: dict[str, str]) -> dict[int, frozenset[int]]:
    """Resolve the per-guild channel allow-list.

    ``MATRIMONY_ALLOWED_CHANNELS`` holds the JSON mapping inline; when it
    is unset, ``MATRIMONY_ALLOWED_CHANNELS_FILE`` points to a JSON file
    with the same structure."""
    raw = env.get("MATRIMONY_ALLOWED_CHANNELS", "").strip()
    if raw:
        return _parse_allowed_channels(raw, "MATRIMONY_ALLOWED_CHANNELS")
    path = env.get("MATRIMONY_ALLOWED_CHANNELS_FILE", "").strip()
    if not path:
        return {}
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        log.warning(
            "Could not read MATRIMONY_ALLOWED_CHANNELS_FILE %r: %s; "
            "ignoring it",
            path,
            exc,
        )
        return {}
    return _parse_allowed_channels(
        raw, f"MATRIMONY_ALLOWED_CHANNELS_FILE ({path})"
    )


@dataclass(frozen=True)
class Config:
    """Runtime configuration, read from environment variables.

    Attributes:
        token: Discord bot token (required).
        default_prefix: Fallback command prefix for guilds/DMs without a custom
            prefix. The command *name* stays fixed (``matr`` by default); only
            the leading sigil is customised.
        command_name: Name of the command group, e.g. ``!matr ...``.
        database_path: SQLite database file location.
        max_partners: Maximum simultaneous partners per user. 0 = unlimited
            (MarriageBot itself has no partner cap).
        max_children: Maximum children per user. 0 = unlimited.
        max_tree_depth: Depth limit applied when rendering family trees.
        proposal_ttl_seconds: How long a proposal stays open.
        fluxpoint_api_key: Fluxpoint API token used to fetch action GIFs.
            Defaults to the provider's public-tier key; set
            ``FLUXPOINT_API_KEY`` to your own token, or to an empty string
            to disable GIF fetching entirely.
        allowed_channels: Per-guild command allow-list: guild id -> the
            channel ids where commands are accepted. Guilds absent from
            the mapping are unrestricted; a guild mapped to an empty list
            blocks every channel. DMs are never restricted. Set via
            ``MATRIMONY_ALLOWED_CHANNELS`` or
            ``MATRIMONY_ALLOWED_CHANNELS_FILE``.
    """

    token: str = ""
    default_prefix: str = "!"
    command_name: str = "matr"
    database_path: str = "matrimony.db"
    max_partners: int = 0
    max_children: int = 0
    max_tree_depth: int = 10
    proposal_ttl_seconds: int = 300
    fluxpoint_api_key: str = DEFAULT_FLUXPOINT_API_KEY
    allowed_channels: dict[int, frozenset[int]] = field(default_factory=dict)

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Config:
        env = os.environ if env is None else env
        return cls(
            token=env.get("MATRIMONY_TOKEN", ""),
            default_prefix=env.get("MATRIMONY_DEFAULT_PREFIX", "!"),
            command_name=env.get("MATRIMONY_COMMAND_NAME", "matr"),
            database_path=env.get("MATRIMONY_DB_PATH", "matrimony.db"),
            max_partners=int(env.get("MATRIMONY_MAX_PARTNERS", "0")),
            max_children=int(env.get("MATRIMONY_MAX_CHILDREN", "0")),
            max_tree_depth=int(env.get("MATRIMONY_MAX_TREE_DEPTH", "10")),
            proposal_ttl_seconds=int(env.get("MATRIMONY_PROPOSAL_TTL", "300")),
            fluxpoint_api_key=env.get(
                "FLUXPOINT_API_KEY", DEFAULT_FLUXPOINT_API_KEY
            ),
            allowed_channels=_allowed_channels_from_env(env),
        )
