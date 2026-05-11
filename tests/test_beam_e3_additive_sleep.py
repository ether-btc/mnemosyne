"""Regression tests for E3 — additive sleep().

Pre-E3 contract: BeamMemory.sleep() consolidated old working_memory rows
into an episodic_memory summary and then DELETED the source rows. The
new contract (per maintainer decision 2026-05-10: "Kill summarize-and-
delete. Originals stay.") is additive:

  - Source working_memory rows REMAIN after sleep
  - A new `consolidated_at` TIMESTAMP column on working_memory is set on
    the rows sleep processed
  - sleep() doesn't pick up rows that already have consolidated_at set
    (so calling sleep twice doesn't double-summarize the same originals)
  - Recall surfaces both the original working_memory row AND the
    episodic summary row when both are relevant

This blocks experiment Arm B (ADD-only ingest) of the BEAM-recovery
experiment.
"""

import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from mnemosyne.core.beam import BeamMemory


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test.db"


def _wm_count(db_path, session_id=None):
    conn = sqlite3.connect(str(db_path))
    try:
        if session_id is None:
            return conn.execute("SELECT COUNT(*) FROM working_memory").fetchone()[0]
        return conn.execute(
            "SELECT COUNT(*) FROM working_memory WHERE session_id = ?",
            (session_id,),
        ).fetchone()[0]
    finally:
        conn.close()


