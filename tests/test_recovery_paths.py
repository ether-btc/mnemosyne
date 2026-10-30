"""Tests for recovery.get_default_paths() honoring the same path configuration
as the live store (mnemosyne.core.beam).

The disaster-recovery helpers (backup/restore, and `mnemosyne reindex`'s
auto-backup) must resolve the database to the same location the store actually
uses. Previously they hardcoded ``~/.mnemosyne/data`` and ignored
MNEMOSYNE_DATA_DIR / HERMES_HOME, so they operated on (or failed to find) the
wrong database.
"""
from __future__ import annotations

import gzip
import logging
import os
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
    # contents are a SQLite database image (format sqlite-binary-v1).
    #
    # The backup used to be a gzipped SQL text dump produced by iterdump().
    # That format could not be restored: iterdump() also emits the FTS5
    # shadow tables, and replaying those rows against the shadow tables
    # SQLite recreates itself fails ("table ... already exists" / UNIQUE),
    # which aborted every restore. The backup is now the raw SQLite image.
    assert Path(result["backup_path"]).exists()
    assert result["backup_size"] > 0
    assert result["format"] == "sqlite-binary-v1"
    import gzip
    with gzip.open(result["backup_path"], "rb") as f:
        payload = f.read()
    assert payload[:16] == b"SQLite format 3\x00"

    # The restored copy must carry the vec0 table and the source rows.
    restored = tmp_path / "restored.db"
    recovery.restore_backup(Path(result["backup_path"]), db_path=restored)
    rconn = sqlite3.connect(str(restored))
    rconn.enable_load_extension(True)
    import sqlite_vec
    sqlite_vec.load(rconn)
    tables = {r[0] for r in rconn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "vec_items" in tables
    assert rconn.execute("SELECT count(*) FROM meta").fetchone()[0] == 2
    assert rconn.execute("SELECT count(*) FROM vec_items").fetchone()[0] == 0
    rconn.close()


def test_backup_opens_source_read_only(tmp_path, monkeypatch):
    """A read-write source connection can become the last WAL holder and, on
    close, checkpoint and unlink -wal/-shm. Any process still holding those
    sidecars then fails every statement with SQLITE_IOERR. Backups only read,
    so the source must be opened with mode=ro.
    """
    db = tmp_path / "src.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE t(a)")
    conn.commit()
    conn.close()

    seen = []
    real_connect = sqlite3.connect

    def spy(dsn, *args, **kwargs):
        seen.append((str(dsn), kwargs.get("uri", False)))
        return real_connect(dsn, *args, **kwargs)

    monkeypatch.setattr(recovery.sqlite3, "connect", spy)
    recovery.create_backup(db_path=db, backup_dir=tmp_path / "backups")

    dsn, uri = seen[0]
    assert "mode=ro" in dsn and uri is True


