"""Environment-driven configuration for Matrimony."""

from __future__ import annotations

import os
from dataclasses import dataclass

# Fluxpoint's shared public-tier key: the API provider ships it for bots to
# use as a default (see https://fluxpoint.dev). Override with FLUXPOINT_API_KEY.
DEFAULT_FLUXPOINT_API_KEY = "FP-Public-naEjca70OhKMtq67WpzaN8Gs"


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
        )
