"""All of Matrimony's quips in one place, organized by where they show up.

Every command reply ends with one of these as ambient commentary - a
Discord subtext line (``-# ...``) appended to the end of the embed or
message. ``AMBIENT`` pools are keyed by the command or theme they comment
on; actions aimed at Matrimony itself draw from ``BOT`` instead, and a few
situations (unknown commands, restraining orders, jail, releases) have
their own named pools. The one-liner content commands keep their material
here too (``PICKUP_LINES``, ``DATE_IDEAS``, ``anniversary_note``).
"""

from __future__ import annotations

import itertools
import random

# ---------------------------------------------------------------------------
# Ambient quips: appended to the matching command's replies
# ---------------------------------------------------------------------------

AMBIENT: dict[str, list[str]] = {
    # Fallback for replies with no dedicated pool (errors, edge cases).
    "generic": [
        "the bot saw nothing, but it will gossip anyway",
        "noted, filed, and mildly judged",
        "the paperwork is unimpressed",
        "this is going in the server's permanent record",
        "even the family tree winced a little",
        "the council of spouses has been notified",
    ],
    # The "X wants to Y you!" proposal prompt and proposal errors.
    "proposal": [
        "the ring is imaginary, the commitment is not",
        "a yes costs nothing but a lifetime",
        "the bot is already crying into the confetti buffer",
        "no pressure, but the chapel only seats two",
    ],
    # A marriage went through (accepted or forced).
    "married": [
        "another merge conflict resolved by union",
        "the family tree gains a branch and a liability",
        "signed in triplicate, sealed with a react",
        "SQLite has been notified and approves",
    ],
    "divorce": [
        "the family tree prunes itself",
        "assets divided: they keep the memes",
        "a clean break - a rollback, in ACID terms",
        "the couple now owes each other only awkwardness",
    ],
    "accept": [
        "consent obtained, bureaucracy satisfied",
        "the yes was implied; now it's paperwork",
    ],
    "decline": [
        "rejected with grace and a paper trail",
        "the proposal has been respectfully yeeted",
        "love declined, dignity mostly intact",
    ],
    "partners": [
        "count them on one hand, or several",
        "a wholesome little polycule ledger",
        "the love is distributed evenly, we checked",
    ],
    # Adoptions and forced adoptions, both directions.
    "adopt": [
        "the tree grows by paperwork, not biology",
        "congrats on the new tax dependent",
        "parental duties include bedtime and lore",
    ],
    # disown / disownall
    "disown": [
        "the inheritance was always imaginary",
        "cut from the will; this message is the will",
        "family reunion attendance: minus one",
    ],
    # emancipate / runaway / forceemancipate
    "emancipate": [
        "the open road has no bedtime",
        "packed a bindle, left a note",
        "freedom tastes like unsupervised screen time",
    ],
    "abandon": [
        "scorched-earth family policy executed",
        "a clean slate and a cold heart",
        "the tree is now a stick",
    ],
    # tree / fulltree
    "tree": [
        "genetically accurate, spiritually questionable",
        "the roots are real; the trunk is SQLite",
        "rendered in glorious plain text, as intended",
    ],
    # parent / children / siblings / familysize / relationship
    "kin": [
        "family: the original group chat",
        "blood is thicker than bandwidth",
        "every family is normal until you render it",
    ],
    # block / unblock / blocked
    "block": [
        "boundaries: now machine-enforced",
        "the door is closed but the window is ajar",
        "proposals now bounce off the force field",
    ],
    # restraining orders filed, charges pressed or declined, sentencing.
    "law": [
        "the courtroom is a Discord channel, as tradition demands",
        "justice served at websocket speed",
        "the gavel is the banhammer's polite cousin",
        "order in the chat",
    ],
    # A restraining order lapsing on its own.
    "expired": [
        "the paperwork quietly self-destructs",
        "protection elapsed; vibes resume",
        "the order dissolves into the aether",
    ],
    # prefix / incest / clear and other server-admin replies.
    "admin": [
        "the sacred texts have been updated",
        "server settings bent to your will",
        "with great power comes great subtext",
        "the config trembles, then complies",
    ],
    # info / invite / stats
    "meta": [
        "powered by SQLite and unchecked optimism",
        "brought to you by the event loop",
        "running on vibes and a WAL file",
    ],
    # The GIF actions (hug..stab) aimed at ordinary users.
    "fun": [
        "the bot rates this interaction 10/10",
        "affection detected and logged",
        "this is what the sensors were installed for",
        "the gif was absolutely worth it",
        "recorded for the highlight reel",
    ],
    "ship": [
        "the oracle has spoken; ship it",
        "percentage computed by a committee of dice",
        "the algorithm ships it; the algorithm is wise",
        "results may drift, like the ship itself",
    ],
    "flirt": [
        "smooth as a segfault",
        "rizz levels legally distinct from zero",
        "that line has a 100% success rate at being said",
    ],
    "date": [
        "reservations are fake, the sentiment is real",
        "romance, now with 100% more planning debt",
        "the itinerary was peer reviewed and mocked",
    ],
    "anniversary": [
        "time flies when you're statically linked",
        "the records hold; so does the love",
        "SQLite remembers so you don't have to",
    ],
    # Jail proposals accepted on the inside.
    "jailwed": [
        "till release do us part",
        "witnessed by two guards and a camera",
        "the ring was fashioned from a spork",
        "love finds a way, even through bars",
    ],
    # The "your partner also married someone else" notice.
    "notice": [
        "the polycule sends its regards",
        "marriage is a many-to-many relationship",
        "your partner's calendar is getting crowded",
    ],
}