def test_restore_refuses_live_path(tmp_path, monkeypatch):
    """Restoring over the live DB replaces pages under a running agent whose
    -wal/-shm map the old inode; it must need an explicit opt-in.
    """
    monkeypatch.setenv("MNEMOSYNE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("MNEMOSYNE_ALLOW_LIVE_RESTORE", raising=False)
    live = tmp_path / "data" / "mnemosyne.db"
    live.parent.mkdir(parents=True)
    conn = sqlite3.connect(str(live))
    conn.execute("CREATE TABLE t(a)")
    conn.commit()
    conn.close()

    backup = recovery.create_backup(db_path=live, backup_dir=tmp_path / "backups")
    with pytest.raises(RuntimeError, match="Refusing to restore over the live database"):
        recovery.restore_backup(Path(backup["backup_path"]))

    monkeypatch.setenv("MNEMOSYNE_ALLOW_LIVE_RESTORE", "1")
    result = recovery.restore_backup(Path(backup["backup_path"]))
    assert result["restored"] is True and result["integrity_check"] is True


def test_c1_empty_legacy_payload_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("MNEMOSYNE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MNEMOSYNE_ALLOW_LIVE_RESTORE", "1")
    data = tmp_path / "data"
    data.mkdir(parents=True)
    target = data / "mnemosyne.db"
    conn = sqlite3.connect(str(target))
    conn.execute("CREATE TABLE t(a)")
    conn.commit()
    conn.close()
    before = target.read_bytes()

    for payload in (b"", b"   \n\t"):
        backup = tmp_path / ("empty.gz" if payload == b"" else "ws.gz")
        with gzip.open(backup, "wb") as f:
            f.write(payload)
        with pytest.raises(RuntimeError):
            recovery.restore_backup(backup, db_path=target)
        assert target.read_bytes() == before


def test_c2_shadow_skip_regression(tmp_path, caplog):
    target = tmp_path / "target.db"
    sql = (
        "CREATE TABLE fts_facts_data (id INTEGER PRIMARY KEY, x TEXT);\n"
        "INSERT INTO fts_facts_data VALUES (1, 'shadow');\n"
        "CREATE TABLE t (id INTEGER PRIMARY KEY, note TEXT);\n"
        "INSERT INTO t VALUES (1, 'keep ... fts_facts_data ...');\n"
        "CREATE TABLE vec_facts_chunks_archive (id INTEGER);\n"
    )
    backup = tmp_path / "legacy.gz"
    with gzip.open(backup, "wb") as f:
        f.write(sql.encode())
    caplog.set_level(logging.WARNING, logger="mnemosyne.dr.recovery")
    recovery.restore_backup(backup, db_path=target)
    conn = sqlite3.connect(str(target))
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "t" in tables
    assert "vec_facts_chunks_archive" in tables
    assert "fts_facts_data" not in tables
    assert conn.execute("SELECT note FROM t").fetchone()[0] == "keep ... fts_facts_data ..."
    conn.close()
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 2


@pytest.mark.parametrize("val,allowed", [
    ("1", True), ("TRUE", True), ("Yes", True), ("true", True),
    ("0", False), ("false", False), ("no", False), ("", False),
])
def test_c3_live_restore_env_parsing(tmp_path, monkeypatch, val, allowed):
    monkeypatch.setenv("MNEMOSYNE_DATA_DIR", str(tmp_path / "data"))
    data = tmp_path / "data"
    data.mkdir(parents=True, exist_ok=True)
    db = data / "mnemosyne.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE t(a)")
    conn.commit()
    conn.close()
    backup = recovery.create_backup(db_path=db, backup_dir=tmp_path / "backups")
    if val == "":
        monkeypatch.delenv("MNEMOSYNE_ALLOW_LIVE_RESTORE", raising=False)
    else:
        monkeypatch.setenv("MNEMOSYNE_ALLOW_LIVE_RESTORE", val)
    if allowed:
        res = recovery.restore_backup(Path(backup["backup_path"]))
        assert res["restored"] is True
    else:
        with pytest.raises(RuntimeError, match="Refusing to restore over the live database"):
            recovery.restore_backup(Path(backup["backup_path"]))


def test_c4_sidecars_refuse(tmp_path, monkeypatch):
    monkeypatch.setenv("MNEMOSYNE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MNEMOSYNE_ALLOW_LIVE_RESTORE", "1")
    data = tmp_path / "data"
    data.mkdir(parents=True)
    db = data / "mnemosyne.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE t(a)")
    conn.commit()
    conn.close()
    (data / "mnemosyne.db-wal").write_bytes(b"x")
    (data / "mnemosyne.db-shm").write_bytes(b"y")
    backup = recovery.create_backup(db_path=db, backup_dir=tmp_path / "backups")
    before = db.read_bytes()
    with pytest.raises(RuntimeError, match="Refusing to restore over the live database"):
        recovery.restore_backup(Path(backup["backup_path"]))
    assert db.read_bytes() == before


def test_f5_verify_integrity_read_only(tmp_path, monkeypatch):
    db = tmp_path / "v.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE t(a)")
    conn.commit()
    conn.close()
    seen = []
    real = sqlite3.connect

    def spy(dsn, *a, **k):
        seen.append((str(dsn), k.get("uri", False)))
        return real(dsn, *a, **k)

    monkeypatch.setattr(recovery.sqlite3, "connect", spy)
    recovery.verify_integrity(db)
    assert seen and "mode=ro" in seen[0][0] and seen[0][1] is True


def test_f7_corrupt_binary_no_orphan(tmp_path):
    target = tmp_path / "target.db"
    conn = sqlite3.connect(str(target))
    conn.execute("CREATE TABLE t(a)")
    conn.commit()
    conn.close()
    payload = b"SQLite format 3\x00" + os.urandom(100)
    backup = tmp_path / "corrupt.gz"
    with gzip.open(backup, "wb") as f:
        f.write(payload)
    tmp = target.with_suffix(".restore.tmp.db")
    with pytest.raises(Exception):
        recovery.restore_backup(backup, db_path=target)
    assert not tmp.exists()


def test_f8_emergency_restore_raises_live_path(tmp_path, monkeypatch):
    monkeypatch.setenv("MNEMOSYNE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("MNEMOSYNE_ALLOW_LIVE_RESTORE", raising=False)
    data = tmp_path / "data"
    data.mkdir(parents=True)
    db = data / "mnemosyne.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE t(a)")
    conn.commit()
    conn.close()
    backup = recovery.create_backup(db_path=db, backup_dir=tmp_path / "backups")
    with pytest.raises(RuntimeError) as exc:
        recovery.emergency_restore(backup_dir=tmp_path / "backups", db_path=db)
    assert "Refusing to restore over the live database" in str(exc.value)
    assert "All backups failed integrity check" not in str(exc.value)