def _consolidated_rows(db_path, session_id):
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute(
            "SELECT id, consolidated_at FROM working_memory "
            "WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
    finally:
        conn.close()


def _seed_old_wm(db_path, session_id, n, ts_offset_hours=20):
    """Insert n old working_memory rows for the given session. Uses
    distinct content per row so each is uniquely identifiable."""
    conn = sqlite3.connect(str(db_path))
    ts = (datetime.now() - timedelta(hours=ts_offset_hours)).isoformat()
    rows = [
        (f"e3-{session_id}-{i}", f"e3-content-{i}", "conversation", ts, session_id)
        for i in range(n)
    ]
    conn.executemany(
        "INSERT INTO working_memory (id, content, source, timestamp, session_id) "
        "VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()
    return [r[0] for r in rows]


class TestE3AdditiveSleep:

    def test_sleep_preserves_working_memory_rows(self, temp_db):
        """Post-E3, source working_memory rows survive sleep()."""
        beam = BeamMemory(session_id="s1", db_path=temp_db)
        seeded_ids = _seed_old_wm(temp_db, "s1", n=3)

        assert _wm_count(temp_db, "s1") == 3

        result = beam.sleep(dry_run=False)
        assert result["status"] == "consolidated"
        assert result["items_consolidated"] == 3

        # The whole point of E3: originals stay.
        post_count = _wm_count(temp_db, "s1")
        assert post_count == 3, (
            f"sleep() deleted working_memory rows — pre-E3 behavior. "
            f"Expected 3 originals to remain, got {post_count}."
        )

        # IDs unchanged.
        conn = sqlite3.connect(str(temp_db))
        post_ids = sorted(r[0] for r in conn.execute(
            "SELECT id FROM working_memory WHERE session_id = 's1'"
        ).fetchall())
        conn.close()
        assert post_ids == sorted(seeded_ids)

    def test_sleep_marks_consolidated_at(self, temp_db):
        """After sleep, every processed row has consolidated_at set."""
        beam = BeamMemory(session_id="s1", db_path=temp_db)
        _seed_old_wm(temp_db, "s1", n=2)

        beam.sleep(dry_run=False)

        rows = _consolidated_rows(temp_db, "s1")
        assert len(rows) == 2
        for row_id, consolidated_at in rows:
            assert consolidated_at is not None, (
                f"row {row_id} survived sleep but consolidated_at is NULL "
                f"— sleep didn't mark it, so the next sleep cycle will "
                f"re-consolidate it and produce a duplicate summary."
            )

    def test_sleep_does_not_reconsolidate_marked_rows(self, temp_db):
        """Calling sleep twice doesn't pick up already-marked rows."""
        beam = BeamMemory(session_id="s1", db_path=temp_db)
        _seed_old_wm(temp_db, "s1", n=2)

        first = beam.sleep(dry_run=False)
        assert first["items_consolidated"] == 2
        first_episodic = sqlite3.connect(str(temp_db)).execute(
            "SELECT COUNT(*) FROM episodic_memory"
        ).fetchone()[0]

        # Second sleep should find no eligible rows (status no_op) and
        # crucially not create a second summary.
        second = beam.sleep(dry_run=False)
        assert second["status"] == "no_op", (
            f"sleep re-processed already-consolidated rows; got {second}"
        )

        second_episodic = sqlite3.connect(str(temp_db)).execute(
            "SELECT COUNT(*) FROM episodic_memory"
        ).fetchone()[0]
        assert second_episodic == first_episodic, (
            f"sleep produced a duplicate summary on the second call: "
            f"first={first_episodic}, second={second_episodic}"
        )

    def test_dry_run_does_not_mark_consolidated_at(self, temp_db):
        """Dry run must not mutate working_memory (no consolidated_at writes)."""
        beam = BeamMemory(session_id="s1", db_path=temp_db)
        _seed_old_wm(temp_db, "s1", n=2)

        result = beam.sleep(dry_run=True)
        assert result["status"] == "dry_run"

        rows = _consolidated_rows(temp_db, "s1")
        for row_id, consolidated_at in rows:
            assert consolidated_at is None, (
                f"dry_run set consolidated_at on row {row_id} — "
                f"dry_run must be side-effect-free."
            )

    def test_consolidated_originals_remain_recallable(self, temp_db, monkeypatch):
        """[E3] Originals stay queryable through recall() after sleep.
        Uses LLM-disabled path so unique tokens survive into the
        aaak-encoded summary; the assertion is that recall returns hits
        whose content matches the ORIGINAL working_memory row content,
        not just the summary."""
        monkeypatch.setattr(
            "mnemosyne.core.local_llm.llm_available", lambda: False
        )
        beam = BeamMemory(session_id="s1", db_path=temp_db)

        # Distinctive token only in the original, very unlikely to
        # appear in an aaak-encoded summary.
        conn = sqlite3.connect(str(temp_db))
        old_ts = (datetime.now() - timedelta(hours=20)).isoformat()
        conn.execute(
            "INSERT INTO working_memory (id, content, source, timestamp, session_id) "
            "VALUES (?, ?, ?, ?, ?)",
            ("orig1", "original wm marker zzzunique42", "conversation", old_ts, "s1"),
        )
        conn.commit()
        conn.close()

        beam.sleep(dry_run=False)

        results = beam.recall("zzzunique42", top_k=10)
        assert results, "consolidated original is unreachable through recall()"
        # The exact-token original should be findable; the wm row carries
        # tier=='working' in the post-recall shape.
        assert any(
            r.get("tier") == "working" and "zzzunique42" in (r.get("content") or "")
            for r in results
        ), (
            f"recall did not surface the original working_memory row that "
            f"carries the unique token. E3 contract requires originals "
            f"remain recallable. Got: "
            f"{[(r.get('tier'), (r.get('content') or '')[:40]) for r in results]}"
        )

    def test_sleep_remains_session_scoped_with_marker(self, temp_db):
        """E3 version of the legacy test_sleep_remains_session_scoped:
        cross-session row stays untouched (no consolidated_at marker)
        because the caller's session is s1."""
        beam = BeamMemory(session_id="s1", db_path=temp_db)
        _seed_old_wm(temp_db, "s1", n=1)
        _seed_old_wm(temp_db, "s2", n=1)

        beam.sleep(dry_run=False)

        conn = sqlite3.connect(str(temp_db))
        rows = conn.execute(
            "SELECT session_id, consolidated_at FROM working_memory ORDER BY session_id"
        ).fetchall()
        conn.close()

        # Both rows still exist; only s1's is marked.
        assert len(rows) == 2
        by_session = {r[0]: r[1] for r in rows}
        assert by_session["s1"] is not None, "s1 row not marked consolidated"
        assert by_session["s2"] is None, (
            "s2 row was marked despite caller being session s1 — cross-"
            "session leak on the consolidation marker"
        )

    def test_consolidated_at_column_added_on_legacy_db(self, temp_db):
        """Pre-E3 databases that don't have consolidated_at must get the
        column added by init_beam() without losing data."""
        # Simulate a legacy DB: create the working_memory table without
        # consolidated_at, insert a row, then re-init.
        legacy_conn = sqlite3.connect(str(temp_db))
        legacy_conn.execute("""
            CREATE TABLE working_memory (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                source TEXT,
                timestamp TEXT,
                session_id TEXT DEFAULT 'default',
                importance REAL DEFAULT 0.5,
                metadata_json TEXT,
                veracity TEXT DEFAULT 'unknown',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        old_ts = (datetime.now() - timedelta(hours=20)).isoformat()
        legacy_conn.execute(
            "INSERT INTO working_memory (id, content, source, timestamp, session_id) "
            "VALUES (?, ?, ?, ?, ?)",
            ("legacy-1", "legacy content", "conversation", old_ts, "s1"),
        )
        legacy_conn.commit()
        legacy_conn.close()

        # init_beam via BeamMemory construction should add the column.
        beam = BeamMemory(session_id="s1", db_path=temp_db)

        conn = sqlite3.connect(str(temp_db))
        cols = [r[1] for r in conn.execute("PRAGMA table_info(working_memory)").fetchall()]
        conn.close()
        assert "consolidated_at" in cols, (
            "init_beam did not add consolidated_at column to legacy DB"
        )

        # Legacy row should still be there with consolidated_at = NULL.
        rows = _consolidated_rows(temp_db, "s1")
        assert rows == [("legacy-1", None)]

        # And sleep should still process it (consolidated_at IS NULL).
        result = beam.sleep(dry_run=False)
        assert result["items_consolidated"] == 1
        rows = _consolidated_rows(temp_db, "s1")
        assert rows[0][1] is not None
