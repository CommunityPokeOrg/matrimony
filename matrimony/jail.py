"""Restraining-order and jail mechanics for Matrimony.

Like ``family.py``, everything here is independent of discord.py: the
sentence-length table, the jail-relationship validation rules, and
``sweep_expiry`` - the periodic expiry pass - are all pure functions of
the store and an injected clock, so the whole module is unit-testable.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .store import ReleaseResult, RestrainingOrder, Store

# ---------------------------------------------------------------------------
# Sentencing
# ---------------------------------------------------------------------------

# Actions covered by restraining-order enforcement: everything a
# restrained user could aim at the protected user. (Read-only actions
# like `ship`, `tree` or `relationship` are not "targeted at" anyone and
# stay free.)
RESTRAINED_ACTIONS = frozenset({
    "marry", "adopt", "makeparent",
    "hug", "cuddle", "kiss", "pat", "poke", "wave", "lick", "nom",
    "tickle", "highfive", "handhold", "slap", "punch", "bite", "stab",
    "flirt", "date",
})

# Jailed users are blocked from the restrained set plus the remaining
# family-mutating actions that target a (necessarily free) user on the
# outside: divorce, disown and (family) block.
JAILED_ACTIONS = RESTRAINED_ACTIONS | {"divorce", "disown", "block"}

# Sentence lengths for violating a restraining order.
#
# Minor infractions - light social actions - draw a RANDOM sentence
# between 1 and 5 minutes. Major infractions draw a fixed sentence that
# scales with severity, up to the 30-minute cap for attempted forced
# marriage:
#
#     slap            10 min
#     adopt           15 min
#     makeparent      15 min
#     bite            20 min
#     punch           20 min
#     stab            25 min
#     marry           30 min
#     (unlisted)      15 min  - safety default for future major actions
MINOR_SENTENCE_RANGE = (60, 300)  # seconds: a random 1-5 minute stint
MAJOR_SENTENCE_MINUTES = {
    "slap": 10,
    "adopt": 15,
    "makeparent": 15,
    "bite": 20,
    "punch": 20,
    "stab": 25,
    "marry": 30,
}
DEFAULT_MAJOR_MINUTES = 15


def is_minor_action(action: str) -> bool:
    """Whether ``action`` draws the random 1-5 minute minor sentence."""
    return action in RESTRAINED_ACTIONS and action not in MAJOR_SENTENCE_MINUTES


def sentence_seconds(action: str, rng: random.Random = random) -> int:
    """How long ``action`` lands the offender in jail, in seconds.

    Minor actions roll a random sentence inside ``MINOR_SENTENCE_RANGE``;
    major ones read ``MAJOR_SENTENCE_MINUTES`` (with a 15-minute default
    for any targeted action not explicitly listed)."""
    if is_minor_action(action):
        return rng.randint(*MINOR_SENTENCE_RANGE)
    return MAJOR_SENTENCE_MINUTES.get(action, DEFAULT_MAJOR_MINUTES) * 60


# ---------------------------------------------------------------------------
# Jail relationships
# ---------------------------------------------------------------------------


def check_jail_marry(store: Store, proposer: int, target: int) -> str | None:
    """Jail equivalent of ``FamilyView.check_marry`` - deliberately much
    laxer (no blood/incest rules, no partner cap), since jail marriages
    are ephemeral anyway."""
    if proposer == target:
        return "You can't marry yourself, even in jail."
    if target in store.jail_partners_of(proposer):
        return "You're already jail-married to them!"
    if store.is_blocked(target, proposer):
        return "They've blocked you from sending them proposals."
    return None


def check_jail_adopt(store: Store, parent: int, child: int) -> str | None:
    """Jail equivalent of ``check_adopt``: one jail parent per child and
    no direct two-cycle, but otherwise open."""
    if parent == child:
        return "You can't adopt yourself, even in jail."
    existing = store.jail_parent_of(child)
    if existing is not None:
        if existing == parent:
            return "They're already your jail child."
        return "They already have a jail parent."
    if store.jail_parent_of(parent) == child:
        return "They're already your jail parent."
    if store.is_blocked(child, parent):
        return "They've blocked you from sending them proposals."
    return None


# ---------------------------------------------------------------------------
# Expiry sweep
# ---------------------------------------------------------------------------


@dataclass
class ExpiryReport:
    """Everything a sweep changed, for the cog to announce.

    ``expired_orders`` are the restraining orders that lapsed;
    ``released`` holds one ReleaseResult per freed inmate (including the
    jail relationships dissolved by their release)."""

    expired_orders: list[RestrainingOrder] = field(default_factory=list)
    released: list[ReleaseResult] = field(default_factory=list)


def sweep_expiry(store: Store, now: int) -> ExpiryReport:
    """Apply expiry for ``now``: lapse restraining orders past their
    expiry and release inmates whose sentence is up (dissolving their
    jail relationships).

    Pure in its inputs - same store state + same ``now`` = same result -
    so tests drive it with an injected clock."""
    expired = store.expire_restraining_orders(now)
    released = []
    for sentence in store.sentences_due(now):
        result = store.release_inmate(sentence.inmate)
        if result is not None:
            released.append(result)
    return ExpiryReport(expired_orders=expired, released=released)
