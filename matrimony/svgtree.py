"""SVG rendering of family trees.

Pure module: a ``Store`` plus a name resolver in, an SVG document out. The
graph it walks is one downward tree from the highest known ancestor: the
pedigree climbs up to ``ancestor_gens`` generations (parents, grandparents,
great-grandparents), then the whole family is laid out below it -
descendants without a depth limit, each ancestor's side branches (their
other children and their descendants), their partners beside them, and
those partners' own children hanging under the couple. Partners of
non-ancestors join only when ``include_spouses`` is set.

The output is a standalone document: no external references, no fonts to
fetch, no scripts. Avatars, when supplied, must already be ``data:`` URIs -
a remote URL would make the file depend on someone else's server, so it is
dropped rather than embedded. Nodes without an avatar fall back to a
coloured disc holding the first letter of the display name.
"""

from __future__ import annotations

from collections.abc import Callable
from xml.sax.saxutils import escape, quoteattr

from .store import Store

NameFn = Callable[[int], str]
AvatarFn = Callable[[int], str | None]

# Geometry, in pixels.
NODE_W = 196
NODE_H = 44
GAP_X = 22
GAP_Y = 58
PAD = 32
AVATAR_R = 14
AVATAR_INSET = 14

# Palette: Discord's dark surface, with the embed green for the root.
BG = "#1e1f22"
BOX = "#2b2d31"
BOX_ROOT = "#20342a"
STROKE = "#4b4d53"
TEXT = "#f2f3f5"
MUTED = "#b5bac1"
ACCENT = "#2ecc71"
PARTNER = "#f1c40f"
FALLBACK_FILL = "#3a3d44"

MAX_LABEL = 20
# Pedigree depth: parents, grandparents, great-grandparents.
ANCESTOR_GENS = 3
FONT = "ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif"

Node = dict[str, object]


def _label(name: str) -> str:
    """Escape and shorten a display name for use inside a ``<text>`` node."""
    text = (name or "").strip() or "unknown"
    if len(text) > MAX_LABEL:
        text = text[: MAX_LABEL - 1] + "\u2026"
    return escape(text)


def _initial(name: str) -> str:
    """First character of a display name, for the avatar-less fallback."""
    text = (name or "").strip()
    return escape(text[:1].upper()) if text else "?"


def _avatar_href(value: str | None) -> str | None:
    """Accept an embedded image payload; reject anything fetched remotely."""
    if not value:
        return None
    href = value.strip()
    return href if href.startswith("data:image/") else None


def _collect(
    store: Store,
    root: int,
    *,
    include_spouses: bool,
    ancestor_gens: int,
    max_nodes: int,
) -> tuple[dict[int, Node], dict[int, list[int]], int, list[int], bool]:
    """Walk the graph around ``root``.

    Climbs the parent chain at most ``ancestor_gens`` steps to the topmost
    ancestor, then descends without a depth limit through the whole family
    below it. Every chain ancestor additionally contributes their partners'
    children to the drawn offspring, so aunts, uncles, cousins and
    step-siblings appear alongside the direct line.

    Returns ``(nodes, partners, top, chain, truncated)`` where ``nodes``
    maps a user id to ``{"gen", "children"}`` (``gen`` counts down from the
    topmost ancestor), ``partners`` maps a user id to the partner ids drawn
    beside it, ``top`` is the tree's root id, and ``chain`` is the ancestor
    chain nearest first. Cycle-safe and bounded by ``max_nodes``.
    """
    nodes: dict[int, Node] = {}
    truncated = False

    # Pedigree: parent, grandparent, great-grandparent (nearest first).
    chain: list[int] = []
    seen_chain = {root}
    node = root
    while len(chain) < ancestor_gens:
        parent = store.parent_of(node)
        if parent is None or parent in seen_chain:
            break
        chain.append(parent)
        seen_chain.add(parent)
        node = parent
    chain_set = set(chain)
    top = chain[-1] if chain else root

    def drawn_children(uid: int) -> list[int]:
        kids = list(store.children_of(uid))
        if uid in chain_set:
            # An ancestor's partners raise children in the same household:
            # draw the partners' own offspring under the couple too.
            for partner in store.partners_of(uid):
                kids.extend(store.children_of(partner))
        seen: set[int] = set()
        out: list[int] = []
        for kid in kids:
            if kid not in seen:
                seen.add(kid)
                out.append(kid)
        return out

    nodes[top] = {"gen": 0, "children": []}
    frontier = [top]
    while frontier:
        uid = frontier.pop(0)
        gen = int(nodes[uid]["gen"])
        for child in drawn_children(uid):
            if child in nodes:
                continue
            if len(nodes) >= max_nodes:
                truncated = True
                continue
            nodes[child] = {"gen": gen + 1, "children": []}
            nodes[uid]["children"].append(child)  # type: ignore[union-attr]
            frontier.append(child)

    # Ancestors always sit beside their partners - a pedigree missing a
    # spouse reads as broken. Other members' partners only join when the
    # caller asked for the full tree. A spouse already drawn as a blood
    # relative keeps that position.
    partners: dict[int, list[int]] = {}
    claimed: set[int] = set()
    for uid in nodes:
        if uid not in chain_set and not include_spouses:
            continue
        spouses = [
            p
            for p in store.partners_of(uid)
            if p != uid and p not in nodes and p not in claimed
        ]
        if spouses:
            partners[uid] = spouses
            claimed.update(spouses)

    return nodes, partners, top, chain, truncated