# ---------------------------------------------------------------------------
# Bot-directed quips: an action aimed at Matrimony itself
# ---------------------------------------------------------------------------

BOT: dict[str, list[str]] = {
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
    "block": [
        "the bot respects the boundary and the irony",
        "blocked: the bot will now pine quietly",
    ],
    "restrain": [
        "the bot is the paperwork",
        "restraining the court itself - bold strategy",
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


# ---------------------------------------------------------------------------
# Situational pools
# ---------------------------------------------------------------------------

# Replies for `!matr <something that isn't a real action>`.
UNKNOWN = [
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
RESTRAIN = [
    "the law is literally one message away",
    "personal space, now legally enforced",
    "the paperwork holds - this time",
    "restraining order: active and petty",
]

# When a jailed user tries to act on somebody on the outside.
JAIL = [
    "the walls have no DMs",
    "yard time doesn't include them",
    "the bars only bend for other inmates",
    "solitary means solitary",
    "you can look but you can't touch - literally",
]

# The release announcement when a sentence ends.
RELEASE = [
    "time served, tree trimmed",
    "the gates swing open; the love stays inside",
    "parole granted - family status: complicated no longer",
    "free to marry someone who isn't a co-defendant",
]

# Appended to jail-relationship dissolution notices.
DISSOLVE = [
    "it was never meant to last past lockup",
    "what happens in jail stays in jail",
    "the prison chapel issues no certificates",
    "conjugal visits end when the sentence does",
]

# Slightly unhinged wisdom: one random pick appended to the help embed.
HELP = [
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


# ---------------------------------------------------------------------------
# Command content (the payload is itself the quip)
# ---------------------------------------------------------------------------

PICKUP_LINES = (
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

DATE_IDEAS = (
    "to a candlelit debugging session, bugs provided free of charge",
    "stargazing at the voice channel member list",
    "to split one RAM upgrade, romantically",
    "on a couples' refactor: you hold the TODOs, they hold your heart",
    "to the edge of the render distance and back",
    "for a slow scroll through each other's pinned messages",
    "to dinner in the guild's AFK channel, it's quiet there",
)


def anniversary_note(seconds: float) -> str:
    """The duration-appropriate quip for `matr anniversary`."""
    if seconds < 300:
        return "The paperwork is still warm."
    if seconds < 86400:
        return "Still in the honeymoon phase."
    if seconds < 30 * 86400:
        return "Past the paper anniversary, into cardboard territory."
    if seconds < 365 * 86400:
        return "A love story for the ages, verified by SQLite."
    return "SQLite remembers. So should you."


# ---------------------------------------------------------------------------
# Rotation and formatting
# ---------------------------------------------------------------------------

# Bot-directed pools are namespaced under "bot:<action>"; everything else
# is keyed plainly ("marry", "jail", "unknown", ...).
_POOLS: dict[str, list[str]] = {
    **{f"bot:{kind}": lines for kind, lines in BOT.items()},
    **AMBIENT,
    "unknown": UNKNOWN,
    "restrain": RESTRAIN,
    "jail": JAIL,
    "release": RELEASE,
    "dissolve": DISSOLVE,
    "help": HELP,
}

_cycles: dict[str, itertools.cycle] = {}


def quip(kind: str, rng: random.Random | None = None) -> str:
    """A quip from ``kind``'s pool.

    With ``rng`` the pick is ``rng.choice`` (seedable, for the help embed);
    otherwise pools rotate deterministically so every line gets used.
    """
    pool = _POOLS[kind]
    if rng is not None:
        return rng.choice(pool)
    if kind not in _cycles:
        _cycles[kind] = itertools.cycle(pool)
    return next(_cycles[kind])


def subtext(text: str, kind: str) -> str:
    """``text`` with an ambient ``-# `` quip line for ``kind`` appended."""
    return f"{text}\n-# {quip(kind)}"
