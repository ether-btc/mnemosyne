"""Tests for CLI verify --quick parsing and missing-database refusal."""

from __future__ import annotations

import sqlite3

import pytest

from mnemosyne import cli


def _make_simple_db(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    conn.executemany("INSERT INTO t VALUES (?, ?)", [(1, "a"), (2, "b")])
    conn.commit()
    conn.close()


def test_cmd_verify_quick_positional(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "src.db"
    _make_simple_db(db_path)

    monkeypatch.setattr(cli, "DATA_DIR", str(tmp_path / "data"))

    cli.cmd_verify(["--quick", str(db_path)])
    out = capsys.readouterr()
    assert "Database integrity check passed" in out.out

    cli.cmd_verify([str(db_path), "--quick"])
    out = capsys.readouterr()
    assert "Database integrity check passed" in out.out


def test_cmd_verify_quick_nonexistent_does_not_create_or_succeed(tmp_path, monkeypatch, capsys):
    nonexistent = tmp_path / "nope.db"
    assert not nonexistent.exists()
    monkeypatch.setattr(cli, "DATA_DIR", str(tmp_path / "data"))

    with pytest.raises(SystemExit) as exc:
        cli.cmd_verify(["--quick", str(nonexistent)])
    assert exc.value.code == 1
    assert not nonexistent.exists()
    out = capsys.readouterr()
    assert "passed" not in out.out.lower()