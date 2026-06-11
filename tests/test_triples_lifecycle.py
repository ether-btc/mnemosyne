"""Tests for the temporal triple lifecycle: explicit valid_until, the supersede
flag (multi-valued facts), end() (expire without replace), as_of historical
queries, and case-insensitive subject matching.
"""

from pathlib import Path

from mnemosyne.core.triples import add_triple, end_triple, query_triples


def _objs(rows):
    return sorted(r["object"] for r in rows)


def test_supersede_default_closes_prior(tmp_path: Path):
    db = tmp_path / "triples.db"
    add_triple("alice", "city", "NYC", valid_from="2025-01-01", db_path=db)
    add_triple("alice", "city", "LA", valid_from="2026-01-01", db_path=db)
    # only the newest value is open now
    assert _objs(query_triples(subject="alice", predicate="city", db_path=db)) == ["LA"]


def test_as_of_returns_historical_value(tmp_path: Path):
    db = tmp_path / "triples.db"
    add_triple("alice", "city", "NYC", valid_from="2025-01-01", db_path=db)
    add_triple("alice", "city", "LA", valid_from="2026-01-01", db_path=db)
    assert _objs(query_triples(subject="alice", predicate="city",
                               as_of="2025-06-01", db_path=db)) == ["NYC"]


def test_supersede_false_allows_multivalued(tmp_path: Path):
    db = tmp_path / "triples.db"
    add_triple("user", "speaks", "English", supersede=False, db_path=db)
    add_triple("user", "speaks", "Spanish", supersede=False, db_path=db)
    assert _objs(query_triples(subject="user", predicate="speaks", db_path=db)) == ["English", "Spanish"]


def test_explicit_valid_until_expires(tmp_path: Path):
    db = tmp_path / "triples.db"
    add_triple("project", "status", "active", valid_until="2026-12-31", db_path=db)
    assert _objs(query_triples(subject="project", predicate="status", db_path=db)) == ["active"]
    assert query_triples(subject="project", predicate="status", as_of="2027-01-15", db_path=db) == []


def test_end_by_object_then_by_subject_predicate(tmp_path: Path):
    db = tmp_path / "triples.db"
    add_triple("user", "speaks", "English", supersede=False, db_path=db)
    add_triple("user", "speaks", "Spanish", supersede=False, db_path=db)
    assert end_triple("user", "speaks", "English", db_path=db) == 1
    assert _objs(query_triples(subject="user", predicate="speaks", db_path=db)) == ["Spanish"]
    assert end_triple("user", "speaks", db_path=db) == 1
    assert query_triples(subject="user", predicate="speaks", db_path=db) == []


def test_subject_match_is_case_insensitive(tmp_path: Path):
    db = tmp_path / "triples.db"
    add_triple("Alice", "city", "LA", db_path=db)
    assert _objs(query_triples(subject="alice", predicate="city", db_path=db)) == ["LA"]
    assert _objs(query_triples(subject="ALICE", predicate="city", db_path=db)) == ["LA"]


def test_add_triple_backcompat(tmp_path: Path):
    db = tmp_path / "triples.db"
    # old-style call without any of the new kwargs still works
    add_triple("bob", "likes", "tea", db_path=db)
    assert _objs(query_triples(subject="bob", predicate="likes", db_path=db)) == ["tea"]
