"""Pure family-graph logic for Matrimony.

Everything in this module is independent of discord.py: a ``FamilyView``
wraps a ``Store`` and exposes ancestors/descendants, validation rules for
proposals, relationship naming, and ASCII tree rendering. Keeping this free
of Discord types makes it fully unit-testable.
"""

from __future__ import annotations

from collections.abc import Callable

from .store import Store

NameFn = Callable[[int], str]

# ---------------------------------------------------------------------------
# Relationship labels
# ---------------------------------------------------------------------------

GRANDPARENT_PREFIX = {2: "grand", 3: "great-grand"}


def _ancestor_label(depth: int) -> str:
    if depth == 1:
        return "parent"
    if depth == 2:
        return "grandparent"
    if depth == 3:
        return "great-grandparent"
    return f"great-x{depth - 2} grandparent"


def _descendant_label(depth: int) -> str:
    if depth == 1:
        return "child"
    if depth == 2:
        return "grandchild"
    if depth == 3:
        return "great-grandchild"
    return f"great-x{depth - 2} grandchild"


class FamilyView:
    def __init__(self, store: Store) -> None:
        self.store = store

    # ------------------------------------------------------------ traversal

    def ancestors(self, user_id: int, max_depth: int = 100) -> dict[int, int]:
        """All ancestors of ``user_id`` as ``{ancestor_id: depth}``.

        Depth 1 = parent, 2 = grandparent, etc. Cycle-safe."""
        found: dict[int, int] = {}
        frontier = [user_id]
        depth = 0
        while frontier and depth < max_depth:
            depth += 1
            next_frontier: list[int] = []
            for node in frontier:
                parent = self.store.parent_of(node)
                if parent is not None and parent not in found and parent != user_id:
                    found[parent] = depth
                    next_frontier.append(parent)
            frontier = next_frontier
        return found

    def descendants(self, user_id: int, max_depth: int = 100) -> dict[int, int]:
        """All descendants of ``user_id`` as ``{descendant_id: depth}``."""
        found: dict[int, int] = {}
        frontier = [user_id]
        depth = 0
        while frontier and depth < max_depth:
            depth += 1
            next_frontier = []
            for node in frontier:
                for child in self.store.children_of(node):
                    if child not in found and child != user_id:
                        found[child] = depth
                        next_frontier.append(child)
            frontier = next_frontier
        return found

    def siblings(self, user_id: int) -> list[int]:
        parent = self.store.parent_of(user_id)
        if parent is None:
            return []
        return [c for c in self.store.children_of(parent) if c != user_id]

    def blood_related(self, a: int, b: int) -> bool:
        """True if ``a`` and ``b`` share any blood relation: one is an
        ancestor/descendant of the other, or they share a common ancestor
        (siblings, cousins, ...)."""
        if a == b:
            return True
        if b in self.ancestors(a) or a in self.ancestors(b):
            return True
        return bool(set(self.ancestors(a)) & set(self.ancestors(b)))

    def relationship(self, a: int, b: int) -> str | None:
        """Human-readable label of how ``b`` relates to ``a``, or None."""
        if a == b:
            return "self"
        if b in self.store.partners_of(a):
            return "partner"
        if self.store.parent_of(a) == b:
            return "parent"
        if self.store.parent_of(b) == a:
            return "child"
        if b in self.siblings(a):
            return "sibling"
        anc = self.ancestors(a)
        if b in anc:
            return _ancestor_label(anc[b])
        desc = self.descendants(a)
        if b in desc:
            return _descendant_label(desc[b])
        parent = self.store.parent_of(a)
        if parent is not None and b in self.siblings(parent):
            return "aunt/uncle"
        their_parent = self.store.parent_of(b)
        if their_parent is not None and a in self.siblings(their_parent):
            return "niece/nephew"
        if set(anc) & set(self.ancestors(b)):
            return "cousin"
        return None

    # ----------------------------------------------------------- validation

    def check_marry(
        self, proposer: int, target: int, *, allow_incest: bool,
        max_partners: int = 0,
    ) -> str | None:
        """Returns an error string if ``proposer`` may not marry ``target``,
        else None. Mirrors MarriageBot's proposal checks."""
        if proposer == target:
            return "You can't marry yourself, as much as you may want to."
        if target in self.store.partners_of(proposer):
            return "You're already married to them!"
        if self.store.is_blocked(target, proposer):
            return "They've blocked you from sending them proposals."
        if not allow_incest and self.blood_related(proposer, target):
            return (
                "You can't marry a family member. A server admin can allow "
                "incest proposals with the `incest` command."
            )
        if max_partners and len(self.store.partners_of(proposer)) >= max_partners:
            return f"You already have the maximum of {max_partners} partners."
        if max_partners and len(self.store.partners_of(target)) >= max_partners:
            return f"They already have the maximum of {max_partners} partners."
        return None

    def check_adopt(
        self, parent: int, child: int, *, allow_incest: bool,
        max_children: int = 0,
    ) -> str | None:
        """Returns an error string if ``parent`` may not adopt ``child``."""
        if parent == child:
            return "You can't adopt yourself."
        if self.store.parent_of(child) is not None:
            if self.store.parent_of(child) == parent:
                return "They're already your child."
            return "They already have a parent. They'd need to emancipate first."
        if self.store.is_blocked(child, parent):
            return "They've blocked you from sending them proposals."
        if child in self.store.partners_of(parent):
            return "You can't adopt your own partner - divorce them first."
        # Structural checks that apply even when incest is allowed: adopting an
        # ancestor would create a cycle, and a descendant is already family.
        anc = self.ancestors(parent)
        if child in anc:
            return "You can't adopt your own ancestor - that would loop the tree."
        if parent in self.ancestors(child) or child in self.descendants(parent):
            return "They're already related to you."
        if not allow_incest and self.blood_related(parent, child):
            return (
                "You can't adopt a family member. A server admin can allow "
                "incest proposals with the `incest` command."
            )
        if max_children and len(self.store.children_of(parent)) >= max_children:
            return f"You already have the maximum of {max_children} children."
        return None

    # ------------------------------------------------------------ rendering

    def render_tree(
        self,
        root: int,
        name_of: NameFn,
        *,
        include_spouses: bool = False,
        max_depth: int = 10,
        max_nodes: int = 500,
    ) -> str:
        """Render ``root``'s family as an indented text tree.

        ``include_spouses=False`` renders blood relatives only (like
        MarriageBot's ``tree``); ``True`` also shows each node's partners
        inline (like ``fulltree``).
        """
        budget = [max_nodes]
        lines: list[str] = [f"**{name_of(root)}**'s family tree", ""]

        # Ancestor chain (single-parent model -> linear chain).
        chain: list[int] = []
        node = root
        seen = {root}
        while len(chain) < max_depth:
            parent = self.store.parent_of(node)
            if parent is None or parent in seen:
                break
            chain.append(parent)
            seen.add(parent)
            node = parent
        if chain:
            lines.append("Ancestors:")
            for depth, anc in enumerate(reversed(chain), start=1):
                label = _ancestor_label(len(chain) - depth + 1)
                lines.append(f"  {'  ' * (depth - 1)}- {name_of(anc)} ({label})")
            lines.append("")

        sibs = self.siblings(root)
        if sibs:
            lines.append("Siblings: " + ", ".join(name_of(s) for s in sibs))

        partners = self.store.partners_of(root)
        if partners:
            lines.append("Partners: " + ", ".join(name_of(p) for p in partners))

        children = self.store.children_of(root)
        if children:
            lines.append("Children:")
            for i, child in enumerate(children):
                last = i == len(children) - 1
                self._render_node(
                    child, name_of, include_spouses, max_depth, 1,
                    "" if last else "|", last, lines, budget, {root},
                )
        if not partners and not children and not chain and not sibs:
            lines.append("_This user has no family yet._")
        if budget[0] <= 0:
            lines.append("_...tree truncated (too many members)_")
        return "\n".join(lines)

    def _render_node(
        self, uid: int, name_of: NameFn, include_spouses: bool,
        depth_left: int, indent: int, prefix: str, last: bool,
        lines: list[str], budget: list[int], seen: set[int],
    ) -> None:
        if budget[0] <= 0 or uid in seen or depth_left <= 0:
            return
        budget[0] -= 1
        seen.add(uid)
        branch = "`-- " if last else "|-- "
        pad = "    " if last else "|   "
        partner_txt = ""
        if include_spouses:
            partners = [p for p in self.store.partners_of(uid) if p not in seen]
            if partners:
                partner_txt = " (+ " + ", ".join(name_of(p) for p in partners) + ")"
        lines.append(f"{prefix}{branch}{name_of(uid)}{partner_txt}")
        children = [c for c in self.store.children_of(uid) if c not in seen]
        for i, child in enumerate(children):
            self._render_node(
                child, name_of, include_spouses, depth_left - 1,
                indent + 1, prefix + pad, i == len(children) - 1,
                lines, budget, seen,
            )
