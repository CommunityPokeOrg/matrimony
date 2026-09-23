"""Tests for family-graph logic (ancestors, validation, relationship,
rendering) - all Discord-free."""

import pytest

from matrimony.family import FamilyView
from matrimony.store import Store


@pytest.fixture()
def store() -> Store:
    s = Store(":memory:")
    yield s
    s.close()


@pytest.fixture()
def fam(store: Store) -> FamilyView:
    return FamilyView(store)


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


def test_ancestors_and_descendants(store: Store, fam: FamilyView) -> None:
    build_tree(store)
    assert fam.ancestors(5) == {3: 1, 1: 2}
    assert fam.descendants(1) == {3: 1, 4: 1, 5: 2}
    assert fam.ancestors(1) == {}
    assert fam.descendants(4) == {}


def test_siblings(store: Store, fam: FamilyView) -> None:
    build_tree(store)
    assert sorted(fam.siblings(3)) == [4]
    assert fam.siblings(1) == []
    assert fam.siblings(5) == []


def test_blood_related(store: Store, fam: FamilyView) -> None:
    build_tree(store)
    assert fam.blood_related(1, 5)      # ancestor/descendant
    assert fam.blood_related(5, 1)
    assert fam.blood_related(3, 4)      # siblings (shared ancestor)
    assert fam.blood_related(4, 5)      # uncle/nephew-ish via 1
    assert not fam.blood_related(1, 2)  # partners aren't blood
    assert not fam.blood_related(1, 6)  # partner of grandchild
    assert not fam.blood_related(7, 8)  # strangers


def test_relationship(store: Store, fam: FamilyView) -> None:
    build_tree(store)
    assert fam.relationship(1, 2) == "partner"
    assert fam.relationship(3, 1) == "parent"
    assert fam.relationship(1, 3) == "child"
    assert fam.relationship(3, 4) == "sibling"
    assert fam.relationship(5, 1) == "grandparent"
    assert fam.relationship(1, 5) == "grandchild"
    assert fam.relationship(4, 5) == "niece/nephew"
    assert fam.relationship(5, 4) == "aunt/uncle"
    assert fam.relationship(1, 6) is None
    assert fam.relationship(7, 8) is None
    assert fam.relationship(3, 3) == "self"


def test_check_marry(store: Store, fam: FamilyView) -> None:
    build_tree(store)
    # self
    assert fam.check_marry(7, 7, allow_incest=False)
    # already partners
    assert fam.check_marry(1, 2, allow_incest=False)
    # blood relation blocked
    assert "family" in (fam.check_marry(3, 4, allow_incest=False) or "")
    # ... but allowed when incest is on
    assert fam.check_marry(3, 4, allow_incest=True) is None
    # strangers fine
    assert fam.check_marry(7, 8, allow_incest=False) is None
    # blocked user
    store.add_block(8, 7)
    assert fam.check_marry(7, 8, allow_incest=False)


def test_check_marry_partner_cap(store: Store, fam: FamilyView) -> None:
    store.add_partners(1, 2)
    store.add_partners(1, 3)
    assert "maximum" in (fam.check_marry(1, 4, allow_incest=False, max_partners=2) or "")
    assert fam.check_marry(1, 4, allow_incest=False, max_partners=0) is None


def test_check_adopt(store: Store, fam: FamilyView) -> None:
    build_tree(store)
    # self
    assert fam.check_adopt(7, 7, allow_incest=False)
    # already has a parent
    assert "already have a parent" in (fam.check_adopt(9, 3, allow_incest=False) or "")
    assert "already your child" in (fam.check_adopt(1, 3, allow_incest=False) or "")
    # can't adopt ancestor (cycle)
    assert fam.check_adopt(5, 1, allow_incest=True)
    # can't adopt descendant (already related)
    assert fam.check_adopt(1, 5, allow_incest=True)
    # can't adopt partner
    assert fam.check_adopt(1, 2, allow_incest=True)
    # unrelated adoption is fine
    assert fam.check_adopt(1, 7, allow_incest=False) is None
    # blocked
    store.add_block(8, 1)
    assert fam.check_adopt(1, 8, allow_incest=False)


def test_check_adopt_children_cap(store: Store, fam: FamilyView) -> None:
    store.add_child(1, 10)
    store.add_child(1, 11)
    assert "maximum" in (fam.check_adopt(1, 20, allow_incest=False, max_children=2) or "")
    assert fam.check_adopt(1, 20, allow_incest=False, max_children=0) is None


def test_render_tree_blood(store: Store, fam: FamilyView) -> None:
    build_tree(store)
    text = fam.render_tree(1, _name)
    assert "U1" in text
    assert "U3" in text and "U4" in text and "U5" in text
    # blood tree shows partners of root in Partners line, not recursively
    assert "Partners: U2" in text
    assert "U6" not in text  # grandchild's partner not shown in blood tree


def test_render_tree_full(store: Store, fam: FamilyView) -> None:
    build_tree(store)
    text = fam.render_tree(1, _name, include_spouses=True)
    assert "U6" in text  # partner of child U5 shown inline


def test_render_tree_ancestors(store: Store, fam: FamilyView) -> None:
    build_tree(store)
    text = fam.render_tree(5, _name)
    assert "Ancestors" in text
    assert "U3" in text and "U1" in text


def test_render_tree_empty(store: Store, fam: FamilyView) -> None:
    text = fam.render_tree(42, _name)
    assert "no family" in text


def test_render_tree_depth_limit(store: Store, fam: FamilyView) -> None:
    # chain 1 -> 2 -> 3 -> 4 -> 5
    for i in range(1, 5):
        store.add_child(i, i + 1)
    text = fam.render_tree(1, _name, max_depth=2)
    assert "U2" in text and "U3" in text
    assert "U4" not in text


def test_render_tree_cyclesafe(store: Store, fam: FamilyView) -> None:
    store.add_child(1, 2)
    store.add_partners(1, 2)  # odd data, but rendering must not loop
    text = fam.render_tree(1, _name, include_spouses=True)
    assert "U1" in text
