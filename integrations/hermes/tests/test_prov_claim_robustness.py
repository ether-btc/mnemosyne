"""Regression: one unclaimable pending record must not abort the whole batch."""
import json, sys, uuid
from pathlib import Path
import pytest
import mnemosyne_hermes as mh

_claim = mh._claim_pending_record
Expected = _claim.__globals__["PendingClaimError"]


def _write(p: Path, n: int) -> Path:
    d = p / "pending"; d.mkdir(exist_ok=True)
    for i in range(n):
        (d / f"r{i}.json").write_text(json.dumps({"id": f"r{i}"}), encoding="utf-8")
    return d


def test_non_enoent_oserror_raises_pending_claim_error(tmp_path, monkeypatch):
    rec = tmp_path / "rec.json"; rec.write_text("{}", encoding="utf-8")
    def boom(self, target, *a, **k): raise OSError(28, "No space left on device")
    monkeypatch.setattr(Path, "rename", boom)
    with pytest.raises(Expected):
        _claim(rec)


def test_failed_claim_leaves_no_stray_claim_file(tmp_path, monkeypatch):
    rec = tmp_path / "rec.json"; rec.write_text("{}", encoding="utf-8")
    def boom(self, target, *a, **k): raise OSError(28, "No space left on device")
    monkeypatch.setattr(Path, "rename", boom)
    with pytest.raises(Expected):
        _claim(rec)
    assert list(tmp_path.glob(".*.claim")) == []
    assert rec.exists()


def test_happy_path_still_atomic(tmp_path):
    rec = tmp_path / "rec.json"; rec.write_text('{"id":"r"}', encoding="utf-8")
    c = _claim(rec)
    assert c is not None and c.exists() and not rec.exists()
