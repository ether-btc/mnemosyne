"""
Mnemosyne Disaster Recovery System

Comprehensive backup, restore, and integrity verification for Mnemosyne.
"""

import gzip
import logging
import os
import json
import hashlib
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List


def _load_sqlite_vec(conn):
    """Load the sqlite-vec extension on a connection, if it is installed.

    Without it sqlite3 refuses to touch vec0 virtual tables ("no such
    module: vec0") -- during backup serialization and during restore.
    """
    try:
        import sqlite_vec
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
    except (ImportError, sqlite3.OperationalError):
        pass  # optional extra; absence just means no vec0 tables


def get_default_paths():
    """Get default Mnemosyne paths.

    These MUST resolve to the same location the live store uses (see
    ``mnemosyne.core.beam``), or backup/restore -- and ``mnemosyne reindex``'s
    auto-backup -- operate on a different database than the one in use. The
    precedence mirrors beam:

    * data dir: ``MNEMOSYNE_DATA_DIR`` if set, else
      ``$HERMES_HOME/mnemosyne/data`` (``HERMES_HOME`` defaults to ``~/.hermes``).
    * backups: ``MNEMOSYNE_BACKUP_DIR`` if set, else a ``backups`` dir alongside
      the data dir.

    Previously this hardcoded ``~/.mnemosyne/data``, which disagreed with the
    store whenever ``MNEMOSYNE_DATA_DIR`` or ``HERMES_HOME`` was set, so
    operations failed with "Database not found".
    """
    if os.environ.get("MNEMOSYNE_DATA_DIR"):
        data_dir = Path(os.environ["MNEMOSYNE_DATA_DIR"])
    else:
        root = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
        data_dir = root / "mnemosyne" / "data"
    backup_dir = Path(os.environ.get("MNEMOSYNE_BACKUP_DIR", data_dir.parent / "backups"))
    db_path = data_dir / "mnemosyne.db"
    return data_dir, backup_dir, db_path


