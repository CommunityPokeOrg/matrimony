"""SVG rendering of family trees.

Pure module: a ``Store`` plus a name resolver in, an SVG document out. The
graph it walks mirrors :meth:`matrimony.family.FamilyView.render_tree` -
the ancestor chain above the root, blood descendants below, partners beside
their spouse when asked - so ``!matr tree`` and the text renderer describe
the same family.

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
    max_depth: int,
    max_nodes: int,
) -> tuple[dict[int, Node], dict[int, list[int]], list[int], bool]:
    """Walk the graph around ``root``.

    Returns ``(nodes, partners, ancestors, truncated)`` where ``nodes`` maps
    a user id to ``{"gen", "children"}``, ``partners`` maps a user id to the
    partner ids drawn beside it, and ``ancestors`` is the parent chain ordered
    nearest first. Cycle-safe and bounded by ``max_nodes``.
    """
    nodes: dict[int, Node] = {}
    ancestors: list[int] = []
    truncated = False

    def add(uid: int, gen: int) -> bool:
        if uid in nodes or len(nodes) >= max_nodes:
            return False
        nodes[uid] = {"gen": gen, "children": []}
        return True

    add(root, 0)

    # Ancestor chain: gen -1 is the parent, -2 the grandparent, and so on.
    seen = {root}
    node = root
    while len(ancestors) < max_depth:
        parent = store.parent_of(node)
        if parent is None or parent in seen or len(nodes) >= max_nodes:
            break
        if not add(parent, -(len(ancestors) + 1)):
            break
        ancestors.append(parent)
        seen.add(parent)
        node = parent

    # Blood descendants, breadth first so generation numbers stay honest.
    frontier: list[tuple[int, int]] = [(root, 0)]
    while frontier:
        uid, gen = frontier.pop(0)
        if gen >= max_depth:
            continue
        for child in store.children_of(uid):
            if child in nodes or child == root:
                continue
            if len(nodes) >= max_nodes:
                truncated = True
                break
            add(child, gen + 1)
            nodes[uid]["children"].append(child)  # type: ignore[union-attr]
            frontier.append((child, gen + 1))

    partners: dict[int, list[int]] = {}
    if include_spouses:
        # A spouse already drawn as a blood relative keeps that position;
        # this only adds people who would otherwise be missing.
        claimed: set[int] = set()
        for uid in nodes:
            spouses = [
                p
                for p in store.partners_of(uid)
                if p != uid and p not in nodes and p not in claimed
            ]
            if spouses:
                partners[uid] = spouses
                claimed.update(spouses)

    return nodes, partners, ancestors, truncated


def tree_members(
    store: Store,
    root: int,
    *,
    include_spouses: bool = False,
    max_depth: int = 10,
    max_nodes: int = 200,
) -> list[int]:
    """Ids that :func:`render_tree_svg` would draw, in no particular order.

    Callers use this to decide whose avatars are worth fetching before the
    synchronous render runs.
    """
    nodes, partners, ancestors, _truncated = _collect(
        store,
        root,
        include_spouses=include_spouses,
        max_depth=max_depth,
        max_nodes=max_nodes,
    )
    ids = list(nodes) + ancestors
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
    max_depth: int = 10,
    max_nodes: int = 200,
    avatar_of: AvatarFn | None = None,
) -> str:
    """Render ``root``'s family as a standalone SVG document.

    ``avatar_of`` may return a ``data:image/...`` URI per user id; anything
    else is ignored and the node falls back to an initial disc.
    """
    nodes, partners, ancestors, truncated = _collect(
        store,
        root,
        include_spouses=include_spouses,
        max_depth=max_depth,
        max_nodes=max_nodes,
    )
    width = _widths(root, nodes, partners)

    unit = NODE_W + GAP_X
    gen_offset = len(ancestors)
    boxes: dict[int, tuple[float, float]] = {}
    spouses: list[tuple[int, float, float]] = []

    def row_y(gen: int) -> float:
        return PAD + (gen + gen_offset) * (NODE_H + GAP_Y)

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

    place(root, 0.0)

    # Ancestors share the root's centre line, one row per generation.
    center_x = boxes[root][0] + NODE_W / 2
    ancestor_boxes = [
        (uid, center_x - NODE_W / 2, row_y(int(nodes[uid]["gen"])))
        for uid in ancestors
    ]

    # Ancestors' partners need boxes too, not just connector lines - a
    # spouse sitting beside someone in the ancestor chain is drawn exactly
    # like one beside a descendant.
    for uid, x, y in ancestor_boxes:
        for index, spouse in enumerate(partners.get(uid, ())):
            spouses.append(
                (spouse, x + NODE_W + GAP_X + index * (NODE_W + GAP_X), y)
            )

    # Every placed node, for edge drawing. Ancestors and spouses are placed
    # outside the root's descent, so ``boxes`` alone is not enough.
    pos: dict[int, tuple[float, float]] = dict(boxes)
    for uid, x, y in ancestor_boxes:
        pos[uid] = (x, y)
    for uid, x, y in spouses:
        pos[uid] = (x, y)

    # Normalise so nothing lands at a negative coordinate.
    xs = [x for x, _ in boxes.values()] + [x for _, x, _ in ancestor_boxes]
    xs += [x for _, x, _ in spouses]
    min_x = min(xs)
    ys = [y for _, y in boxes.values()] + [y for _, _, y in ancestor_boxes]
    ys += [y for _, _, y in spouses]
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

    previous = root
    for uid, x, y in ancestor_boxes:
        px, py = pos[previous]
        edge(px + NODE_W / 2, py, x + NODE_W / 2, y + NODE_H)
        previous = uid

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
    for uid, x, y in ancestor_boxes:
        box(uid, x, y, root_node=False, partner=False)
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