def tree_members(
    store: Store,
    root: int,
    *,
    include_spouses: bool = False,
    ancestor_gens: int = ANCESTOR_GENS,
    max_nodes: int = 200,
) -> list[int]:
    """Ids that :func:`render_tree_svg` would draw, in no particular order.

    Callers use this to decide whose avatars are worth fetching before the
    synchronous render runs.
    """
    nodes, partners, _top, _chain, _truncated = _collect(
        store,
        root,
        include_spouses=include_spouses,
        ancestor_gens=ancestor_gens,
        max_nodes=max_nodes,
    )
    ids = list(nodes)
    for spouses in partners.values():
        ids.extend(spouses)
    seen: set[int] = set()
    ordered: list[int] = []
    for uid in ids:
        if uid not in seen:
            seen.add(uid)
            ordered.append(uid)
    return ordered


def _widths(
    uid: int, nodes: dict[int, Node], partners: dict[int, list[int]]
) -> dict[int, int]:
    """Subtree width of every node, in column slots."""
    width: dict[int, int] = {}

    def slots(node: int) -> int:
        return 1 + len(partners.get(node, ()))

    def walk(node: int) -> int:
        children = list(nodes[node]["children"])  # type: ignore[arg-type]
        if not children:
            width[node] = slots(node)
            return width[node]
        total = sum(walk(child) for child in children)
        width[node] = max(slots(node), total)
        return width[node]

    walk(uid)
    return width


