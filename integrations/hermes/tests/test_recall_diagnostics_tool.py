from __future__ import annotations

import json

from mnemosyne_hermes import MnemosyneMemoryProvider


def _provider(tmp_path) -> MnemosyneMemoryProvider:
    provider = MnemosyneMemoryProvider()
    provider.initialize("session-1", hermes_home=str(tmp_path), agent_identity="profile_a")
    assert provider._beam is not None
    return provider


def _close(provider: MnemosyneMemoryProvider) -> None:
    try:
        provider._beam.conn.close()
    except Exception:
        pass


def test_recall_diagnostics_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("MNEMOSYNE_RECALL_DIAGNOSTICS", raising=False)
    provider = _provider(tmp_path)
    try:
        result = json.loads(provider.handle_tool_call(
            "mnemosyne_recall_diagnostics", {}
        ))
        assert result["status"] == "disabled"
    finally:
        _close(provider)


def test_recall_diagnostics_enabled_and_reset(tmp_path, monkeypatch):
    monkeypatch.setenv("MNEMOSYNE_RECALL_DIAGNOSTICS", "1")
    provider = _provider(tmp_path)
    try:
        from mnemosyne.core.recall_diagnostics import get_recall_diagnostics, reset_recall_diagnostics

        reset_recall_diagnostics()
        provider._beam.remember("Diagnostic test memory about recall", importance=0.7)
        provider._beam.recall("diagnostic recall", top_k=5)

        before = get_recall_diagnostics()
        assert before["totals"]["calls"] >= 1

        result = json.loads(provider.handle_tool_call(
            "mnemosyne_recall_diagnostics", {"reset": True}
        ))
        assert result["reset"] is True
        assert result["diagnostics"]["totals"]["calls"] >= 1

        after = get_recall_diagnostics()
        assert after["totals"]["calls"] == 0
    finally:
        _close(provider)


def test_recall_diagnostics_schema_exposed():
    provider = MnemosyneMemoryProvider()
    names = {schema["name"] for schema in provider.get_tool_schemas()}
    assert "mnemosyne_recall_diagnostics" in names
