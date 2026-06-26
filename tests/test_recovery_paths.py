"""Tests for recovery.get_default_paths() honoring the same path configuration
as the live store (mnemosyne.core.beam).

The disaster-recovery helpers (backup/restore, and `mnemosyne reindex`'s
auto-backup) must resolve the database to the same location the store actually
uses. Previously they hardcoded ``~/.mnemosyne/data`` and ignored
MNEMOSYNE_DATA_DIR / HERMES_HOME, so they operated on (or failed to find) the
wrong database.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from mnemosyne.dr import recovery


def test_get_default_paths_honors_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("MNEMOSYNE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("MNEMOSYNE_BACKUP_DIR", raising=False)
    data_dir, backup_dir, db_path = recovery.get_default_paths()
    assert data_dir == tmp_path / "data"
    assert db_path == tmp_path / "data" / "mnemosyne.db"
    # backups land alongside the data dir, not under ~/.mnemosyne
    assert backup_dir == tmp_path / "backups"


def test_get_default_paths_honors_hermes_home(monkeypatch, tmp_path):
    monkeypatch.delenv("MNEMOSYNE_DATA_DIR", raising=False)
    monkeypatch.delenv("MNEMOSYNE_BACKUP_DIR", raising=False)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home"))
    data_dir, backup_dir, db_path = recovery.get_default_paths()
    assert data_dir == tmp_path / "home" / "mnemosyne" / "data"
    assert db_path == data_dir / "mnemosyne.db"
    assert backup_dir == tmp_path / "home" / "mnemosyne" / "backups"


def test_get_default_paths_backup_dir_override(monkeypatch, tmp_path):
    monkeypatch.setenv("MNEMOSYNE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MNEMOSYNE_BACKUP_DIR", str(tmp_path / "custom_backups"))
    _, backup_dir, _ = recovery.get_default_paths()
    assert backup_dir == tmp_path / "custom_backups"


def test_get_default_paths_data_dir_takes_precedence_over_hermes_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MNEMOSYNE_DATA_DIR", str(tmp_path / "explicit"))
    data_dir, _, db_path = recovery.get_default_paths()
    assert data_dir == tmp_path / "explicit"
    assert db_path == tmp_path / "explicit" / "mnemosyne.db"


def test_create_backup_succeeds_with_sqlite_vec_tables(tmp_path):
    """Regression: create_backup() must load sqlite-vec on the source AND
    destination connections, otherwise sqlite3.Connection.backup() and
    Connection.iterdump() both fail with ``no such module: vec0`` on
    databases that use vec0 virtual tables.

    Pre-fix: this test fails with ``sqlite3.OperationalError: no such
    module: vec0`` raised from inside the backup serialization path.
    """
    pytest.importorskip("sqlite_vec")

    db_path = tmp_path / "vec_test.db"
    backup_dir = tmp_path / "backups"

    # Build a tiny DB that has a vec0 virtual table — the exact schema
    # shape that triggered the original bug in 3.10.x.
    conn = sqlite3.connect(str(db_path))
    conn.enable_load_extension(True)
    import sqlite_vec
    sqlite_vec.load(conn)
    conn.execute(
        "CREATE VIRTUAL TABLE vec_items USING vec0("
        "embedding float[4] distance_metric=cosine)"
    )
    conn.execute("CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT)")
    conn.executemany("INSERT INTO meta VALUES (?, ?)", [("a", "1"), ("b", "2")])
    conn.commit()
    conn.close()

    # Act: this is the call path `mnemosyne backup` uses. Pre-fix it
    # raised sqlite3.OperationalError: no such module: vec0.
    result = recovery.create_backup(db_path=db_path, backup_dir=backup_dir)

    # Assert: backup file exists, is non-empty, gzipped, and the gz
    # contents contain the vec0 table definition.
    assert Path(result["backup_path"]).exists()
    assert result["backup_size"] > 0
    import gzip
    with gzip.open(result["backup_path"], "rt") as f:
        dump = f.read()
    assert "vec_items" in dump
    assert "CREATE VIRTUAL TABLE" in dump
