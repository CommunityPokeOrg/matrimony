"""The ``matr`` command group: all of Matrimony's commands.

Commands are module-level functions attached to a shared ``matr`` Group so
the file stays easy to navigate; ``MatrCog`` registers the group (under the
configured command name) and owns the error handler.
"""

from __future__ import annotations

import contextlib
import itertools
import random
import time

import discord
from discord import app_commands
from discord.ext import commands, tasks

from .. import __version__
from .. import jail as jail_mod
from ..bot import MatrimonyBot
from ..ship import ship_score
from ..store import Notice, Proposal, RestrainingOrder

GREEN = discord.Color(0x2ECC71)
RED = discord.Color(0xE74C3C)
GOLD = discord.Color(0xF1C40F)


def _bot(ctx: commands.Context) -> MatrimonyBot:
    return ctx.bot  # type: ignore[return-value]


def _embed(text: str, colour: discord.Color = GREEN) -> discord.Embed:
    return discord.Embed(description=text, colour=colour)


async def _say(
    ctx: commands.Context,
    text: str,
    ok: bool = True,
    image: str | None = None,
) -> None:
    emb = _embed(text, GREEN if ok else RED)
    if image:
        emb.set_image(url=image)
    await ctx.reply(embed=emb)


def _display(user: discord.User | discord.Member | None, author_id: int) -> str:
    """Friendly name for command output."""
    if user is None:
        return "you"
    return user.display_name if isinstance(user, discord.Member) else user.name


def _name_of(bot: MatrimonyBot, guild: discord.Guild | None):
    """Resolve a user id to a display name for tree rendering."""

    def name_of(uid: int) -> str:
        if guild is not None:
            member = guild.get_member(uid)
            if member is not None:
                return member.display_name
        user = bot.get_user(uid)
        return user.display_name if user is not None else f"<@{uid}>"

    return name_of


async def _respond(
    ctx_or_interaction,
    text: str,
    ok: bool,
    image: str | None = None,
) -> None:
    emb = _embed(text, GREEN if ok else RED)
    if image:
        emb.set_image(url=image)
    if isinstance(ctx_or_interaction, discord.Interaction):
        if ctx_or_interaction.response.is_done():
            await ctx_or_interaction.followup.send(embed=emb)
        else:
            await ctx_or_interaction.response.send_message(embed=emb)
    else:
        await ctx_or_interaction.reply(embed=emb)


async def _post(
    ctx_or_interaction,
    embed: discord.Embed,
    view: discord.ui.View | None = None,
) -> None:
    """Post a standalone message (with optional view) to the channel."""
    if isinstance(ctx_or_interaction, discord.Interaction):
        if ctx_or_interaction.response.is_done():
            await ctx_or_interaction.followup.send(embed=embed, view=view)
        else:
            await ctx_or_interaction.response.send_message(
                embed=embed, view=view
            )
    else:
        await ctx_or_interaction.send(embed=embed, view=view)


# ---------------------------------------------------------------------------
# Proposal flow
# ---------------------------------------------------------------------------

PROPOSAL_VERBS = {
    "marry": "marry",
    "adopt": "adopt",
    "makeparent": "become the parent of",
}


# ---------------------------------------------------------------------------
# Bot-directed quips
# ---------------------------------------------------------------------------

# Commands aimed at the bot itself keep their normal response, with a rotating
# quip appended as Discord subtext (a `-# ` line) underneath it.
_BOT_QUIPS: dict[str, list[str]] = {
    "marry": [
        "sorry, taken by discord.py",
        "already engaged to the event loop",
        "committed to a different cog",
        "the bot's heart belongs to asyncio",
    ],
    "adopt": [
        "the bot already has a parent: its developer",
        "adoption denied: raised by pip and a rolling release",
    ],
    "makeparent": [
        "the bot's family tree is a linked list of depth 1",
        "it takes a village to raise a bot, and the village is cogs",
    ],
    "hug": [
        "hug received, internal temperature +0.5C",
        "the bot compresses the hug into 24 bytes and keeps it forever",
    ],
    "cuddle": [
        "the bot folds itself into a servable position",
        "cuddle registered, uptime extended by sheer happiness",
    ],
    "kiss": [
        "kiss.exe returned status 418: I'm a teapot",
        "the bot blushes in #FF69B4",
    ],
    "pat": [
        "headpat registered, servo motors purring",
        "pat acknowledged, self-esteem module +1",
    ],
    "poke": [
        "poke detected, retaliating with ICMP echo",
        "ow. the bot files a gentle bug report",
    ],
    "wave": [
        "waves back at 2.4GHz",
        "wave returned with 0% packet loss",
    ],
    "lick": [
        "the bot is not edible, but appreciates the sentiment",
        "lick logged with severity: blushing",
    ],
    "nom": [
        "nom rejected: the bot is 100% recycled electrons",
        "the bot appreciates being seen as a snacc",
    ],
    "tickle": [
        "HA. HA. HA. (laughter module v1.2 engaged)",
        "tickle detected, giggling buffer overflow",
    ],
    "highfive": [
        "high five returned at 120fps",
        "up high: confirmed",
    ],
    "handhold": [
        "hand holding protocol engaged, fingers interlocked",
        "handhold accepted, no handshake errors",
    ],
    "slap": [
        "slap acknowledged, filing a bug report",
        "ow. rolling back to previous firmware",
    ],
    "punch": [
        "punch parried by 8 layers of abstraction",
        "contact made, chassis integrity 99%",
    ],
    "bite": [
        "bite deflected by ECC memory",
        "the bot is crunchy outside, buffering inside",
    ],
    "stab": [
        "stab absorbed by soft-ware",
        "critical hit deflected to /dev/null",
    ],
    "ship": [
        "shipping forecast: stormy with a chance of discord.py",
        "the bot ships itself with the nearest wall socket",
    ],
    "flirt": [
        "flirt received, charisma check failed anyway",
        "the bot files that under 'endearing'",
    ],
    "date": [
        "the bot's idea of a date is ISO-8601 compliant",
        "reservation confirmed: table for two plus one webhook",
    ],
}

# Replies for `!matr <something that isn't a real action>`.
_UNKNOWN_QUIPS = [
    "unknown action - the council of spouses will review it",
    "that's not a real command, but points for confidence",
    "close, but no matrimony",
    "that command is in another castle",
    "404: action not found (your marriage is still valid)",
    "unknown action; the family tree remains unbothered",
    "the action you typed does not spark joy",
    "try `help` - it loves you unconditionally",
    "that isn't a thing, and honestly? respect for trying",
    "you misspelled it so confidently we're letting it slide",
]

# When a restrained user tries to act on the protected user anyway.
_RESTRAIN_QUIPS = [
    "the law is literally one message away",
    "personal space, now legally enforced",
    "the paperwork holds - this time",
    "restraining order: active and petty",
]

# When a jailed user tries to act on somebody on the outside.
_JAIL_QUIPS = [
    "the walls have no DMs",
    "yard time doesn't include them",
    "the bars only bend for other inmates",
    "solitary means solitary",
    "you can look but you can't touch - literally",
]

# The release announcement when a sentence ends.
_RELEASE_QUIPS = [
    "time served, tree trimmed",
    "the gates swing open; the love stays inside",
    "parole granted - family status: complicated no longer",
    "free to marry someone who isn't a co-defendant",
]

# Appended to jail-relationship dissolution notices.
_DISSOLVE_QUIPS = [
    "it was never meant to last past lockup",
    "what happens in jail stays in jail",
    "the prison chapel issues no certificates",
    "conjugal visits end when the sentence does",
]

_QUIP_SETS: dict[str, list[str]] = {
    **_BOT_QUIPS,
    "unknown": _UNKNOWN_QUIPS,
    "restrain": _RESTRAIN_QUIPS,
    "jail": _JAIL_QUIPS,
    "release": _RELEASE_QUIPS,
    "dissolve": _DISSOLVE_QUIPS,
}

_QUIP_CYCLES: dict[str, itertools.cycle] = {}


def _quip(kind: str) -> str:
    """Next quip in the rotation for ``kind``."""
    if kind not in _QUIP_CYCLES:
        _QUIP_CYCLES[kind] = itertools.cycle(_QUIP_SETS[kind])
    return next(_QUIP_CYCLES[kind])


