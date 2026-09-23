"""Tests for the SQLite store layer."""


import pytest

from matrimony.store import Store


@pytest.fixture()
def store() -> Store:
    s = Store(":memory:")
    yield s
    s.close()


def test_partners_roundtrip(store: Store) -> None:
    store.add_partners(10, 20)
    store.add_partners(30, 10)
    assert sorted(store.partners_of(10)) == [20, 30]
    assert store.partners_of(20) == [10]
    assert store.partners_of(99) == []

    assert store.remove_partners(10, 20) is True
    assert store.remove_partners(10, 20) is False
    assert store.partners_of(10) == [30]


def test_partners_idempotent(store: Store) -> None:
    store.add_partners(1, 2)
    store.add_partners(1, 2)  # duplicate insert is a no-op
    assert store.partners_of(1) == [2]


def test_one_parent_per_child(store: Store) -> None:
    assert store.add_child(100, 200) is True
    assert store.parent_of(200) == 100
    # Second parent rejected
    assert store.add_child(300, 200) is False
    assert store.parent_of(200) == 100
    assert store.children_of(100) == [200]
    assert store.children_of(300) == []

    assert store.remove_child(200) is True
    assert store.remove_child(200) is False


def test_proposal_lifecycle(store: Store) -> None:
    p = store.create_proposal(1, 2, 10, 20, "marry", 300)
    assert p is not None
    assert store.get_proposal(p.id) == p

    # Duplicate (same proposer/target/kind) rejected while open
    assert store.create_proposal(1, 2, 10, 20, "marry", 300) is None
    # Different kind allowed
    assert store.create_proposal(1, 2, 10, 20, "adopt", 300) is not None
    # Reverse direction allowed
    assert store.create_proposal(1, 2, 20, 10, "marry", 300) is not None

    store.delete_proposal(p.id)
    assert store.get_proposal(p.id) is None
    assert store.create_proposal(1, 2, 10, 20, "marry", 300) is not None


def test_proposal_expiry(store: Store) -> None:
    store.create_proposal(1, 2, 10, 20, "marry", ttl_seconds=-1)
    assert store.expire_proposals() == 1
    assert store.proposals_for(20) == []


def test_proposals_for_filters(store: Store) -> None:
    store.create_proposal(1, 2, 10, 20, "marry", 300)
    store.create_proposal(1, 2, 30, 20, "adopt", 300)
    assert len(store.proposals_for(20)) == 2
    assert len(store.proposals_for(20, "marry")) == 1
    assert store.proposals_for(21) == []


def test_blocks(store: Store) -> None:
    store.add_block(1, 2)
    assert store.is_blocked(1, 2) is True
    assert store.is_blocked(2, 1) is False
    assert store.blocked_users(1) == [2]
    assert store.remove_block(1, 2) is True
    assert store.is_blocked(1, 2) is False


def test_guild_settings(store: Store) -> None:
    assert store.get_prefix(1) is None
    store.set_prefix(1, "?")
    assert store.get_prefix(1) == "?"
    store.set_prefix(1, "$")
    assert store.get_prefix(1) == "$"

    assert store.get_allow_incest(1) is False
    store.set_allow_incest(1, True)
    assert store.get_allow_incest(1) is True
    # prefix survives incest toggle
    assert store.get_prefix(1) == "$"
    # other guild unaffected
    assert store.get_allow_incest(2) is False


def test_family_size(store: Store) -> None:
    # 1 - 2 partners; 1 -> 3 child; 3 -> 4 grandchild; 4 partners 5
    store.add_partners(1, 2)
    store.add_child(1, 3)
    store.add_child(3, 4)
    store.add_partners(4, 5)
    assert store.family_size(1) == 4
    assert store.family_size(2) == 4
    assert store.family_size(99) == 0


def test_stats(store: Store) -> None:
    store.add_partners(1, 2)
    store.add_child(1, 3)
    store.create_proposal(9, 9, 5, 6, "marry", 300)
    store.add_block(7, 8)
    s = store.stats()
    assert s["marriages"] == 1
    assert s["parent_child_links"] == 1
    assert s["open_proposals"] == 1
    assert s["blocks"] == 1


def test_persistence(tmp_path) -> None:
    db = tmp_path / "m.db"
    s = Store(str(db))
    s.add_partners(1, 2)
    s.close()
    s2 = Store(str(db))
    assert s2.partners_of(1) == [2]
    s2.close()