def create_backup(db_path: Path = None, backup_dir: Path = None) -> Dict:
    """
    Create a compressed backup of the database.

    Note: db_checksum covers the main database file only (sha256 of
    read_bytes); -wal/-shm sidecars are not covered.

    Returns:
        Dict with backup_path, size, checksum, and timestamp
    """
    _, default_backup_dir, default_db = get_default_paths()
    db_path = db_path or default_db
    backup_dir = backup_dir or default_backup_dir
    
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")
    
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"mnemosyne_backup_{timestamp}.db.gz"
    backup_path = backup_dir / backup_name
    
    # Use sqlite3 online backup API instead of shutil.copyfileobj.
    # sqlite3.backup() is lock-aware (acquires read-lock), includes
    # uncommitted WAL frames, and is atomic — it won't produce a torn
    # file if a checkpoint runs partway through. The old copyfileobj
    # approach only copied the .db file, missed .db-wal frames, and
    # could produce corrupted backups under concurrent write load.
    # OPEN THE SOURCE READ-ONLY. A read-write connection to a WAL database can
    # become the "last connection" and, on close, checkpoint and unlink the
    # -wal/-shm files. If another long-lived process (the Hermes agent) still
    # holds those sidecars open, every later statement in that process fails
    # with SQLITE_IOERR "disk I/O error" until it restarts. Backups only read,
    # so mode=ro is both correct and non-disturbing.
    src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    # Load sqlite-vec on BOTH connections: without it src.backup(dst) and the
    # serialization step both fail with "no such module: vec0".
    # Mirrors the graceful-fallback pattern in core/beam.py.
    _load_sqlite_vec(src)
    dst = sqlite3.connect(":memory:")
    _load_sqlite_vec(dst)
    src.backup(dst)
    src.close()

    # Serialize the in-memory backup → gzip → disk.
    # Binary SQLite payload (exact page copy, keeps vec0 virtual tables and
    # FTS index state intact). The previous SQL-text dump could not be
    # replayed reliably: iterdump() also emits the FTS5 shadow tables, and
    # replaying those rows against the shadow tables SQLite recreates itself
    # fails ("already exists" / UNIQUE) and aborts the restore.
    try:
        payload = dst.serialize()
    except AttributeError:  # pragma: no cover - Python < 3.11
        tmp_db = backup_path.with_suffix(".tmp.db")
        file_dst = sqlite3.connect(str(tmp_db))
        _load_sqlite_vec(file_dst)
        dst.backup(file_dst)
        file_dst.close()
        payload = tmp_db.read_bytes()
        tmp_db.unlink()
    dst.close()

    with gzip.open(backup_path, "wb") as f_out:
        f_out.write(payload)
    
    # Calculate checksums
    db_checksum = hashlib.sha256(db_path.read_bytes()).hexdigest()[:16]
    backup_checksum = hashlib.sha256(backup_path.read_bytes()).hexdigest()[:16]
    
    # Create metadata
    metadata = {
        "timestamp": timestamp,
        "original_size": db_path.stat().st_size,
        "backup_size": backup_path.stat().st_size,
        "db_checksum": db_checksum,
        "backup_checksum": backup_checksum,
        "compressed": True,
        "format": "sqlite-binary-v1"
    }
    
    # Save metadata
    meta_path = backup_path.with_suffix('.gz.json')
    with open(meta_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    return {
        "backup_path": str(backup_path),
        "metadata_path": str(meta_path),
        **metadata
    }


def _live_restore_allowed() -> bool:
    """Guard env parsing for MNEMOSYNE_ALLOW_LIVE_RESTORE.

    Accepts only {"1", "true", "yes"} case-insensitively (whitespace
    stripped). Everything else (including unset/empty) refuses.
    """
    value = os.environ.get("MNEMOSYNE_ALLOW_LIVE_RESTORE", "")
    return value.strip().lower() in {"1", "true", "yes"}


def restore_backup(backup_path: Path, db_path: Path = None) -> Dict:
    """
    Restore database from a compressed backup.
    
    Args:
        backup_path: Path to the .gz backup file
        db_path: Destination database path (default: ~/.mnemosyne/data/mnemosyne.db)
        
    Returns:
        Dict with restore status and details

    Note: restored=True can be returned with integrity_check=False; the
    caller must check integrity_check.
    """
    _, _, default_db = get_default_paths()
    db_path = db_path or default_db

    if not backup_path.exists():
        raise FileNotFoundError(f"Backup not found: {backup_path}")

    # Restoring OVER the live database while the agent holds it open replaces
    # the pages under a running process (its -wal/-shm map to the old inode),
    # leaving it with SQLITE_IOERR "disk I/O error" until it restarts.
    # Fail closed: the live path needs an explicit opt-in from the operator.
    # Sidecar refusal first (a live holder leaves -wal/-shm behind), regardless
    # of how default_db resolved.
    if Path(str(db_path) + "-wal").exists() and Path(str(db_path) + "-shm").exists():
        raise RuntimeError(
            "Refusing to restore over the live database: -wal and -shm sidecars present"
        )
    if Path(db_path).resolve() == Path(default_db).resolve() and not _live_restore_allowed():
        raise RuntimeError(
            "Refusing to restore over the live database: stop the Hermes agent "
            "first, or set MNEMOSYNE_ALLOW_LIVE_RESTORE=1 if you accept that the "
            "running process must be restarted afterwards."
        )
    
    # Create emergency backup of current DB
    if db_path.exists():
        emergency_path = db_path.with_suffix('.emergency_backup.db')
        # NOTE: this emergency copy is a RAW main-file copy (shutil.copy2 on
        # the .db only). It misses uncheckpointed -wal frames and must not be
        # treated as a recovery source.
        shutil.copy2(db_path, emergency_path)
    
    # Decompress and restore using sqlite3 backup API
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with gzip.open(backup_path, "rb") as f_in:
        payload = f_in.read()

    def _is_shadow_stmt(stmt: str) -> bool:
        """True for the shadow-table DDL/DML that SQLite recreates itself.

        Parses the statement's actual target identifier instead of substring
        matching, so lookalike content (e.g. a row whose text mentions a
        shadow table name, or an *_archive table) is NOT treated as a shadow.
        """
        low = stmt.lower().strip()
        if "create virtual table" in low:
            return False

        import re

        dq, sq, bq = '"', "'", "`"
        ident = rf"(?:[{dq}{sq}{bq}]?[A-Za-z_][\w$]*[{dq}{sq}{bq}]?)"

        def _strip_quotes(name: str) -> str:
            name = name.strip()
            if len(name) >= 2 and name[0] == name[-1] and name[0] in (dq, sq, bq):
                return name[1:-1]
            return name

        name = None
        m = re.match(rf"create\s+(?:or\s+replace\s+)?(?:temp(?:orary)?\s+)?table\s+(?:if\s+not\s+exists\s+)?({ident})", low, re.IGNORECASE)
        if m:
            name = _strip_quotes(m.group(1))
        else:
            m = re.match(rf"insert\s+(?:or\s+\w+\s+)?into\s+({ident})", low, re.IGNORECASE)
            if m:
                name = _strip_quotes(m.group(1))
            else:
                m = re.match(rf"delete\s+from\s+({ident})", low, re.IGNORECASE)
                if m:
                    name = _strip_quotes(m.group(1))
                else:
                    m = re.match(rf"alter\s+table\s+({ident})", low, re.IGNORECASE)
                    if m:
                        name = _strip_quotes(m.group(1))

        if name is None:
            return False

        fts_bases = ("fts_episodes", "fts_facts", "fts_working")
        vec_bases = ("vec_episodes", "vec_facts", "vec_working")
        fts_suffixes = ("_config", "_data", "_docsize", "_idx", "_content")
        vec_suffixes = ("_chunks", "_rowids", "_info", "_vector_chunks")

        shadow_names = set()
        for base in fts_bases:
            for sfx in fts_suffixes:
                shadow_names.add(base + sfx)
        for base in vec_bases:
            for sfx in vec_suffixes:
                shadow_names.add(base + sfx)

        return name in shadow_names

    if payload[:16] == b"SQLite format 3\x00":
        # Binary backup (format sqlite-binary-v1): exact page copy.
        tmp_db = db_path.with_suffix(".restore.tmp.db")
        try:
            tmp_db.write_bytes(payload)
            src_db = sqlite3.connect(str(tmp_db))
            _load_sqlite_vec(src_db)
            integrity = src_db.execute("PRAGMA quick_check;").fetchone()[0] == "ok"
            if not integrity:
                src_db.close()
                raise RuntimeError("Backup failed integrity check; restore aborted")
            target_db = sqlite3.connect(str(db_path))
            _load_sqlite_vec(target_db)
            src_db.backup(target_db)
            src_db.close()
            target_db.close()
        finally:
            tmp_db.unlink(missing_ok=True)
    else:
        # Legacy SQL-text dump (pre sqlite-binary-v1). Replay statement by
        # statement: FTS5 shadow-table statements are skipped because the
        # virtual-table DDL recreates those shadows itself (the explicit
        # shadow rows in a dump collide and abort the whole restore), and the
        # full-text index must be rebuilt afterwards. Any other failure is
        # fatal so a partial restore is never reported as success.
        sql_dump = payload.decode("utf-8")
        mem_db = sqlite3.connect(":memory:")
        _load_sqlite_vec(mem_db)
        stmt = ""
        skipped_fts = 0
        executed = 0
        for raw in sql_dump.splitlines():
            stmt += raw + "\n"
            if not sqlite3.complete_statement(stmt):
                continue
            if not stmt.strip():
                stmt = ""
                continue
            if _is_shadow_stmt(stmt):
                skipped_fts += 1
                logging.getLogger(__name__).warning(
                    "restore: skipping shadow statement: %s", stmt.strip()
                )
                stmt = ""
                continue
            mem_db.execute(stmt)
            executed += 1
            stmt = ""
        if stmt.strip():
            if _is_shadow_stmt(stmt):
                skipped_fts += 1
                logging.getLogger(__name__).warning(
                    "restore: skipping shadow statement: %s", stmt.strip()
                )
            else:
                mem_db.execute(stmt)
                executed += 1
        if skipped_fts:
            print(f"restore: skipped {skipped_fts} FTS shadow statement(s); "
                  "run a reindex/rebuild if full-text search returns empty.")
        # C1: fail-closed empty legacy payload
        schema_objects = mem_db.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()[0]
        if executed == 0 or schema_objects == 0:
            mem_db.close()
            raise RuntimeError(
                "Refusing to restore empty legacy payload: no statements replayed"
            )
        # Commit any open transaction from replayed DML before backing up:
        # sqlite3.Connection.backup() blocks when the source holds an open
        # write transaction (a replayed INSERT/DELETE leaves one open under
        # Python's implicit-transaction rules).
        mem_db.commit()
        target_db = sqlite3.connect(str(db_path))
        _load_sqlite_vec(target_db)
        mem_db.backup(target_db)
        mem_db.close()
        target_db.close()

    # Verify restored database
    is_valid = verify_integrity(db_path)
    
    return {
        "restored": True,
        "backup_used": str(backup_path),
        "database_path": str(db_path),
        "integrity_check": is_valid
    }


def emergency_restore(backup_dir: Path = None, db_path: Path = None) -> Dict:
    """
    Automatically restore from the most recent valid backup.
    
    Returns:
        Dict with restore status
    """
    _, default_backup_dir, default_db = get_default_paths()
    backup_dir = backup_dir or default_backup_dir
    db_path = db_path or default_db
    
    # Find all backups
    backups = sorted(backup_dir.glob("mnemosyne_backup_*.db.gz"), reverse=True)
    
    if not backups:
        raise FileNotFoundError("No backups found in " + str(backup_dir))
    
    # Try each backup until one works
    for backup in backups:
        try:
            result = restore_backup(backup, db_path)
            if result["integrity_check"]:
                return {
                    "restored": True,
                    "backup_used": str(backup),
                    "attempts": 1
                }
        except Exception as exc:
            if isinstance(exc, RuntimeError) and "refusing to restore over the live database" in str(exc).lower():
                raise
            continue
    
    raise RuntimeError("All backups failed integrity check")


def verify_integrity(db_path: Path = None) -> bool:
    """
    Verify SQLite database integrity.
    
    Returns:
        True if database is valid, False otherwise
    """
    import sqlite3
    
    _, _, default_db = get_default_paths()
    db_path = db_path or default_db
    
    if not db_path.exists():
        return False
    
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cursor = conn.cursor()
        
        # Run PRAGMA integrity_check
        cursor.execute("PRAGMA integrity_check")
        result = cursor.fetchone()
        
        conn.close()
        
        return result[0] == "ok"
    except Exception:
        return False


def list_backups(backup_dir: Path = None) -> List[Dict]:
    """
    List all available backups with metadata.
    
    Returns:
        List of backup information dictionaries
    """
    _, default_backup_dir, _ = get_default_paths()
    backup_dir = backup_dir or default_backup_dir
    
    backups = []
    for backup_file in sorted(backup_dir.glob("mnemosyne_backup_*.db.gz"), reverse=True):
        meta_file = backup_file.with_suffix('.gz.json')
        
        info = {
            "file": str(backup_file),
            "name": backup_file.name,
            "size": backup_file.stat().st_size,
            "modified": datetime.fromtimestamp(backup_file.stat().st_mtime).isoformat()
        }
        
        if meta_file.exists():
            with open(meta_file) as f:
                info["metadata"] = json.load(f)
        
        backups.append(info)
    
    return backups


def rotate_backups(backup_dir: Path = None, keep: int = 10) -> Dict:
    """
    Rotate backups, keeping only the most recent N.
    
    Args:
        keep: Number of backups to retain
        
    Returns:
        Dict with rotation results
    """
    _, default_backup_dir, _ = get_default_paths()
    backup_dir = backup_dir or default_backup_dir
    
    backups = sorted(backup_dir.glob("mnemosyne_backup_*.db.gz"))
    
    to_delete = backups[:-keep] if len(backups) > keep else []
    deleted = []
    
    for backup in to_delete:
        # Delete backup and metadata
        backup.unlink()
        meta = backup.with_suffix('.gz.json')
        if meta.exists():
            meta.unlink()
        deleted.append(backup.name)
    
    return {
        "total_backups": len(backups),
        "kept": keep,
        "deleted": len(deleted),
        "deleted_files": deleted
    }


def health_check() -> Dict:
    """
    Comprehensive health check of Mnemosyne system.
    
    Returns:
        Dict with health status of all components
    """
    data_dir, backup_dir, db_path = get_default_paths()
    
    # Check database
    db_exists = db_path.exists()
    db_valid = verify_integrity(db_path) if db_exists else False
    
    # Check backups
    backups = list(backup_dir.glob("mnemosyne_backup_*.db.gz")) if backup_dir.exists() else []
    
    return {
        "database": {
            "exists": db_exists,
            "valid": db_valid,
            "path": str(db_path),
            "message": "Database integrity verified" if db_valid else "Database missing or corrupt"
        },
        "backups": {
            "total": len(backups),
            "latest": str(backups[-1]) if backups else None,
            "directory": str(backup_dir)
        },
        "status": "healthy" if db_valid else "unhealthy"
    }


# CLI interface
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python -m mnemosyne.dr [backup|restore|emergency|verify|list|health|rotate]")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "backup":
        result = create_backup()
        print(json.dumps(result, indent=2))
    
    elif cmd == "restore" and len(sys.argv) > 2:
        result = restore_backup(Path(sys.argv[2]))
        print(json.dumps(result, indent=2))
    
    elif cmd == "emergency":
        result = emergency_restore()
        print(json.dumps(result, indent=2))
    
    elif cmd == "verify":
        valid = verify_integrity()
        print(json.dumps({"valid": valid}))
    
    elif cmd == "list":
        backups = list_backups()
        print(json.dumps(backups, indent=2))
    
    elif cmd == "health":
        status = health_check()
        print(json.dumps(status, indent=2))
    
    elif cmd == "rotate":
        result = rotate_backups()
        print(json.dumps(result, indent=2))
    
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
