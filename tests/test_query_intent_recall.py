"""Regression tests for query-intent recall weighting."""

import os
import tempfile
from pathlib import Path


def test_query_intent_classification_and_weight_adjustment():
    from mnemosyne.core.query_intent import adjust_weights, classify_intent

    temporal = classify_intent("what happened last week")
    assert temporal.category == "temporal"
    tv, tf, ti = adjust_weights(0.5, 0.3, 0.2, temporal)
    assert round(tv + tf + ti, 6) == 1.0
    assert tf > 0.3
    assert tv < 0.5

    procedural = classify_intent("how do I deploy this service")
    assert procedural.category == "procedural"
    pv, pf, pi = adjust_weights(0.5, 0.3, 0.2, procedural)
    assert round(pv + pf + pi, 6) == 1.0
    assert pv > 0.5
    assert pi < 0.2

    preference = classify_intent("which option should I choose")
    assert preference.category == "preference"
    _, _, pref_i = adjust_weights(0.5, 0.3, 0.2, preference)
    assert pref_i > 0.2


def test_recall_works_with_query_intent_enabled_and_disabled(monkeypatch):
    from mnemosyne.core.beam import BeamMemory

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "mnemosyne.db"
        beam = BeamMemory(session_id="test", db_path=db_path)
        beam.remember("Yesterday we configured the deployment workflow", importance=0.8)
        beam.remember("The user prefers compact direct answers", importance=0.9)

        monkeypatch.delenv("MNEMOSYNE_QUERY_INTENT", raising=False)
        off_results = beam.recall("what happened yesterday", top_k=5)
        assert off_results

        monkeypatch.setenv("MNEMOSYNE_QUERY_INTENT", "1")
        on_results = beam.recall("what happened yesterday", top_k=5)
        assert on_results
        assert any("Yesterday" in r.get("content", "") for r in on_results)


def test_explicit_recall_weights_override_query_intent(monkeypatch):
    from mnemosyne.core.beam import BeamMemory

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "mnemosyne.db"
        beam = BeamMemory(session_id="test", db_path=db_path)
        beam.remember("Last week we changed the deployment workflow", importance=0.7)

        monkeypatch.setenv("MNEMOSYNE_QUERY_INTENT", "1")
        results = beam.recall(
            "what happened last week",
            top_k=5,
            vec_weight=0.2,
            fts_weight=0.7,
            importance_weight=0.1,
        )
        assert results