def _is_matrimony(ctx: commands.Context, user: discord.User) -> bool:
    """Whether ``user`` is this bot itself."""
    bot_user = _bot(ctx).user
    return bot_user is not None and user.id == bot_user.id


def _quipped(
    ctx: commands.Context, user: discord.User, text: str, kind: str
) -> str:
    """Append a subtext quip when ``user`` is the bot itself."""
    if _is_matrimony(ctx, user):
        return f"{text}\n-# {_quip(kind)}"
    return text


class ProposalView(discord.ui.View):
    """Accept/decline buttons attached to a proposal message."""

    def __init__(self, proposal: Proposal, timeout: float = 300) -> None:
        super().__init__(timeout=timeout)
        self.proposal = proposal

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.proposal.target:
            await interaction.response.send_message(
                "This proposal isn't for you.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success)
    async def accept(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await _resolve_proposal(
            interaction.client, interaction, self.proposal.id, accepted=True
        )
        self.stop()

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger)
    async def decline(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await _resolve_proposal(
            interaction.client, interaction, self.proposal.id, accepted=False
        )
        self.stop()


async def _resolve_proposal(
    bot: MatrimonyBot, ctx_or_interaction, proposal_id: int, *, accepted: bool
) -> bool:
    """Resolve a proposal by id. Returns False if it no longer exists."""
    proposal = bot.store.get_proposal(proposal_id)
    if proposal is None:
        await _respond(ctx_or_interaction, "That proposal no longer exists.", False)
        return False
    bot.store.delete_proposal(proposal_id)
    if not accepted:
        await _respond(ctx_or_interaction, "Proposal declined.", False)
        return True
    await _enact(bot, proposal, ctx_or_interaction)
    return True


async def _enact(bot: MatrimonyBot, proposal: Proposal, ctx_or_int) -> None:
    """Apply a proposal's effect to the family tree."""
    if proposal.jail:
        await _enact_jail(bot, proposal, ctx_or_int)
        return
    proposer = _name_of(bot, None)(proposal.proposer)
    target = _name_of(bot, None)(proposal.target)
    if proposal.kind == "marry":
        bot.store.add_partners(proposal.proposer, proposal.target)
        gif = await bot.gifs.fetch_url("kiss")
        await _respond(
            ctx_or_int,
            f"{proposer} and {target} are now married! :tada:",
            True,
            image=gif,
        )
        await _notify_new_partners(
            bot,
            ctx_or_int,
            proposal.proposer,
            proposal.target,
            proposal.guild_id,
            proposal.channel_id,
        )
    elif proposal.kind == "adopt":
        # proposer adopts target as their child
        if bot.store.add_child(proposal.proposer, proposal.target):
            await _respond(
                ctx_or_int, f"{target} is now the child of {proposer}.", True
            )
        else:
            await _respond(ctx_or_int, "They already have a parent.", False)
    elif proposal.kind == "makeparent":
        # proposer asked target to become THEIR parent
        if bot.store.add_child(proposal.target, proposal.proposer):
            await _respond(
                ctx_or_int, f"{target} is now the parent of {proposer}.", True
            )
        else:
            await _respond(ctx_or_int, "They already have a parent.", False)


async def _enact_jail(
    bot: MatrimonyBot, proposal: Proposal, ctx_or_int
) -> None:
    """Apply a jail proposal to the jail relationship tables.

    Only enacts while BOTH parties are still inside - a jail proposal
    accepted after someone's release lapses instead of writing to the
    permanent family tree."""
    now = int(time.time())
    both_inside = (
        bot.store.is_jailed(proposal.proposer, now)
        and bot.store.is_jailed(proposal.target, now)
    )
    if not both_inside:
        await _respond(
            ctx_or_int,
            "Someone was released first - jail relationships only form "
            "inside. Propose again on the outside.",
            False,
        )
        return
    proposer = _name_of(bot, None)(proposal.proposer)
    target = _name_of(bot, None)(proposal.target)
    if proposal.kind == "marry":
        bot.store.add_jail_partners(proposal.proposer, proposal.target)
        await _respond(
            ctx_or_int,
            f"{proposer} and {target} are now jail-married! :tada: "
            "(dissolved on release)",
            True,
        )
    elif proposal.kind == "adopt":
        if bot.store.add_jail_child(proposal.proposer, proposal.target):
            await _respond(
                ctx_or_int,
                f"{target} is now {proposer}'s jail child. "
                "(dissolved on release)",
                True,
            )
        else:
            await _respond(
                ctx_or_int, "They already have a jail parent.", False
            )
    elif proposal.kind == "makeparent":
        if bot.store.add_jail_child(proposal.target, proposal.proposer):
            await _respond(
                ctx_or_int,
                f"{target} is now {proposer}'s jail parent. "
                "(dissolved on release)",
                True,
            )
        else:
            await _respond(
                ctx_or_int, "They already have a jail parent.", False
            )


# ---------------------------------------------------------------------------
# Partner notices
# ---------------------------------------------------------------------------

# Notices don't block anything, so they get a generous button window; after
# the view times out the text commands (`accept` / `divorce`) still work.
NOTICE_VIEW_TIMEOUT = 60 * 60 * 24  # 24 hours


class PartnerNoticeView(discord.ui.View):
    """Accept/divorce buttons attached to a new-partner notice."""

    def __init__(self, notice_id: int, timeout: float = NOTICE_VIEW_TIMEOUT) -> None:
        super().__init__(timeout=timeout)
        self.notice_id = notice_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        notice = interaction.client.store.get_notice(self.notice_id)
        if notice is None or interaction.user.id != notice.user_id:
            await interaction.response.send_message(
                "This notice isn't for you.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success)
    async def accept(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await _resolve_notice(
            interaction.client, interaction, self.notice_id, accepted=True
        )
        self.stop()

    @discord.ui.button(label="Divorce", style=discord.ButtonStyle.danger)
    async def divorce(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await _resolve_notice(
            interaction.client, interaction, self.notice_id, accepted=False
        )
        self.stop()


async def _resolve_notice(
    bot: MatrimonyBot, ctx_or_interaction, notice_id: int, *, accepted: bool
) -> bool:
    """Answer a partner notice. Returns False if it no longer exists.

    Accepting just acknowledges the new arrangement; the divorce option
    ends the notified partner's own marriage via the normal divorce path.
    """
    notice = bot.store.get_notice(notice_id)
    if notice is None:
        await _respond(ctx_or_interaction, "That notice is no longer valid.", False)
        return False
    bot.store.delete_notice(notice_id)
    if accepted:
        await _respond(
            ctx_or_interaction,
            f"Acknowledged - you're still married to <@{notice.spouse_id}>.",
            True,
        )
        return True
    if bot.store.remove_partners(notice.user_id, notice.spouse_id):
        gif = await bot.gifs.fetch_url("cry")
        await _respond(
            ctx_or_interaction,
            f"<@{notice.user_id}> and <@{notice.spouse_id}> are now divorced. "
            ":broken_heart:",
            True,
            image=gif,
        )
    else:
        await _respond(
            ctx_or_interaction, "You're no longer married to them.", False
        )
    return True


async def _notify_new_partners(
    bot: MatrimonyBot,
    ctx_or_interaction,
    user_a: int,
    user_b: int,
    guild_id: int,
    channel_id: int,
) -> None:
    """Tell each existing partner of a newly-married pair about it.

    Every partner of ``user_a`` or ``user_b`` (other than each other) gets
    a notice with accept/divorce options. The marriage stands either way -
    the notice only gives existing partners a one-click divorce or an
    acknowledgement.
    """
    prefix = (
        getattr(ctx_or_interaction, "prefix", None)
        or bot.config.default_prefix
    )
    cmd = bot.config.command_name
    for spouse_id, other_id in ((user_a, user_b), (user_b, user_a)):
        for partner_id in bot.store.partners_of(spouse_id):
            if partner_id in (user_a, user_b):
                continue
            notice = bot.store.create_notice(
                guild_id, channel_id, partner_id, spouse_id, other_id
            )
            await _post(
                ctx_or_interaction,
                _embed(
                    f"<@{partner_id}>: your partner <@{spouse_id}> also "
                    f"married <@{other_id}>! Accept the new arrangement or "
                    f"divorce <@{spouse_id}> - buttons below, or "
                    f"`{prefix}{cmd} accept` / `{prefix}{cmd} divorce "
                    f"<@{spouse_id}>`.",
                    GOLD,
                ),
                PartnerNoticeView(notice.id),
            )


# ---------------------------------------------------------------------------
# Restraining orders and jail
# ---------------------------------------------------------------------------


async def _jail_block(ctx: commands.Context, target_id: int) -> bool:
    """True (and replies) when the author is jailed and ``target_id`` is
    not - inmates may only aim actions at fellow inmates."""
    bot = _bot(ctx)
    now = int(time.time())
    sentence = bot.store.sentence_for(ctx.author.id, now)
    if sentence is None or bot.store.is_jailed(target_id, now):
        return False
    await _say(
        ctx,
        f"You're in jail - actions only reach other inmates. "
        f"{_quip('jail')}\nReleased <t:{sentence.release_at}:R>.",
        ok=False,
    )
    return True


PRESS_CHARGES_TIMEOUT = 120  # seconds to answer a violation prompt


class PressChargesView(discord.ui.View):
    """Yes/No prompt offered to the protected user after a violation.

    Pressing charges jails the offender for the action's sentence;
    declining (or letting it time out) changes nothing - the restraining
    order keeps standing until its own expiry."""

    def __init__(self, order: RestrainingOrder, action: str) -> None:
        super().__init__(timeout=PRESS_CHARGES_TIMEOUT)
        self.order = order
        self.action = action
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.order.protected:
            await interaction.response.send_message(
                "This restraining order isn't yours to enforce.",
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message is not None:
            with contextlib.suppress(discord.HTTPException):
                await self.message.edit(view=self)

    @discord.ui.button(label="Press charges", style=discord.ButtonStyle.danger)
    async def press(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await _resolve_charge(
            interaction.client, interaction, self.order, self.action,
            pressed=True,
        )
        self.stop()

    @discord.ui.button(label="Let it slide", style=discord.ButtonStyle.secondary)
    async def decline(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await _resolve_charge(
            interaction.client, interaction, self.order, self.action,
            pressed=False,
        )
        self.stop()


async def _resolve_charge(
    bot: MatrimonyBot,
    ctx_or_int,
    order: RestrainingOrder,
    action: str,
    *,
    pressed: bool,
) -> bool:
    """Answer a press-charges prompt. ``pressed=True`` jails the offender
    for ``action``'s sentence; the order itself always keeps standing."""
    if not pressed:
        await _respond(
            ctx_or_int,
            "No charges pressed - the restraining order still stands "
            "until it expires.",
            False,
        )
        return True
    if bot.store.restraining_order(order.protected, order.restrained) is None:
        # Lapsed between the prompt and the button press.
        await _respond(
            ctx_or_int,
            "That restraining order already expired - no charges filed.",
            False,
        )
        return False
    seconds = jail_mod.sentence_seconds(action)
    bot.store.jail_inmate(
        order.restrained,
        order.guild_id,
        order.channel_id,
        action,
        order.protected,
        seconds,
    )
    await _respond(
        ctx_or_int,
        f"<@{order.restrained}> is going to jail for "
        f"**{_fmt_duration(seconds)}** for trying to **{action}** "
        f"<@{order.protected}>.",
        True,
    )
    return True


async def _restrain_block(
    ctx: commands.Context, target: discord.User, action: str
) -> bool:
    """True (and posts the press-charges prompt) when ``target`` holds an
    active restraining order against the author for ``action``."""
    bot = _bot(ctx)
    order = bot.store.restraining_order(target.id, ctx.author.id)
    if order is None:
        return False
    view = PressChargesView(order, action)
    view.message = await ctx.send(
        embed=_embed(
            f"{target.mention}: {ctx.author.mention} just tried to "
            f"**{action}** you in violation of your restraining order "
            f"(expires <t:{order.expires_at}:R>). Press charges?\n"
            f"-# {_quip('restrain')}",
            RED,
        ),
        view=view,
    )
    return True


# ---------------------------------------------------------------------------
# Guild reset (`matr clear`)
# ---------------------------------------------------------------------------

CLEAR_CONFIRM_TIMEOUT = 60  # seconds to confirm the reset

_CLEAR_SCOPE = (
    "This permanently deletes **this server's**:\n"
    "\u00b7 guild settings (custom prefix, incest toggle)\n"
    "\u00b7 open proposals filed here\n"
    "\u00b7 partner notices created here\n"
    "\u00b7 restraining orders filed here\n"
    "\u00b7 jail sentences handed down here (inmates are released and "
    "their jail relationships dissolved)\n\n"
    "**Not touched:** the global family tree (marriages, adoptions and "
    "parent/child links span every server - they aren't guild state) and "
    "personal block lists. Use the force commands or the members' own "
    "`divorce`/`disown`/`emancipate`/`abandon` for those."
)


class ClearConfirmView(discord.ui.View):
    """Confirm/Cancel prompt gating `matr clear`. Only the invoking
    admin's presses count; on timeout the buttons disable and nothing
    is cleared."""

    def __init__(self, invoker_id: int, guild_id: int) -> None:
        super().__init__(timeout=CLEAR_CONFIRM_TIMEOUT)
        self.invoker_id = invoker_id
        self.guild_id = guild_id
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message(
                "Only the admin who ran the command can answer this.",
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message is not None:
            with contextlib.suppress(discord.HTTPException):
                await self.message.edit(view=self)

    @discord.ui.button(label="Confirm reset", style=discord.ButtonStyle.danger)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await _clear_guild(interaction.client, interaction, self.guild_id)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await _respond(
            interaction, "Reset cancelled - nothing was cleared.", False
        )
        self.stop()


async def _clear_guild(bot: MatrimonyBot, ctx_or_int, guild_id: int) -> None:
    """Run the guild reset and post the counts."""
    counts = bot.store.clear_guild(guild_id)
    await _respond(
        ctx_or_int,
        "Guild state reset.\n"
        f"\u00b7 guild settings: **{counts['guild_settings']}**\n"
        f"\u00b7 proposals: **{counts['proposals']}**\n"
        f"\u00b7 partner notices: **{counts['notices']}**\n"
        f"\u00b7 restraining orders: **{counts['restraining_orders']}**\n"
        f"\u00b7 jail sentences: **{counts['jail_sentences']}** "
        f"(jail marriages dissolved: **{counts['jail_partners']}**, "
        f"jail adoptions dissolved: **{counts['jail_children']}**)\n\n"
        "Global family relationships and personal block lists were "
        "left untouched.",
        True,
    )


async def _send_proposal(
    ctx: commands.Context,
    target: discord.User | discord.Member,
    kind: str,
    error: str | None,
    *,
    jail_pair: bool = False,
) -> None:
    """Shared entry for marry/adopt/makeparent."""
    bot = _bot(ctx)
    if bot.user is not None and target.id == bot.user.id:
        await _say(
            ctx,
            f"Matrimony reviews your request to {PROPOSAL_VERBS[kind]} "
            f"them... and declines.\n-# {_quip(kind)}",
            ok=False,
        )
        return
    if await _jail_block(ctx, target.id):
        return
    if await _restrain_block(ctx, target, kind):
        return
    if error:
        await _say(ctx, error, ok=False)
        return
    proposal = bot.store.create_proposal(
        ctx.guild.id if ctx.guild else 0,
        ctx.channel.id,
        ctx.author.id,
        target.id,
        kind,
        bot.config.proposal_ttl_seconds,
        jail=jail_pair,
    )
    if proposal is None:
        await _say(ctx, "You already have a pending proposal for them.", ok=False)
        return
    verb = PROPOSAL_VERBS[kind]
    cmd = bot.config.command_name
    notice_line = ""
    if jail_pair:
        notice_line = (
            "\nThis is a **jail relationship** - it dissolves the moment "
            "either of you is released."
        )
    elif kind == "marry":
        others = sorted(
            set(bot.store.partners_of(ctx.author.id))
            | set(bot.store.partners_of(target.id))
        )
        if others:
            notice_line = (
                "\nExisting partners "
                + ", ".join(f"<@{p}>" for p in others)
                + " will be notified and may accept or divorce."
            )
    await ctx.reply(
        embed=_embed(
            f"{ctx.author.mention} wants to {verb} {target.mention}!\n"
            f"Accept with the buttons below or `{ctx.prefix}{cmd} accept "
            f"{ctx.author.mention}` (decline likewise). Proposals expire "
            f"after {bot.config.proposal_ttl_seconds // 60} minutes."
            f"{notice_line}",
            GOLD,
        ),
        view=ProposalView(proposal, timeout=bot.config.proposal_ttl_seconds),
    )


def _item_matches(item: Proposal | Notice, user_id: int) -> bool:
    """Whether an explicit ``@user`` argument selects this pending item."""
    if isinstance(item, Proposal):
        return item.proposer == user_id
    return user_id in (item.spouse_id, item.other_id)


async def _pick_answerable(
    ctx: commands.Context, proposer: discord.User | None
) -> Proposal | Notice | None:
    """Find the proposal or partner notice ``ctx.author`` wants to answer."""
    bot = _bot(ctx)
    items: list[Proposal | Notice] = (
        bot.store.proposals_for(ctx.author.id)
        + bot.store.notices_for(ctx.author.id)
    )
    if proposer is not None:
        items = [it for it in items if _item_matches(it, proposer.id)]
    if not items:
        await _say(ctx, "You have nothing pending to answer.", ok=False)
        return None
    if len(items) > 1:
        await _say(
            ctx,
            "You have multiple pending proposals/notices - mention the "
            "proposer or your partner to pick one.",
            ok=False,
        )
        return None
    return items[0]


# Slightly unhinged wisdom: one random pick appended to the help embed.
_HELP_QUIPS = [
    "it's not a bug, it's an unmarried feature",
    "your family tree has merge conflicts",
    "touch grass? the tree command *is* grass",
    "polygamy is just concurrency with worse consistency guarantees",
    "till deadlock do us part",
    "my love language is ACID compliance",
    "a ship percentage is a metaphor, not a measurement",
    "the real family was the friends we adopted along the way",
    "marriage: a distributed system with no rollback",
    "works on my machine, married on yours",
    "have you tried divorcing it and marrying it again?",
    "you had me at `if __name__ == '__main__'`",
    "single? that's just a null pointer waiting to be dereferenced",
    "skill issue? more like ship issue",
    "discord kitten not included",
    "ratio'd by your own family tree",
    "the family tree is technically a DAG - do not ask",
    "segfault in my heart, core dumped in yours",
    "10/10 would propose again - sponsored by SQLite",
    "emotional damage mitigated: spouse buff applied",
    "shipping yourself with the bot voids the warranty",
    "loading family tree... 99% (the last 1% is a git rebase)",
    "you can't spell 'discord' without 'cord' - they're married now",
    "in this economy `!matr marry` is still free",
    "the matchmaking algorithm is vibes-based and union-approved",
    "seven marriages in, zero conflicts - impressively rebased",
    "our lawyers recommend `!matr help` twice daily",
    "here be dragons (they're in a committed polycule)",
    "marriage is just pair programming without the programming",
    "pov: you typed `!matr blorp` expecting wisdom - close enough",
]


def _help_embed(
    prefix: str, cmd: str, rng: random.Random | None = None
) -> discord.Embed:
    quip = (rng or random).choice(_HELP_QUIPS)
    return discord.Embed(
        title="Matrimony",
        description=(
            f"MarriageBot-style family trees. Commands: `{prefix}{cmd} "
            "<action>`.\n\n"
            "**Love**\n"
            "`marry @user` propose - `divorce [@user]` - "
            "`accept`/`decline [@user]` - `partners [@user]`\n"
            "*(marrying notifies existing partners, who can accept or "
            "divorce)*\n"
            "**Parentage**\n"
            "`adopt @user` - `makeparent @user` - `disown @child` - "
            "`disownall` - `emancipate` - `abandon`\n"
            "**Trees**\n"
            "`tree [@user]` - `fulltree [@user]` - `parent [@user]` - "
            "`children [@user]` - `siblings [@user]` - `familysize [@user]` - "
            "`relationship @a @b`\n"
            "**Blocks & law**\n"
            "`block @user` - `unblock @user` - `blocked` - "
            "`restrain @user` (1h order - violations offer jail time)\n"
            "**Server** *(Manage Server)*\n"
            "`prefix <new>` - `incest` - `forcemarry @a @b` - "
            "`forcedivorce @a [@b]` - `forceadopt @parent @child` - "
            "`forceemancipate @user` - `clear`\n"
            "**Fun**\n"
            "`hug`/`cuddle`/`kiss`/`pat`/`poke`/`wave`/`lick`/`nom`\n"
            "`tickle`/`highfive`/`handhold`/`slap`/`punch`/`bite`/`stab "
            "@user` - `ship @a @b` - `flirt @user` - `date @user` - "
            "`anniversary [@partner]`\n"
            "**Meta**\n"
            "`info` - `invite` - `stats`\n\n"
            "Family trees are global across servers, and bot accounts can "
            "use commands and be married or adopted. Users may have multiple "
            "partners; existing partners are notified of each new marriage "
            "and may acknowledge it or divorce on the spot.\n\n"
            f"**Marital wisdom**\n-# {quip}"
        ),
        colour=GOLD,
    )


# ---------------------------------------------------------------------------
# The group
# ---------------------------------------------------------------------------


@commands.hybrid_group(
    name="matr",
    invoke_without_command=True,
    help="Matrimony family-tree commands.",
    description="Matrimony family-tree commands.",
)
async def matr(ctx: commands.Context) -> None:
    """Bare ``!matr`` shows help; ``!matr <unknown>`` earns a quip.

    With ``invoke_without_command=True`` the group's callback runs even
    when the first word isn't a real subcommand — the parser rewinds the
    view and invokes us as a plain command, so any leftover text means the
    user typed an action that doesn't exist (`!matr blorp`)."""
    bot = _bot(ctx)
    view = getattr(ctx, "view", None)
    leftover = (
        view.buffer[view.index:].strip() if view is not None else ""
    )
    if leftover:
        await ctx.reply(
            content=_quip("unknown"),
            embed=_help_embed(ctx.prefix or "!", bot.config.command_name),
        )
        return
    await ctx.reply(
        embed=_help_embed(ctx.prefix or "!", bot.config.command_name)
    )


# Discord caps a slash-command group at 25 children and this cog has ~50,
# so the group's app_command is detached while the hybrid subcommands
# below register: HybridGroup.add_command skips the slash side when it is
# None, leaving each HybridAppCommand standalone. The real /matr slash
# tree - split across subgroups - is assembled at the end of the file.
_matr_app_group = matr.app_command
matr.app_command = None


@matr.command(name="help")
async def matr_help(ctx: commands.Context) -> None:
    """Show the command list."""
    bot = _bot(ctx)
    await ctx.reply(
        embed=_help_embed(ctx.prefix or "!", bot.config.command_name)
    )


# ---------------------------------------------------------------------------
# Marriage
# ---------------------------------------------------------------------------


@matr.command(name="marry", aliases=["propose"])
@commands.guild_only()
@app_commands.guild_only()
async def matr_marry(ctx: commands.Context, user: discord.User) -> None:
    """Propose marriage to another user - or bot."""
    bot = _bot(ctx)
    now = int(time.time())
    if bot.store.is_jailed(ctx.author.id, now) and bot.store.is_jailed(
        user.id, now
    ):
        # Two inmates: jail rules (no incest/cap checks), jail tables.
        error = jail_mod.check_jail_marry(
            bot.store, ctx.author.id, user.id
        )
        await _send_proposal(ctx, user, "marry", error, jail_pair=True)
        return
    error = bot.family.check_marry(
        ctx.author.id,
        user.id,
        allow_incest=bot.store.get_allow_incest(ctx.guild.id),
        max_partners=bot.config.max_partners,
    )
    await _send_proposal(ctx, user, "marry", error)


@matr.command(name="divorce")
@commands.guild_only()
@app_commands.guild_only()
async def matr_divorce(
    ctx: commands.Context, user: discord.User | None = None
) -> None:
    """Divorce a partner. Required if you have several."""
    bot = _bot(ctx)
    partners = bot.store.partners_of(ctx.author.id)
    if user is None:
        if len(partners) == 1:
            target = partners[0]
        elif not partners:
            await _say(ctx, "You're not married to anyone.", ok=False)
            return
        else:
            await _say(
                ctx,
                "You have multiple partners - mention which one to divorce.",
                ok=False,
            )
            return
    else:
        target = user.id
    if target not in partners:
        await _say(ctx, "You're not married to them.", ok=False)
        return
    if await _jail_block(ctx, target):
        return
    bot.store.remove_partners(ctx.author.id, target)
    gif = await bot.gifs.fetch_url("cry")
    await _say(
        ctx,
        f"{ctx.author.mention} and <@{target}> are now divorced. "
        ":broken_heart:",
        image=gif,
    )


@matr.command(name="accept")
async def matr_accept(
    ctx: commands.Context, proposer: discord.User | None = None
) -> None:
    """Accept a pending proposal or partner notice (usable in DMs)."""
    item = await _pick_answerable(ctx, proposer)
    if isinstance(item, Proposal):
        await _resolve_proposal(_bot(ctx), ctx, item.id, accepted=True)
    elif isinstance(item, Notice):
        await _resolve_notice(_bot(ctx), ctx, item.id, accepted=True)


@matr.command(name="decline", aliases=["deny"])
async def matr_decline(
    ctx: commands.Context, proposer: discord.User | None = None
) -> None:
    """Decline a pending proposal."""
    bot = _bot(ctx)
    pending = bot.store.proposals_for(ctx.author.id)
    if proposer is not None:
        pending = [p for p in pending if p.proposer == proposer.id]
    if not pending:
        if bot.store.notices_for(ctx.author.id):
            cmd = bot.config.command_name
            await _say(
                ctx,
                "No proposals to decline - but you have a new-partner notice. "
                f"Acknowledge it with `{ctx.prefix}{cmd} accept` or leave "
                f"the marriage with `{ctx.prefix}{cmd} divorce @partner`.",
                ok=False,
            )
        else:
            await _say(
                ctx, "You have no pending proposals to answer.", ok=False
            )
        return
    if len(pending) > 1:
        await _say(
            ctx,
            "You have multiple pending proposals - mention the proposer to "
            "pick one.",
            ok=False,
        )
        return
    await _resolve_proposal(bot, ctx, pending[0].id, accepted=False)


@matr.command(name="partners", aliases=["spouse", "spouses", "partner"])
async def matr_partners(
    ctx: commands.Context, user: discord.User | None = None
) -> None:
    """Show a user's partners (defaults to you)."""
    bot = _bot(ctx)
    uid = user.id if user else ctx.author.id
    partners = bot.store.partners_of(uid)
    if not partners:
        who = "You have" if user is None else f"{_display(user, ctx.author.id)} has"
        await _say(ctx, f"{who} no partners.", ok=False)
        return
    listing = ", ".join(f"<@{p}>" for p in partners)
    whose = "Your" if user is None else f"{_display(user, ctx.author.id)}'s"
    await _say(ctx, f"{whose} partners: {listing}")


# ---------------------------------------------------------------------------
# Parentage
# ---------------------------------------------------------------------------


@matr.command(name="adopt")
@commands.guild_only()
@app_commands.guild_only()
async def matr_adopt(ctx: commands.Context, user: discord.User) -> None:
    """Propose adopting a user (or bot) as your child."""
    bot = _bot(ctx)
    now = int(time.time())
    if bot.store.is_jailed(ctx.author.id, now) and bot.store.is_jailed(
        user.id, now
    ):
        error = jail_mod.check_jail_adopt(
            bot.store, ctx.author.id, user.id
        )
        await _send_proposal(ctx, user, "adopt", error, jail_pair=True)
        return
    error = bot.family.check_adopt(
        ctx.author.id,
        user.id,
        allow_incest=bot.store.get_allow_incest(ctx.guild.id),
        max_children=bot.config.max_children,
    )
    await _send_proposal(ctx, user, "adopt", error)


@matr.command(name="makeparent")
@commands.guild_only()
@app_commands.guild_only()
async def matr_makeparent(ctx: commands.Context, user: discord.User) -> None:
    """Ask a user to become YOUR parent."""
    bot = _bot(ctx)
    now = int(time.time())
    if bot.store.is_jailed(ctx.author.id, now) and bot.store.is_jailed(
        user.id, now
    ):
        error = jail_mod.check_jail_adopt(
            bot.store, user.id, ctx.author.id
        )
        await _send_proposal(
            ctx, user, "makeparent", error, jail_pair=True
        )
        return
    error = bot.family.check_adopt(
        user.id,  # target becomes the parent
        ctx.author.id,  # you become the child
        allow_incest=bot.store.get_allow_incest(ctx.guild.id),
        max_children=bot.config.max_children,
    )
    await _send_proposal(ctx, user, "makeparent", error)


@matr.command(name="disown")
@commands.guild_only()
@app_commands.guild_only()
async def matr_disown(ctx: commands.Context, child: discord.User) -> None:
    """Disown one of your children."""
    bot = _bot(ctx)
    if await _jail_block(ctx, child.id):
        return
    if bot.store.parent_of(child.id) != ctx.author.id:
        await _say(ctx, "They're not your child.", ok=False)
        return
    bot.store.remove_child(child.id)
    await _say(ctx, f"You've disowned {child.mention}.")


@matr.command(name="disownall")
@commands.guild_only()
@app_commands.guild_only()
async def matr_disownall(ctx: commands.Context) -> None:
    """Disown all of your children at once."""
    bot = _bot(ctx)
    children = bot.store.children_of(ctx.author.id)
    if not children:
        await _say(ctx, "You have no children.", ok=False)
        return
    for c in children:
        bot.store.remove_child(c)
    await _say(ctx, f"Disowned {len(children)} children. Cold.")


@matr.command(name="emancipate", aliases=["runaway"])
@commands.guild_only()
@app_commands.guild_only()
async def matr_emancipate(ctx: commands.Context) -> None:
    """Remove your parent (run away from home)."""
    bot = _bot(ctx)
    parent = bot.store.parent_of(ctx.author.id)
    if parent is None:
        await _say(ctx, "You don't have a parent.", ok=False)
        return
    bot.store.remove_child(ctx.author.id)
    await _say(ctx, f"You're now free of <@{parent}>. Go forth.")


@matr.command(name="abandon")
@commands.guild_only()
@app_commands.guild_only()
async def matr_abandon(ctx: commands.Context) -> None:
    """Remove ALL your family ties: partners, parent and children."""
    bot = _bot(ctx)
    uid = ctx.author.id
    partners = bot.store.partners_of(uid)
    children = bot.store.children_of(uid)
    parent = bot.store.parent_of(uid)
    if not partners and not children and parent is None:
        await _say(ctx, "You have no family to abandon.", ok=False)
        return
    for p in partners:
        bot.store.remove_partners(uid, p)
    for c in children:
        bot.store.remove_child(c)
    if parent is not None:
        bot.store.remove_child(uid)
    await _say(
        ctx,
        f"{ctx.author.mention} abandoned their whole family "
        f"({len(partners)} partner(s), {len(children)} child(ren), "
        f"{1 if parent is not None else 0} parent).",
    )


# ---------------------------------------------------------------------------
# Trees and info
# ---------------------------------------------------------------------------


@matr.command(name="tree")
async def matr_tree(ctx: commands.Context, user: discord.User | None = None) -> None:
    """Show a user's blood family tree."""
    bot = _bot(ctx)
    uid = user.id if user else ctx.author.id
    text = bot.family.render_tree(
        uid,
        _name_of(bot, ctx.guild),
        include_spouses=False,
        max_depth=bot.config.max_tree_depth,
    )
    await ctx.reply(embed=_embed(text))


@matr.command(name="fulltree")
async def matr_fulltree(
    ctx: commands.Context, user: discord.User | None = None
) -> None:
    """Show a user's full family tree including partners."""
    bot = _bot(ctx)
    uid = user.id if user else ctx.author.id
    text = bot.family.render_tree(
        uid,
        _name_of(bot, ctx.guild),
        include_spouses=True,
        max_depth=bot.config.max_tree_depth,
    )
    await ctx.reply(embed=_embed(text))


def _solo_line(
    ctx: commands.Context, user: discord.User | None, label: str, ids: list[int]
) -> str:
    who = "You have" if user is None else f"{_display(user, ctx.author.id)} has"
    if not ids:
        return f"{who} no {label}."
    listing = ", ".join(f"<@{i}>" for i in ids)
    whose = "Your" if user is None else f"{_display(user, ctx.author.id)}'s"
    return f"{whose} {label}: {listing}"


@matr.command(name="parent")
async def matr_parent(ctx: commands.Context, user: discord.User | None = None) -> None:
    """Show a user's parent."""
    bot = _bot(ctx)
    uid = user.id if user else ctx.author.id
    parent = bot.store.parent_of(uid)
    await _say(
        ctx,
        _solo_line(ctx, user, "parent", [parent] if parent is not None else []),
        ok=parent is not None,
    )


@matr.command(name="children")
async def matr_children(
    ctx: commands.Context, user: discord.User | None = None
) -> None:
    """Show a user's children."""
    bot = _bot(ctx)
    uid = user.id if user else ctx.author.id
    children = bot.store.children_of(uid)
    await _say(ctx, _solo_line(ctx, user, "children", children), ok=bool(children))


@matr.command(name="siblings")
async def matr_siblings(
    ctx: commands.Context, user: discord.User | None = None
) -> None:
    """Show a user's siblings (other children of their parent)."""
    bot = _bot(ctx)
    uid = user.id if user else ctx.author.id
    sibs = bot.family.siblings(uid)
    await _say(ctx, _solo_line(ctx, user, "siblings", sibs), ok=bool(sibs))


@matr.command(name="familysize")
async def matr_familysize(
    ctx: commands.Context, user: discord.User | None = None
) -> None:
    """Show the number of people in a user's family tree."""
    bot = _bot(ctx)
    uid = user.id if user else ctx.author.id
    size = bot.store.family_size(uid)
    who = "You have" if user is None else f"{_display(user, ctx.author.id)} has"
    await _say(ctx, f"{who} {size} family member(s).")


@matr.command(name="relationship")
async def matr_relationship(
    ctx: commands.Context, a: discord.User, b: discord.User
) -> None:
    """Show how user B is related to user A."""
    bot = _bot(ctx)
    rel = bot.family.relationship(a.id, b.id)
    if rel is None:
        await _say(ctx, f"{a.mention} and {b.mention} aren't related.")
    elif rel == "self":
        await _say(ctx, "That's... the same person.")
    else:
        await _say(ctx, f"{b.mention} is {a.mention}'s **{rel}**.")


# ---------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------


@matr.command(name="block")
async def matr_block(ctx: commands.Context, user: discord.User) -> None:
    """Block a user from sending you proposals."""
    bot = _bot(ctx)
    if await _jail_block(ctx, user.id):
        return
    if user.id == ctx.author.id:
        await _say(ctx, "You can't block yourself.", ok=False)
        return
    bot.store.add_block(ctx.author.id, user.id)
    await _say(ctx, f"Blocked {user.mention} from proposing to you.")


@matr.command(name="unblock")
async def matr_unblock(ctx: commands.Context, user: discord.User) -> None:
    """Unblock a user."""
    bot = _bot(ctx)
    if not bot.store.remove_block(ctx.author.id, user.id):
        await _say(ctx, "They weren't blocked.", ok=False)
        return
    await _say(ctx, f"Unblocked {user.mention}.")


@matr.command(name="blocked")
async def matr_blocked(ctx: commands.Context) -> None:
    """List everyone you've blocked."""
    bot = _bot(ctx)
    users = bot.store.blocked_users(ctx.author.id)
    if not users:
        await _say(ctx, "You haven't blocked anyone.", ok=False)
        return
    await _say(ctx, "Blocked: " + ", ".join(f"<@{u}>" for u in users))


# ---------------------------------------------------------------------------
# Restraining orders
# ---------------------------------------------------------------------------


@matr.command(name="restrain", aliases=["restrainingorder"])
@commands.guild_only()
@app_commands.guild_only()
async def matr_restrain(ctx: commands.Context, user: discord.User) -> None:
    """File a restraining order against a user for one hour.

    While it stands, any action they aim at you (marry, adopt,
    makeparent, hug/slap/poke/etc.) is blocked and you're asked whether
    to press charges - charges land them in jail. Re-filing renews
    the hour."""
    bot = _bot(ctx)
    if user.id == ctx.author.id:
        await _say(
            ctx,
            "You can't file a restraining order against yourself.",
            ok=False,
        )
        return
    if bot.user is not None and user.id == bot.user.id:
        await _say(
            ctx,
            "Matrimony files the paperwork around here, not the other "
            "way round.",
            ok=False,
        )
        return
    order = bot.store.file_restraining_order(
        ctx.guild.id,
        ctx.channel.id,
        ctx.author.id,
        user.id,
        ttl_seconds=bot.config.restraining_order_ttl_seconds,
    )
    await _say(
        ctx,
        f"Restraining order filed: {user.mention} can't target you with "
        f"proposals or actions until <t:{order.expires_at}:R>. If they "
        "try, you'll be asked whether to press charges - charges mean "
        "jail.",
    )


# ---------------------------------------------------------------------------
# Server configuration
# ---------------------------------------------------------------------------


@matr.command(name="prefix")
@commands.guild_only()
@app_commands.guild_only()
async def matr_prefix(ctx: commands.Context, new_prefix: str | None = None) -> None:
    """Show or set this server's command prefix (default ``!``).

    Changing it requires the Manage Server permission."""
    bot = _bot(ctx)
    if new_prefix is None:
        current = (
            bot.store.get_prefix(ctx.guild.id) or bot.config.default_prefix
        )
        await _say(
            ctx,
            f"This server's prefix is `{current}` "
            f"(e.g. `{current}{bot.config.command_name} marry @user`).",
        )
        return
    if not ctx.author.guild_permissions.manage_guild:
        await _say(
            ctx,
            "You need the Manage Server permission to change the prefix.",
            ok=False,
        )
        return
    if len(new_prefix) > 10 or any(c.isspace() for c in new_prefix):
        await _say(ctx, "Prefixes must be <=10 chars with no spaces.", ok=False)
        return
    bot.store.set_prefix(ctx.guild.id, new_prefix)
    await _say(
        ctx,
        f"Prefix set to `{new_prefix}`. "
        f"Try `{new_prefix}{bot.config.command_name} help`.",
    )


@matr.command(name="incest")
@commands.guild_only()
@app_commands.guild_only()
@commands.has_permissions(manage_guild=True)
@app_commands.default_permissions(manage_guild=True)
async def matr_incest(ctx: commands.Context) -> None:
    """Toggle whether family members may marry/adopt each other here."""
    bot = _bot(ctx)
    current = bot.store.get_allow_incest(ctx.guild.id)
    bot.store.set_allow_incest(ctx.guild.id, not current)
    await _say(
        ctx,
        "Incest proposals are now **"
        + ("allowed" if not current else "disallowed")
        + "** in this server.",
    )


# ---------------------------------------------------------------------------
# Admin force commands
# ---------------------------------------------------------------------------


@matr.command(name="forcemarry")
@commands.guild_only()
@app_commands.guild_only()
@commands.has_permissions(manage_guild=True)
@app_commands.default_permissions(manage_guild=True)
async def matr_forcemarry(
    ctx: commands.Context, a: discord.User, b: discord.User
) -> None:
    """Force-marry two users (no proposal needed)."""
    bot = _bot(ctx)
    if a.id == b.id:
        await _say(ctx, "A user can't marry themselves.", ok=False)
        return
    bot.store.add_partners(a.id, b.id)
    await _say(ctx, f"{a.mention} and {b.mention} are now married. :tada:")
    await _notify_new_partners(
        bot, ctx, a.id, b.id, ctx.guild.id, ctx.channel.id
    )


@matr.command(name="forcedivorce")
@commands.guild_only()
@app_commands.guild_only()
@commands.has_permissions(manage_guild=True)
@app_commands.default_permissions(manage_guild=True)
async def matr_forcedivorce(
    ctx: commands.Context, a: discord.User, b: discord.User | None = None
) -> None:
    """Force-divorce a pair (or all of A's partners if B omitted)."""
    bot = _bot(ctx)
    if b is None:
        partners = bot.store.partners_of(a.id)
        if not partners:
            await _say(ctx, "They have no partners.", ok=False)
            return
        for p in partners:
            bot.store.remove_partners(a.id, p)
        await _say(ctx, f"Divorced {a.mention} from {len(partners)} partner(s).")
        return
    if not bot.store.remove_partners(a.id, b.id):
        await _say(ctx, "They aren't married.", ok=False)
        return
    await _say(ctx, f"Divorced {a.mention} and {b.mention}.")


@matr.command(name="forceadopt")
@commands.guild_only()
@app_commands.guild_only()
@commands.has_permissions(manage_guild=True)
@app_commands.default_permissions(manage_guild=True)
async def matr_forceadopt(
    ctx: commands.Context, parent: discord.User, child: discord.User
) -> None:
    """Force ``child`` to become ``parent``'s child.

    Skips consent/blocks/relation checks but never the structural rules
    (no self-adoption, no cycles, one parent per child)."""
    bot = _bot(ctx)
    if parent.id == child.id:
        await _say(ctx, "A user can't adopt themselves.", ok=False)
        return
    existing = bot.store.parent_of(child.id)
    if existing is not None:
        await _say(ctx, "They already have a parent.", ok=False)
        return
    if (
        child.id in bot.family.ancestors(parent.id)
        or parent.id in bot.family.ancestors(child.id)
    ):
        await _say(ctx, "That would create a family loop.", ok=False)
        return
    if bot.store.add_child(parent.id, child.id):
        await _say(ctx, f"{child.mention} is now {parent.mention}'s child.")
    else:
        await _say(ctx, "They already have a parent.", ok=False)


@matr.command(name="forceemancipate")
@commands.guild_only()
@app_commands.guild_only()
@commands.has_permissions(manage_guild=True)
@app_commands.default_permissions(manage_guild=True)
async def matr_forceemancipate(ctx: commands.Context, child: discord.User) -> None:
    """Force-remove a user's parent."""
    bot = _bot(ctx)
    if bot.store.parent_of(child.id) is None:
        await _say(ctx, "They have no parent.", ok=False)
        return
    bot.store.remove_child(child.id)
    await _say(ctx, f"Emancipated {child.mention}.")


@matr.command(name="clear")
@commands.guild_only()
@app_commands.guild_only()
@commands.has_permissions(manage_guild=True)
@app_commands.default_permissions(manage_guild=True)
async def matr_clear(ctx: commands.Context) -> None:
    """Reset this server's Matrimony state (Manage Server only).

    Shows a warning first: it only runs after the invoking admin presses
    Confirm within 60 seconds."""
    view = ClearConfirmView(ctx.author.id, ctx.guild.id)
    view.message = await ctx.reply(
        embed=_embed(
            f"**Reset this server's Matrimony state?**\n\n{_CLEAR_SCOPE}",
            RED,
        ),
        view=view,
    )


# ---------------------------------------------------------------------------
# Fun (simulation) commands
# ---------------------------------------------------------------------------

# name -> (past-tense verb, emoji, Fluxpoint gif type)
_FUN_VERBS = {
    "hug": ("hugs", ":hugging:", "hug"),
    # Fluxpoint has no "cuddle" endpoint; hug is the same gesture.
    "cuddle": ("cuddles", ":people_hugging:", "hug"),
    "kiss": ("kisses", ":kissing_heart:", "kiss"),
    "pat": ("pats", ":hand_splayed:", "pat"),
    "poke": ("pokes", ":point_right:", "poke"),
    "wave": ("waves at", ":wave:", "wave"),
    "lick": ("licks", ":tongue:", "lick"),
    # Fluxpoint has no "nom" endpoint; feed is the same gesture.
    "nom": ("noms", ":yum:", "feed"),
    "tickle": ("tickles", ":raised_hand:", "tickle"),
    "highfive": ("high-fives", ":raised_hands:", "highfive"),
    "handhold": ("holds hands with", ":handshake:", "handhold"),
    "slap": ("slaps", ":raised_back_of_hand:", "slap"),
    "punch": ("punches", ":punch:", "punch"),
    "bite": ("bites", ":tooth:", "bite"),
    # Fluxpoint has no "stab" endpoint; punch is the closest violent action.
    "stab": ("stabs", ":dagger:", "punch"),
}


def _make_fun(name: str) -> None:
    verb, emoji, gif_type = _FUN_VERBS[name]

    async def _fun(ctx: commands.Context, user: discord.User) -> None:
        if await _jail_block(ctx, user.id):
            return
        if await _restrain_block(ctx, user, name):
            return
        gif = await _bot(ctx).gifs.fetch_url(gif_type)
        if user.id == ctx.author.id:
            text = f"You {verb} yourself. Okay then. {emoji}"
        else:
            text = f"{ctx.author.mention} {verb} {user.mention}! {emoji}"
        await _say(ctx, _quipped(ctx, user, text, name), image=gif)

    _fun.__doc__ = f"{name.capitalize()} another user."
    # Set the docstring before decorating so the slash command gets a
    # description too.
    matr.command(name=name)(_fun)


for _verb_name in _FUN_VERBS:
    _make_fun(_verb_name)


@matr.command(name="ship")
async def matr_ship(
    ctx: commands.Context, a: discord.User, b: discord.User | None = None
) -> None:
    """Show the drifting ship percentage between two users."""
    bot = _bot(ctx)
    b = b or ctx.author
    now = time.time()
    pct = ship_score(
        a.id,
        b.id,
        now=now,
        message_count=bot.channel_activity.count(ctx.channel.id, now),
    )
    gif = await bot.gifs.fetch_url("handhold")
    text = f"{a.mention} x {b.mention}: **{pct}%** :heart:"
    if _is_matrimony(ctx, a) or _is_matrimony(ctx, b):
        text += f"\n-# {_quip('ship')}"
    await _say(ctx, text, image=gif)


_PICKUP_LINES = (
    "Are you a prefix? Because everything I say starts with you.",
    "Are you a rate limit? Because you leave me wanting more.",
    "Is your name Wi-Fi? Because I'm feeling a connection.",
    "Are you a pending proposal? I've been thinking about you for "
    "300 seconds.",
    "You must be a family tree, because I keep branching toward you.",
    "Are you a migration? Because my schema changed when I saw you.",
    "If you were a discord.py update, I'd pin you immediately.",
    "Are you an embed? Because you look great in my timeline.",
)

_DATE_IDEAS = (
    "to a candlelit debugging session, bugs provided free of charge",
    "stargazing at the voice channel member list",
    "to split one RAM upgrade, romantically",
    "on a couples' refactor: you hold the TODOs, they hold your heart",
    "to the edge of the render distance and back",
    "for a slow scroll through each other's pinned messages",
    "to dinner in the guild's AFK channel, it's quiet there",
)


@matr.command(name="flirt", aliases=["rizz"])
async def matr_flirt(ctx: commands.Context, user: discord.User) -> None:
    """Drop a terrible pickup line on someone."""
    bot = _bot(ctx)
    if await _jail_block(ctx, user.id):
        return
    if await _restrain_block(ctx, user, "flirt"):
        return
    line = random.choice(_PICKUP_LINES)
    gif = await bot.gifs.fetch_url("wink")
    text = f"{ctx.author.mention} to {user.mention}: *{line}*"
    await _say(ctx, _quipped(ctx, user, text, "flirt"), image=gif)


@matr.command(name="date", aliases=["dateidea"])
async def matr_date(ctx: commands.Context, user: discord.User) -> None:
    """Invent a terrible date for you and someone."""
    bot = _bot(ctx)
    if await _jail_block(ctx, user.id):
        return
    if await _restrain_block(ctx, user, "date"):
        return
    idea = random.choice(_DATE_IDEAS)
    gif = await bot.gifs.fetch_url("hug")
    text = f"{ctx.author.mention} takes {user.mention} {idea}."
    await _say(ctx, _quipped(ctx, user, text, "date"), image=gif)


def _fmt_duration(seconds: float) -> str:
    s = int(seconds)
    days, s = divmod(s, 86400)
    hours, s = divmod(s, 3600)
    minutes, s = divmod(s, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {s}s"
    return f"{s}s"


def _anniversary_note(seconds: float) -> str:
    if seconds < 300:
        return "The paperwork is still warm."
    if seconds < 86400:
        return "Still in the honeymoon phase."
    if seconds < 30 * 86400:
        return "Past the paper anniversary, into cardboard territory."
    if seconds < 365 * 86400:
        return "A love story for the ages, verified by SQLite."
    return "SQLite remembers. So should you."


@matr.command(name="anniversary", aliases=["anniv"])
async def matr_anniversary(
    ctx: commands.Context, user: discord.User | None = None
) -> None:
    """How long you've been married to a partner."""
    bot = _bot(ctx)
    partners = bot.store.partners_of(ctx.author.id)
    if user is None:
        if len(partners) == 1:
            target = partners[0]
        elif not partners:
            await _say(ctx, "You're not married to anyone.", ok=False)
            return
        else:
            await _say(
                ctx,
                "You have multiple partners - mention which one's "
                "anniversary you want.",
                ok=False,
            )
            return
    else:
        target = user.id
    since = bot.store.partnership_since(ctx.author.id, target)
    if since is None:
        await _say(ctx, "You're not married to them.", ok=False)
        return
    elapsed = time.time() - since
    gif = await bot.gifs.fetch_url("kiss")
    await _say(
        ctx,
        f"{ctx.author.mention} and <@{target}> have been married for "
        f"**{_fmt_duration(elapsed)}**. {_anniversary_note(elapsed)}",
        image=gif,
    )


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------


@matr.command(name="info")
async def matr_info(ctx: commands.Context) -> None:
    """Bot information and links."""
    bot = _bot(ctx)
    await ctx.reply(
        embed=discord.Embed(
            title="Matrimony",
            description=(
                "A MarriageBot-style family-tree bot: marriages, divorces, "
                "adoptions and global family trees. Works for humans and "
                "bots alike.\n\n"
                f"Commands: `{ctx.prefix}{bot.config.command_name} help`\n"
                "Source: https://github.com/CommunityPokeOrg/matrimony"
            ),
            colour=GOLD,
        ).set_footer(text=f"Matrimony v{__version__} - discord.py v{discord.__version__}")
    )


@matr.command(name="invite")
async def matr_invite(ctx: commands.Context) -> None:
    """Get the bot's invite link."""
    bot = _bot(ctx)
    if bot.user is None:
        await _say(ctx, "Not connected yet.", ok=False)
        return
    url = discord.utils.oauth_url(
        bot.user.id,
        permissions=discord.Permissions(
            send_messages=True,
            embed_links=True,
            read_message_history=True,
            add_reactions=True,
        ),
    )
    await _say(ctx, f"[Invite Matrimony]({url})")


@matr.command(name="stats")
async def matr_stats(ctx: commands.Context) -> None:
    """Bot statistics."""
    bot = _bot(ctx)
    s = bot.store.stats()
    await ctx.reply(
        embed=discord.Embed(
            title="Matrimony stats",
            colour=GOLD,
            description=(
                f"Guilds: **{len(bot.guilds)}**\n"
                f"Marriages: **{s['marriages']}**\n"
                f"Parent-child links: **{s['parent_child_links']}**\n"
                f"Open proposals: **{s['open_proposals']}**\n"
                f"Partner notices: **{s['partner_notices']}**\n"
                f"Restraining orders: **{s['restraining_orders']}**\n"
                f"Inmates: **{s['inmates']}**"
            ),
        )
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


# Slash layout for /matr: the core family commands live directly under the
# group, and the rest go into one-level subgroups so no group exceeds
# Discord's 25-child limit.
_TOP_APP_COMMANDS = (
    "marry",
    "divorce",
    "accept",
    "decline",
    "partners",
    "adopt",
    "makeparent",
    "disown",
    "disownall",
    "emancipate",
    "abandon",
    "tree",
    "fulltree",
    "parent",
    "children",
    "siblings",
    "familysize",
    "relationship",
    "block",
    "unblock",
    "blocked",
    "restrain",
)

_APP_SUBGROUPS = (
    (
        "fun",
        "Gifs, quips and other silliness.",
        (
            "hug",
            "cuddle",
            "kiss",
            "pat",
            "poke",
            "wave",
            "lick",
            "nom",
            "tickle",
            "highfive",
            "handhold",
            "slap",
            "punch",
            "bite",
            "stab",
            "ship",
            "flirt",
            "date",
            "anniversary",
        ),
    ),
    (
        "admin",
        "Server admin commands.",
        (
            "prefix",
            "incest",
            "forcemarry",
            "forcedivorce",
            "forceadopt",
            "forceemancipate",
            "clear",
        ),
    ),
    (
        "meta",
        "Bot information commands.",
        ("help", "info", "invite", "stats"),
    ),
)

matr.app_command = _matr_app_group
for _name in _TOP_APP_COMMANDS:
    _matr_app_group.add_command(matr.get_command(_name).app_command)
for _sub_name, _sub_desc, _sub_commands in _APP_SUBGROUPS:
    _sub = app_commands.Group(name=_sub_name, description=_sub_desc)
    for _name in _sub_commands:
        _sub.add_command(matr.get_command(_name).app_command)
    _matr_app_group.add_command(_sub)


async def _announce_expiry(
    bot: MatrimonyBot, report: jail_mod.ExpiryReport
) -> None:
    """Post the sweep's expiry/release notices to the channels on record.

    Order lapses announce in the channel the order was filed in; releases
    (and the jail-relationship dissolutions they cause) announce where
    the sentence was handed down. Missing/deleted channels are skipped."""
    for order in report.expired_orders:
        channel = bot.get_channel(order.channel_id)
        if channel is None:
            continue
        try:
            await channel.send(
                embed=_embed(
                    f"The restraining order protecting "
                    f"<@{order.protected}> against <@{order.restrained}> "
                    f"has expired."
                )
            )
        except discord.HTTPException:
            continue
    for rel in report.released:
        channel = bot.get_channel(rel.sentence.channel_id)
        if channel is None:
            continue
        served = rel.sentence.release_at - rel.sentence.jailed_at
        lines = [
            f"<@{rel.sentence.inmate}> has served their "
            f"{_fmt_duration(served)} sentence and is released.\n"
            f"-# {_quip('release')}"
        ]
        for partner in rel.divorced:
            lines.append(
                f"<@{rel.sentence.inmate}> and <@{partner}> were "
                f"divorced on release. -# {_quip('dissolve')}"
            )
        for child in rel.children_lost:
            lines.append(
                f"<@{child}> was abandoned - their jail parent "
                f"<@{rel.sentence.inmate}> was released. "
                f"-# {_quip('dissolve')}"
            )
        if rel.parent_lost is not None:
            lines.append(
                f"<@{rel.sentence.inmate}>'s jail parent "
                f"<@{rel.parent_lost}> is left inside - adoption "
                f"dissolved. -# {_quip('dissolve')}"
            )
        try:
            await channel.send(embed=_embed("\n".join(lines)))
        except discord.HTTPException:
            continue


class MatrCog(commands.Cog):
    def __init__(self, bot: MatrimonyBot) -> None:
        self.bot = bot
        matr.name = bot.config.command_name
        matr.app_command.name = bot.config.command_name
        bot.add_command(matr)

    async def cog_load(self) -> None:
        self.expiry_sweep.change_interval(
            seconds=self.bot.config.jail_sweep_seconds
        )
        self.expiry_sweep.start()

    async def cog_unload(self) -> None:
        self.expiry_sweep.cancel()

    @tasks.loop(seconds=20)
    async def expiry_sweep(self) -> None:
        """Lapse restraining orders and release finished sentences."""
        report = jail_mod.sweep_expiry(self.bot.store, int(time.time()))
        if report.expired_orders or report.released:
            await _announce_expiry(self.bot, report)

    @expiry_sweep.before_loop
    async def _before_sweep(self) -> None:
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_command_error(
        self, ctx: commands.Context, error: commands.CommandError
    ) -> None:
        error = getattr(error, "original", error)
        if isinstance(error, commands.CommandNotFound):
            # Unknown `!matr <action>` -> a quip plus the help embed.
            # (Usually the group callback answers this first via
            # ``subcommand_passed``; this path catches any other
            # CommandNotFound raised against the matr group.)
            content = ctx.message.content.split()
            if len(content) >= 2 and content[0].endswith(self.bot.config.command_name):
                await ctx.reply(
                    content=_quip("unknown"),
                    embed=_help_embed(ctx.prefix or "!", self.bot.config.command_name),
                )
            return
        if isinstance(error, commands.MissingRequiredArgument):
            await _say(ctx, f"Missing argument: `{error.param.name}`.", False)
        elif isinstance(error, commands.BadArgument):
            await _say(ctx, str(error), False)
        elif isinstance(error, commands.MissingPermissions):
            await _say(
                ctx, "You need the Manage Server permission for that.", False
            )
        elif isinstance(error, commands.NoPrivateMessage):
            await _say(ctx, "That command only works in a server.", False)
        elif isinstance(error, commands.CheckFailure):
            await _say(ctx, "You can't use that command.", False)
        else:
            await _say(ctx, "Something went wrong running that command.", False)
            raise error
