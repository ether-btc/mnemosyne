"""Tests for the recall orchestrator compatibility wrapper."""

import tempfile
from pathlib import Path


def test_orchestrate_recall_with_beam_instance():
    from mnemosyne.core.beam import BeamMemory
    from mnemosyne.core.orchestrator import orchestrate_recall

    with tempfile.TemporaryDirectory() as tmpdir:
        beam = BeamMemory(session_id="test", db_path=Path(tmpdir) / "mnemosyne.db")
        beam.remember("Orchestrator test memory", importance=0.8)

        results = orchestrate_recall("orchestrator", beam=beam, top_k=3)
        assert results
        assert any("Orchestrator" in r.get("content", "") for r in results)


def test_orchestrate_recall_without_conn_uses_default_wrapper(monkeypatch, tmp_path):
    from mnemosyne.core.orchestrator import orchestrate_recall

    # Smoke test: no conn/beam should not raise even when no results exist.
    monkeypatch.setenv("MNEMOSYNE_DATA_DIR", str(tmp_path))
    results = orchestrate_recall("no matching memory", top_k=3)
    assert isinstance(results, list)
