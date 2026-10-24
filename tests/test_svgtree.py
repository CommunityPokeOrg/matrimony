"""Tests for the SVG family-tree renderer - Discord-free, like test_family."""

from xml.etree import ElementTree

import pytest

from matrimony.store import Store
from matrimony.svgtree import render_tree_svg, tree_members


@pytest.fixture()
def store() -> Store:
    s = Store(":memory:")
    yield s
    s.close()


def _name(uid: int) -> str:
    return f"U{uid}"


def build_tree(store: Store) -> None:
    """       1+2
               |
          3 ---+--- 4
               |
               5+6   (5 partners 6)
    """
    store.add_partners(1, 2)
    store.add_child(1, 3)
    store.add_child(1, 4)
    store.add_child(3, 5)
    store.add_partners(5, 6)


def text_nodes(svg: str) -> list[str]:
    root = ElementTree.fromstring(svg)
    return [
        (node.text or "")
        for node in root.iter("{http://www.w3.org/2000/svg}text")
    ]


def test_svg_is_wellformed(store: Store) -> None:
    build_tree(store)
    svg = render_tree_svg(store, 1, _name)
    root = ElementTree.fromstring(svg)
    assert root.tag == "{http://www.w3.org/2000/svg}svg"
    assert int(root.get("width", "0")) > 0
    assert int(root.get("height", "0")) > 0


def test_svg_contains_blood_relatives(store: Store) -> None:
    build_tree(store)
    svg = render_tree_svg(store, 1, _name)
    names = text_nodes(svg)
    for expected in ("U1", "U3", "U4", "U5"):
        assert expected in names
    # Partner of the root is not part of the blood tree...
    assert "U2" not in names
    # ...nor is the grandchild's partner.
    assert "U6" not in names


def test_svg_with_spouses(store: Store) -> None:
    build_tree(store)
    svg = render_tree_svg(store, 1, _name, include_spouses=True)
    names = text_nodes(svg)
    assert "U2" in names
    assert "U6" in names


def test_svg_ancestors(store: Store) -> None:
    build_tree(store)
    svg = render_tree_svg(store, 5, _name)
    names = text_nodes(svg)
    assert {"U3", "U1", "U5"} <= set(names)


def test_svg_empty_family(store: Store) -> None:
    svg = render_tree_svg(store, 42, _name)
    root = ElementTree.fromstring(svg)
    assert "U42" in text_nodes(svg)
    assert int(root.get("width", "0")) > 0


def test_svg_depth_limit(store: Store) -> None:
    # chain 1 -> 2 -> 3 -> 4 -> 5
    for i in range(1, 5):
        store.add_child(i, i + 1)
    names = text_nodes(render_tree_svg(store, 1, _name, max_depth=2))
    assert "U2" in names and "U3" in names
    assert "U4" not in names


def test_svg_cycle_safe(store: Store) -> None:
    store.add_child(1, 2)
    store.add_partners(1, 2)  # odd data, but rendering must not recurse forever
    names = text_nodes(render_tree_svg(store, 1, _name, include_spouses=True))
    assert "U1" in names


def test_svg_truncates_huge_trees(store: Store) -> None:
    for child in range(100, 160):
        store.add_child(1, child)
    svg = render_tree_svg(store, 1, _name, max_nodes=20)
    assert "truncated" in svg
    assert svg.count("<rect") <= 22  # background + at most max_nodes boxes


def test_svg_escapes_names(store: Store) -> None:
    store.add_child(1, 2)
    svg = render_tree_svg(
        store, 1, lambda uid: "<script>&" if uid == 2 else "root"
    )
    # Markup in a display name must not become markup in the document.
    assert "<script>" not in svg
    assert "&lt;script&gt;" in svg
    ElementTree.fromstring(svg)


def test_svg_shortens_long_names(store: Store) -> None:
    store.add_child(1, 2)
    svg = render_tree_svg(store, 1, lambda uid: "x" * 80)
    assert "x" * 80 not in svg
    assert "\u2026" in svg


def test_svg_no_external_references(store: Store) -> None:
    """The document has to stand alone to be safe to hand to Discord."""
    build_tree(store)
    svg = render_tree_svg(store, 1, _name, include_spouses=True)
    assert "http://" not in svg.replace(
        'xmlns="http://www.w3.org/2000/svg"', ""
    )
    assert "<script" not in svg
    assert "<image" not in svg


# A 1x1 PNG, enough to prove the embedding path works.
TINY_PNG = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8"
    "BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def test_svg_embeds_avatars(store: Store) -> None:
    build_tree(store)
    svg = render_tree_svg(
        store, 1, _name, include_spouses=True, avatar_of=lambda uid: TINY_PNG
    )
    # root, its partner, two children, a grandchild, that grandchild's partner
    assert svg.count("<image") == 6
    assert TINY_PNG in svg
    assert "clip-path" in svg
    ElementTree.fromstring(svg)


def test_svg_avatar_fallback_disc(store: Store) -> None:
    """No avatar means an initial disc, not a blank gap."""
    store.add_child(1, 2)
    svg = render_tree_svg(
        store, 1, lambda uid: "zoe" if uid == 2 else "adam", avatar_of=lambda uid: None
    )
    assert "<image" not in svg
    assert "<circle" in svg
    names = text_nodes(svg)
    assert "Z" in names  # initial of the avatar-less child
    assert "A" in names  # initial of the avatar-less root


def test_svg_rejects_remote_avatar_urls(store: Store) -> None:
    """A remote URL would make the file depend on someone else's server."""
    store.add_child(1, 2)
    svg = render_tree_svg(
        store,
        1,
        _name,
        avatar_of=lambda uid: "https://cdn.discordapp.com/avatars/1/x.png",
    )
    assert "<image" not in svg
    assert "cdn.discordapp.com" not in svg


def test_svg_ignores_blank_avatar(store: Store) -> None:
    store.add_child(1, 2)
    svg = render_tree_svg(store, 1, _name, avatar_of=lambda uid: "  ")
    assert "<image" not in svg


def test_tree_members_lists_everyone_drawn(store: Store) -> None:
    build_tree(store)
    members = set(tree_members(store, 1, include_spouses=True))
    assert {1, 2, 3, 4, 5, 6} <= members
    # Blood-only view leaves the grandchild's partner out.
    blood = set(tree_members(store, 1, include_spouses=False))
    assert 6 not in blood


def test_rendered_svg_rasterizes_to_png(store: Store) -> None:
    """The document the cog sends must actually convert - Discord will not
    inline an SVG attachment, so the upload is a PNG."""
    try:
        import cairosvg
    except Exception:  # missing package or native cairo
        pytest.skip("cairosvg/cairo unavailable")

    build_tree(store)
    png = cairosvg.svg2png(
        bytestring=render_tree_svg(store, 1, _name).encode("utf-8")
    )
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
