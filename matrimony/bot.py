"""The Matrimony bot client."""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from .config import Config
from .family import FamilyView
from .store import Store

log = logging.getLogger("matrimony")


class MatrimonyBot(commands.Bot):
    """commands.Bot subclass wiring together config, store and cogs.

    Deliberately does **not** ignore messages from other bot accounts:
    marrying/adopting bots is a supported feature, so bot-authored command
    messages are dispatched like any other. Only messages authored by this
    bot itself are skipped, which is enough to prevent self-command loops.
    """

    def __init__(self, config: Config, store: Store | None = None) -> None:
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(
            command_prefix=self._get_prefix,
            intents=intents,
            case_insensitive=True,
            help_command=None,
        )
        self.config = config
        self.store = store or Store(config.database_path)
        self.family = FamilyView(self.store)

    # ------------------------------------------------------------- prefixes

    async def _get_prefix(self, bot: MatrimonyBot, message: discord.Message):
        """Per-guild prefix; falls back to the configured default.

        ``commands.when_mentioned`` support is kept so ``@Matrimony matr ...``
        always works regardless of prefix."""
        prefix = self.config.default_prefix
        if message.guild is not None:
            prefix = self.store.get_prefix(message.guild.id) or prefix
        return commands.when_mentioned_or(prefix)(bot, message)

    # ----------------------------------------------------------- dispatching

    def should_process(self, message: discord.Message) -> bool:
        """Whether ``message`` should be run through the command parser.

        Returns False only for this bot's own messages (self-loop guard).
        Other bots' messages ARE processed so that bot accounts can propose,
        accept, and adopt like human users."""
        return self.user is None or message.author.id != self.user.id

    async def on_message(self, message: discord.Message) -> None:
        if not self.should_process(message):
            return
        await self.process_commands(message)

    # --------------------------------------------------------------- setup

    async def setup_hook(self) -> None:
        from .cogs import ALL_COGS

        for cog in ALL_COGS:
            await self.add_cog(cog(self))
        log.info("Loaded %d cogs", len(ALL_COGS))


def run() -> None:
    """Console entrypoint: ``python -m matrimony``."""
    logging.basicConfig(level=logging.INFO)
    config = Config.from_env()
    if not config.token:
        raise SystemExit(
            "MATRIMONY_TOKEN is not set. Copy .env.example to .env, fill in "
            "your Discord bot token, and export it (or use a process manager "
            "that loads .env)."
        )
    bot = MatrimonyBot(config)
    bot.run(config.token)
