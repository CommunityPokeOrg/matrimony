"""The ``matr`` command group: all of Matrimony's commands.

Commands are module-level functions attached to a shared ``matr`` Group so
the file stays easy to navigate; ``MatrCog`` registers the group (under the
configured command name) and owns the error handler.
"""

from __future__ import annotations

import hashlib

import discord
from discord.ext import commands

from .. import __version__
from ..bot import MatrimonyBot
from ..store import Proposal

GREEN = discord.Color(0x2ECC71)
RED = discord.Color(0xE74C3C)
GOLD = discord.Color(0xF1C40F)


def _bot(ctx: commands.Context) -> MatrimonyBot:
    return ctx.bot  # type: ignore[return-value]


def _embed(text: str, colour: discord.Color = GREEN) -> discord.Embed:
    return discord.Embed(description=text, colour=colour)


async def _say(ctx: commands.Context, text: str, ok: bool = True) -> None:
    await ctx.reply(embed=_embed(text, GREEN if ok else RED))


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


async def _respond(ctx_or_interaction, text: str, ok: bool) -> None:
    emb = _embed(text, GREEN if ok else RED)
    if isinstance(ctx_or_interaction, discord.Interaction):
        if ctx_or_interaction.response.is_done():
            await ctx_or_interaction.followup.send(embed=emb)
        else:
            await ctx_or_interaction.response.send_message(embed=emb)
    else:
        await ctx_or_interaction.reply(embed=emb)


# ---------------------------------------------------------------------------
# Proposal flow
# ---------------------------------------------------------------------------