def render_tree_svg(
    store: Store,
    root: int,
    name_of: NameFn,
    *,
    include_spouses: bool = False,
    ancestor_gens: int = ANCESTOR_GENS,
    max_nodes: int = 200,
    avatar_of: AvatarFn | None = None,
) -> str:
    """Render ``root``'s family as a standalone SVG document.

    ``avatar_of`` may return a ``data:image/...`` URI per user id; anything
    else is ignored and the node falls back to an initial disc.
    """
    nodes, partners, top, _chain, truncated = _collect(
        store,
        root,
        include_spouses=include_spouses,
        ancestor_gens=ancestor_gens,
        max_nodes=max_nodes,
    )
    width = _widths(top, nodes, partners)

    unit = NODE_W + GAP_X
    boxes: dict[int, tuple[float, float]] = {}
    spouses: list[tuple[int, float, float]] = []

    def row_y(gen: int) -> float:
        return PAD + gen * (NODE_H + GAP_Y)

    def place(uid: int, left: float) -> None:
        kids = list(nodes[uid]["children"])  # type: ignore[arg-type]
        own_px = (1 + len(partners.get(uid, ()))) * unit - GAP_X
        sub_px = width[uid] * unit - GAP_X
        center = left + (sub_px / 2 if kids else own_px / 2)
        x = center - NODE_W / 2
        y = row_y(int(nodes[uid]["gen"]))  # type: ignore[arg-type]
        boxes[uid] = (x, y)
        for index, spouse in enumerate(partners.get(uid, ())):
            spouses.append(
                (spouse, x + NODE_W + GAP_X + index * (NODE_W + GAP_X), y)
            )
        if kids:
            kids_total = sum(width[c] * unit - GAP_X for c in kids)
            cursor = left + (sub_px - kids_total) / 2
            for child in kids:
                place(child, cursor)
                cursor += width[child] * unit

    place(top, 0.0)

    # Every placed node, for edge drawing. Spouses are placed outside the
    # main descent, so ``boxes`` alone is not enough.
    pos: dict[int, tuple[float, float]] = dict(boxes)
    for uid, x, y in spouses:
        pos[uid] = (x, y)

    # Normalise so nothing lands at a negative coordinate.
    xs = [x for x, _ in boxes.values()] + [x for _, x, _ in spouses]
    min_x = min(xs)
    ys = [y for _, y in boxes.values()] + [y for _, _, y in spouses]
    max_y = max(ys)

    canvas_w = int(round(max(xs) - min_x + NODE_W + PAD * 2))
    canvas_h = int(round(max_y + NODE_H + PAD + (24 if truncated else 0)))

    def shift(px: float) -> float:
        return px - min_x + PAD

    avatars: dict[int, str] = {}
    if avatar_of is not None:
        for uid in pos:
            href = _avatar_href(avatar_of(uid))
            if href:
                avatars[uid] = href

    out: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{canvas_w}" '
        f'height="{canvas_h}" viewBox="0 0 {canvas_w} {canvas_h}" '
        f"font-family={quoteattr(FONT)}>",
        f'<rect width="{canvas_w}" height="{canvas_h}" fill="{BG}"/>',
    ]

    def edge(x1: float, y1: float, x2: float, y2: float) -> None:
        x1, x2 = shift(x1), shift(x2)
        if abs(x1 - x2) < 1:
            path = f"M {x1:.1f} {y1:.1f} L {x2:.1f} {y2:.1f}"
        else:
            mid = y1 + (y2 - y1) / 2
            path = (
                f"M {x1:.1f} {y1:.1f} L {x1:.1f} {mid:.1f} "
                f"L {x2:.1f} {mid:.1f} L {x2:.1f} {y2:.1f}"
            )
        out.append(
            f'<path d="{path}" fill="none" stroke="{STROKE}" stroke-width="2"/>'
        )

    # Blood edges first, so the boxes paint over the joins.
    for uid, (x, y) in boxes.items():
        for child in nodes[uid]["children"]:  # type: ignore[union-attr]
            if child not in pos:
                continue
            cx, cy = pos[child]
            edge(x + NODE_W / 2, y + NODE_H, cx + NODE_W / 2, cy)

    # Partner connectors: dashed, in the marriage gold.
    for uid, spouse_list in partners.items():
        x, y = pos[uid]
        for index, _spouse in enumerate(spouse_list):
            sx = x + NODE_W + GAP_X + index * (NODE_W + GAP_X)
            out.append(
                f'<line x1="{shift(x + NODE_W):.1f}" y1="{y + NODE_H / 2:.1f}" '
                f'x2="{shift(sx):.1f}" y2="{y + NODE_H / 2:.1f}" '
                f'stroke="{PARTNER}" stroke-width="2" stroke-dasharray="4 4"/>'
            )

    def box(uid: int, x: float, y: float, *, root_node: bool, partner: bool) -> None:
        fill = BOX_ROOT if root_node else BOX
        stroke = ACCENT if root_node else STROKE
        bx = shift(x)
        out.append(
            f'<rect x="{bx:.1f}" y="{y:.1f}" width="{NODE_W}" '
            f'height="{NODE_H}" rx="10" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="{2 if root_node else 1}"/>'
        )

        # Avatar disc, then the name to its right.
        cx = bx + AVATAR_INSET + AVATAR_R
        cy = y + NODE_H / 2
        href = avatars.get(uid)
        if href is not None:
            out.append(
                f'<clipPath id="av{uid}"><circle cx="{cx:.1f}" cy="{cy:.1f}" '
                f'r="{AVATAR_R}"/></clipPath>'
            )
            out.append(
                f'<image x="{cx - AVATAR_R:.1f}" y="{cy - AVATAR_R:.1f}" '
                f'width="{AVATAR_R * 2}" height="{AVATAR_R * 2}" '
                f'preserveAspectRatio="xMidYMid slice" '
                f'clip-path="url(#av{uid})" href={quoteattr(href)}/>'
            )
        else:
            out.append(
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{AVATAR_R}" '
                f'fill="{FALLBACK_FILL}" stroke="{STROKE}" stroke-width="1"/>'
            )
            out.append(
                f'<text x="{cx:.1f}" y="{cy:.1f}" fill="{MUTED}" '
                f'font-size="12" text-anchor="middle" '
                f'dominant-baseline="central">{_initial(name_of(uid))}</text>'
            )

        text_x = cx + AVATAR_R + 10
        out.append(
            f'<text x="{text_x:.1f}" y="{cy:.1f}" '
            f'fill="{PARTNER if partner else TEXT}" font-size="14" '
            f'text-anchor="start" dominant-baseline="middle">'
            f"{_label(name_of(uid))}</text>"
        )

    for uid, (x, y) in boxes.items():
        box(uid, x, y, root_node=uid == root, partner=False)
    for uid, x, y in spouses:
        box(uid, x, y, root_node=False, partner=True)

    if truncated:
        out.append(
            f'<text x="{canvas_w / 2:.1f}" y="{canvas_h - 12:.1f}" '
            f'fill="{MUTED}" font-size="12" text-anchor="middle">'
            f"tree truncated - too many members</text>"
        )

    out.append("</svg>")
    return "\n".join(out)