PROPOSAL_VERBS = {
    "marry": "marry",
    "adopt": "adopt",
    "makeparent": "become the parent of",
}


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
    proposer = _name_of(bot, None)(proposal.proposer)
    target = _name_of(bot, None)(proposal.target)
    if proposal.kind == "marry":
        bot.store.add_partners(proposal.proposer, proposal.target)
        await _respond(
            ctx_or_int,
            f"{proposer} and {target} are now married! :tada:",
            True,
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


async def _send_proposal(
    ctx: commands.Context,
    target: discord.User | discord.Member,
    kind: str,
    error: str | None,
) -> None:
    """Shared entry for marry/adopt/makeparent."""
    if error:
        await _say(ctx, error, ok=False)
        return
    bot = _bot(ctx)
    proposal = bot.store.create_proposal(
        ctx.guild.id if ctx.guild else 0,
        ctx.channel.id,
        ctx.author.id,
        target.id,
        kind,
        bot.config.proposal_ttl_seconds,
    )
    if proposal is None:
        await _say(ctx, "You already have a pending proposal for them.", ok=False)
        return
    verb = PROPOSAL_VERBS[kind]
    cmd = bot.config.command_name
    await ctx.reply(
        embed=_embed(
            f"{ctx.author.mention} wants to {verb} {target.mention}!\n"
            f"Accept with the buttons below or `{ctx.prefix}{cmd} accept "
            f"{ctx.author.mention}` (decline likewise). Proposals expire "
            f"after {bot.config.proposal_ttl_seconds // 60} minutes.",
            GOLD,
        ),
        view=ProposalView(proposal, timeout=bot.config.proposal_ttl_seconds),
    )


async def _pick_proposal(
    ctx: commands.Context, proposer: discord.User | None
) -> Proposal | None:
    """Find the proposal ``ctx.author`` wants to act on."""
    pending = _bot(ctx).store.proposals_for(ctx.author.id)
    if proposer is not None:
        pending = [p for p in pending if p.proposer == proposer.id]
    if not pending:
        await _say(ctx, "You have no pending proposals to answer.", ok=False)
        return None
    if len(pending) > 1:
        await _say(
            ctx,
            "You have multiple pending proposals - mention the proposer to "
            "pick one.",
            ok=False,
        )
        return None
    return pending[0]


def _help_embed(prefix: str, cmd: str) -> discord.Embed:
    return discord.Embed(
        title="Matrimony",
        description=(
            f"MarriageBot-style family trees. Commands: `{prefix}{cmd} "
            "<action>`.\n\n"
            "**Love**\n"
            "`marry @user` propose - `divorce [@user]` - "
            "`accept`/`decline [@user]` - `partners [@user]`\n"
            "**Parentage**\n"
            "`adopt @user` - `makeparent @user` - `disown @child` - "
            "`disownall` - `emancipate` - `abandon`\n"
            "**Trees**\n"
            "`tree [@user]` - `fulltree [@user]` - `parent [@user]` - "
            "`children [@user]` - `siblings [@user]` - `familysize [@user]` - "
            "`relationship @a @b`\n"
            "**Blocks**\n"
            "`block @user` - `unblock @user` - `blocked`\n"
            "**Server** *(Manage Server)*\n"
            "`prefix <new>` - `incest` - `forcemarry @a @b` - "
            "`forcedivorce @a [@b]` - `forceadopt @parent @child` - "
            "`forceemancipate @user`\n"
            "**Fun**\n"
            "`hug`/`kiss`/`slap`/`punch`/`bite`/`stab @user` - `ship @a @b`\n"
            "**Meta**\n"
            "`info` - `invite` - `stats`\n\n"
            "Family trees are global across servers, and bot accounts can "
            "use commands and be married or adopted."
        ),
        colour=GOLD,
    )


# ---------------------------------------------------------------------------
# The group
# ---------------------------------------------------------------------------


@commands.group(
    name="matr",
    invoke_without_command=True,
    help="Matrimony family-tree commands.",
)
async def matr(ctx: commands.Context) -> None:
    """Bare ``!matr`` shows help."""
    bot = _bot(ctx)
    await ctx.reply(
        embed=_help_embed(ctx.prefix or "!", bot.config.command_name)
    )


@matr.command(name="help")
async def matr_help(ctx: commands.Context) -> None:
    bot = _bot(ctx)
    await ctx.reply(
        embed=_help_embed(ctx.prefix or "!", bot.config.command_name)
    )


# ---------------------------------------------------------------------------
# Marriage
# ---------------------------------------------------------------------------


@matr.command(name="marry", aliases=["propose"])
@commands.guild_only()
async def matr_marry(ctx: commands.Context, user: discord.User) -> None:
    """Propose marriage to another user - or bot."""
    bot = _bot(ctx)
    error = bot.family.check_marry(
        ctx.author.id,
        user.id,
        allow_incest=bot.store.get_allow_incest(ctx.guild.id),
        max_partners=bot.config.max_partners,
    )
    await _send_proposal(ctx, user, "marry", error)


@matr.command(name="divorce")
@commands.guild_only()
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
    bot.store.remove_partners(ctx.author.id, target)
    await _say(
        ctx,
        f"{ctx.author.mention} and <@{target}> are now divorced. "
        ":broken_heart:",
    )


@matr.command(name="accept")
async def matr_accept(
    ctx: commands.Context, proposer: discord.User | None = None
) -> None:
    """Accept a pending proposal (usable in DMs)."""
    proposal = await _pick_proposal(ctx, proposer)
    if proposal:
        await _resolve_proposal(_bot(ctx), ctx, proposal.id, accepted=True)


@matr.command(name="decline", aliases=["deny"])
async def matr_decline(
    ctx: commands.Context, proposer: discord.User | None = None
) -> None:
    """Decline a pending proposal."""
    proposal = await _pick_proposal(ctx, proposer)
    if proposal:
        await _resolve_proposal(_bot(ctx), ctx, proposal.id, accepted=False)


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
async def matr_adopt(ctx: commands.Context, user: discord.User) -> None:
    """Propose adopting a user (or bot) as your child."""
    bot = _bot(ctx)
    error = bot.family.check_adopt(
        ctx.author.id,
        user.id,
        allow_incest=bot.store.get_allow_incest(ctx.guild.id),
        max_children=bot.config.max_children,
    )
    await _send_proposal(ctx, user, "adopt", error)


@matr.command(name="makeparent")
@commands.guild_only()
async def matr_makeparent(ctx: commands.Context, user: discord.User) -> None:
    """Ask a user to become YOUR parent."""
    bot = _bot(ctx)
    error = bot.family.check_adopt(
        user.id,  # target becomes the parent
        ctx.author.id,  # you become the child
        allow_incest=bot.store.get_allow_incest(ctx.guild.id),
        max_children=bot.config.max_children,
    )
    await _send_proposal(ctx, user, "makeparent", error)


@matr.command(name="disown")
@commands.guild_only()
async def matr_disown(ctx: commands.Context, child: discord.User) -> None:
    """Disown one of your children."""
    bot = _bot(ctx)
    if bot.store.parent_of(child.id) != ctx.author.id:
        await _say(ctx, "They're not your child.", ok=False)
        return
    bot.store.remove_child(child.id)
    await _say(ctx, f"You've disowned {child.mention}.")


@matr.command(name="disownall")
@commands.guild_only()
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
# Server configuration
# ---------------------------------------------------------------------------


@matr.command(name="prefix")
@commands.guild_only()
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
@commands.has_permissions(manage_guild=True)
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
@commands.has_permissions(manage_guild=True)
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


@matr.command(name="forcedivorce")
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
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
@commands.has_permissions(manage_guild=True)
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
@commands.has_permissions(manage_guild=True)
async def matr_forceemancipate(ctx: commands.Context, child: discord.User) -> None:
    """Force-remove a user's parent."""
    bot = _bot(ctx)
    if bot.store.parent_of(child.id) is None:
        await _say(ctx, "They have no parent.", ok=False)
        return
    bot.store.remove_child(child.id)
    await _say(ctx, f"Emancipated {child.mention}.")


# ---------------------------------------------------------------------------
# Fun (simulation) commands
# ---------------------------------------------------------------------------

_FUN_VERBS = {
    "hug": ("hugs", ":hugging:"),
    "kiss": ("kisses", ":kissing_heart:"),
    "slap": ("slaps", ":raised_back_of_hand:"),
    "punch": ("punches", ":punch:"),
    "bite": ("bites", ":tooth:"),
    "stab": ("stabs", ":dagger:"),
}


def _make_fun(name: str) -> None:
    verb, emoji = _FUN_VERBS[name]

    @matr.command(name=name)
    async def _fun(ctx: commands.Context, user: discord.User) -> None:
        if user.id == ctx.author.id:
            await _say(ctx, f"You {verb} yourself. Okay then. {emoji}")
        else:
            await _say(ctx, f"{ctx.author.mention} {verb} {user.mention}! {emoji}")

    _fun.__doc__ = f"{name.capitalize()} another user."


for _verb_name in _FUN_VERBS:
    _make_fun(_verb_name)


@matr.command(name="ship")
async def matr_ship(
    ctx: commands.Context, a: discord.User, b: discord.User | None = None
) -> None:
    """Show a (deterministic) ship percentage between two users."""
    b = b or ctx.author
    lo, hi = sorted((a.id, b.id))
    pct = int(hashlib.md5(f"{lo}:{hi}".encode()).hexdigest()[:6], 16) % 101
    await _say(ctx, f"{a.mention} x {b.mention}: **{pct}%** :heart:")


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
                f"Open proposals: **{s['open_proposals']}**"
            ),
        )
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class MatrCog(commands.Cog):
    def __init__(self, bot: MatrimonyBot) -> None:
        self.bot = bot
        matr.name = bot.config.command_name
        bot.add_command(matr)

    @commands.Cog.listener()
    async def on_command_error(
        self, ctx: commands.Context, error: commands.CommandError
    ) -> None:
        error = getattr(error, "original", error)
        if isinstance(error, commands.CommandNotFound):
            # Unknown `!matr <action>` -> show help instead of silence.
            content = ctx.message.content.split()
            if len(content) >= 2 and content[0].endswith(self.bot.config.command_name):
                await ctx.reply(
                    content="Unknown action.",
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
