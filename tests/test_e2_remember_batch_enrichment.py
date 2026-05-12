"""
Regression tests for E2 — remember_batch enrichment parity with remember().

Pre-E2: ``BeamMemory.remember_batch`` skipped the post-insert enrichment
pipeline that ``BeamMemory.remember`` runs unconditionally
(`_add_temporal_triple` + `_ingest_graph_and_veracity`). High-throughput
ingest paths — including the BEAM benchmark adapter (E1) — bypassed the
annotation / gist / fact / consolidated-fact population entirely. The
polyphonic engine's graph + fact voices then had no data to fuse for
benchmark-scale recall queries — 4-voice RRF collapsed to 2 voices.

Post-E2: ``remember_batch`` mirrors ``remember()``'s post-insert
sequence:
  - Always-on (zero-LLM, rule-based / pattern-based):
    * `_add_temporal_triple` → annotations (occurred_on, has_source)
    * `_ingest_graph_and_veracity` → gists + facts + graph_edges +
      consolidated_facts (rule-based pattern extraction)
  - Opt-in via `extract_entities=True`:
    * `_extract_and_store_entities` → annotations (mentions)
  - Opt-in via `extract=True`:
    * `_extract_and_store_facts` → LLM-extracted facts table content

These tests pin:
  - Always-on parts fire for every batch row
  - Per-row source + veracity flow correctly into annotations + facts
  - Opt-in flags are respected (default off → no entity/LLM extraction)
  - Parity with ``remember()`` for the always-on parts
  - Benchmark-scale shape: 100-row batch still enriches every row
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from mnemosyne.core.beam import BeamMemory


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    return tmp_path / "mnemosyne_e2.db"


def _annotation_rows(conn: sqlite3.Connection, memory_id: str):
    return conn.execute(
        "SELECT kind, value, source, confidence "
        "FROM annotations WHERE memory_id = ? "
        "ORDER BY kind, value",
        (memory_id,),
    ).fetchall()


def _gist_count(conn: sqlite3.Connection, memory_id: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM gists WHERE memory_id = ?", (memory_id,)
    ).fetchone()[0]


def _fact_count(conn: sqlite3.Connection, memory_id: str) -> int:
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM facts WHERE memory_id = ?",
            (memory_id,),
        ).fetchone()[0]
    except sqlite3.OperationalError:
        return 0


def _consolidated_fact_count(conn: sqlite3.Connection) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM consolidated_facts"
    ).fetchone()[0]


# ---------------------------------------------------------------------------
# Always-on enrichment fires for every row in the batch
# ---------------------------------------------------------------------------


def test_remember_batch_writes_temporal_annotations_for_every_row(temp_db):
    """Each row should get an `occurred_on` annotation (date slice of
    the row's timestamp). Pre-fix this didn't happen — annotations
    table was empty after a batch insert."""
    beam = BeamMemory(session_id="e2-temporal", db_path=temp_db)
    ids = beam.remember_batch([
        {"content": "Alice deployed the service", "source": "convo"},
        {"content": "Bob filed a bug", "source": "convo"},
        {"content": "Carol approved the plan", "source": "convo"},
    ])
    assert len(ids) == 3
    for memory_id in ids:
        kinds = {row[0] for row in _annotation_rows(beam.conn, memory_id)}
        assert "occurred_on" in kinds, (
            f"{memory_id}: missing occurred_on annotation — "
            "_add_temporal_triple didn't fire"
        )


def test_remember_batch_writes_has_source_when_source_is_non_default(temp_db):
    """`has_source` annotation only fires for non-conversational
    sources (mirrors _add_temporal_triple's filter). Items with
    source='conversation' / 'user' / 'assistant' get only
    occurred_on; explicit non-default sources also get has_source."""
    beam = BeamMemory(session_id="e2-source", db_path=temp_db)
    ids = beam.remember_batch([
        {"content": "From a doc",  "source": "document"},
        {"content": "From convo",  "source": "conversation"},
    ])
    doc_kinds = {row[0] for row in _annotation_rows(beam.conn, ids[0])}
    convo_kinds = {row[0] for row in _annotation_rows(beam.conn, ids[1])}
    assert "has_source" in doc_kinds, (
        "non-default source should produce has_source annotation"
    )
    assert "has_source" not in convo_kinds, (
        "conversational source should NOT produce has_source annotation "
        "(matches _add_temporal_triple filter)"
    )


def test_remember_batch_extracts_gists_and_consolidated_facts(temp_db):
    """`_ingest_graph_and_veracity` should fire for every batch row,
    producing rule-based gists + facts + consolidated_facts. Content
    chosen to match the regex pattern in
    `EpisodicGraph.extract_facts` ('X is Y')."""
    beam = BeamMemory(session_id="e2-graph", db_path=temp_db)
    ids = beam.remember_batch([
        {"content": "Alice is the lead engineer", "source": "convo"},
        {"content": "Bob is a contractor",        "source": "convo"},
    ])
    # Each row should have a gist
    for memory_id in ids:
        assert _gist_count(beam.conn, memory_id) >= 1, (
            f"{memory_id}: missing gist — _ingest_graph_and_veracity "
            "didn't fire"
        )
    # The pattern extractor should have produced consolidated_facts
    # entries from the "X is Y" matches.
    assert _consolidated_fact_count(beam.conn) > 0, (
        "consolidated_facts is empty — VeracityConsolidator wasn't "
        "consulted by the batch path"
    )


# ---------------------------------------------------------------------------
# Per-row source + veracity flow through to enrichment
# ---------------------------------------------------------------------------


def test_per_row_veracity_threads_into_consolidated_facts(temp_db):
    """Per-row veracity must propagate to VeracityConsolidator so
    consolidated_facts weighting is per-row, not collapsed to the
    method-level default."""
    beam = BeamMemory(session_id="e2-ver", db_path=temp_db)
    beam.remember_batch([
        {"content": "Dana is a developer", "veracity": "stated"},
        {"content": "Eric is a tester",    "veracity": "inferred"},
    ])
    rows = beam.conn.execute(
        "SELECT subject, predicate, object, confidence "
        "FROM consolidated_facts "
        "WHERE subject IN ('Dana', 'Eric') "
        "ORDER BY subject"
    ).fetchall()
    # At least one consolidated_fact per subject; confidences should
    # differ (stated >  inferred in the veracity weight table).
    by_subject = {r[0]: r[3] for r in rows}
    if "Dana" in by_subject and "Eric" in by_subject:
        assert by_subject["Dana"] != by_subject["Eric"], (
            "stated and inferred veracity collapsed to same confidence — "
            "per-row veracity didn't reach VeracityConsolidator"
        )


def test_per_row_source_flows_to_has_source_annotation(temp_db):
    """`has_source` annotation value should reflect each row's own
    `source` field, not the first row's or a default."""
    beam = BeamMemory(session_id="e2-src", db_path=temp_db)
    ids = beam.remember_batch([
        {"content": "From a wiki page", "source": "wiki"},
        {"content": "From an email",    "source": "email"},
    ])
    wiki_rows = _annotation_rows(beam.conn, ids[0])
    email_rows = _annotation_rows(beam.conn, ids[1])
    wiki_has_source = {r[1] for r in wiki_rows if r[0] == "has_source"}
    email_has_source = {r[1] for r in email_rows if r[0] == "has_source"}
    assert "wiki" in wiki_has_source, (
        f"row 0 has_source = {wiki_has_source}, expected 'wiki'"
    )
    assert "email" in email_has_source, (
        f"row 1 has_source = {email_has_source}, expected 'email'"
    )


# ---------------------------------------------------------------------------
# Opt-in flags are respected (and default-off)
# ---------------------------------------------------------------------------


def test_extract_entities_off_by_default(temp_db):
    """Default `extract_entities=False`: no `mentions` annotation
    rows should appear in a fresh batch insert."""
    beam = BeamMemory(session_id="e2-no-ent", db_path=temp_db)
    ids = beam.remember_batch([
        {"content": "Alice and Bob worked on the auth refactor"},
    ])
    rows = _annotation_rows(beam.conn, ids[0])
    kinds = [r[0] for r in rows]
    assert "mentions" not in kinds, (
        "default-off entity extraction leaked a mentions annotation"
    )


def test_extract_entities_true_populates_mentions(temp_db):
    """`extract_entities=True`: regex entity scan should produce
    `mentions` annotation rows."""
    beam = BeamMemory(session_id="e2-ent-on", db_path=temp_db)
    ids = beam.remember_batch(
        [
            {"content": "Alice and Bob worked on the auth refactor"},
        ],
        extract_entities=True,
    )
    rows = _annotation_rows(beam.conn, ids[0])
    kinds = [r[0] for r in rows]
    assert "mentions" in kinds, (
        "extract_entities=True should produce mentions annotations"
    )


def test_extract_false_does_not_call_llm(temp_db):
    """Default `extract=False`: the LLM-backed
    `_extract_and_store_facts` must NOT be called. We verify by
    patching the module-level function and asserting it never fired."""
    with patch(
        "mnemosyne.core.beam._extract_and_store_facts"
    ) as mock_facts:
        beam = BeamMemory(session_id="e2-no-llm", db_path=temp_db)
        beam.remember_batch([{"content": "Some content"}])
        assert mock_facts.call_count == 0, (
            "extract=False but LLM fact extraction fired anyway"
        )


def test_extract_true_calls_llm_fact_extractor_per_row(temp_db):
    """`extract=True`: `_extract_and_store_facts` must be called
    once per batch row. We patch the module-level function so the
    test doesn't actually hit any LLM provider."""
    with patch(
        "mnemosyne.core.beam._extract_and_store_facts"
    ) as mock_facts:
        beam = BeamMemory(session_id="e2-llm-on", db_path=temp_db)
        beam.remember_batch(
            [
                {"content": "Row A"},
                {"content": "Row B"},
                {"content": "Row C"},
            ],
            extract=True,
        )
        assert mock_facts.call_count == 3, (
            f"expected 3 LLM calls (one per row), got {mock_facts.call_count}"
        )


# ---------------------------------------------------------------------------
# Parity with remember() for the always-on parts
# ---------------------------------------------------------------------------


def test_remember_batch_parity_with_remember_for_annotations(temp_db):
    """`remember_batch([single_item])` should produce the same
    annotation rows as `remember(single_item)` does for the
    always-on enrichment pipeline (excluding LLM-only paths)."""
    # Run remember() in one beam, remember_batch() in another, then
    # compare annotation shapes for the same content.
    content = "Frank is a database administrator"
    src = "wiki"

    beam_single = BeamMemory(session_id="e2-parity-a", db_path=temp_db)
    mid_single = beam_single.remember(content, source=src)

    parity_db = temp_db.parent / "parity.db"
    beam_batch = BeamMemory(session_id="e2-parity-b", db_path=parity_db)
    [mid_batch] = beam_batch.remember_batch(
        [{"content": content, "source": src}]
    )

    a_kinds = sorted({
        row[0] for row in _annotation_rows(beam_single.conn, mid_single)
    })
    b_kinds = sorted({
        row[0] for row in _annotation_rows(beam_batch.conn, mid_batch)
    })
    assert a_kinds == b_kinds, (
        f"annotation kinds diverge: remember()={a_kinds}, "
        f"remember_batch()={b_kinds}"
    )


def test_remember_batch_parity_with_remember_for_gists(temp_db):
    """Single-row remember_batch should produce at least the same
    number of gists as remember() does for identical content."""
    content = "Grace is the new VP of engineering"

    beam_single = BeamMemory(session_id="e2-gist-a", db_path=temp_db)
    mid_single = beam_single.remember(content)

    parity_db = temp_db.parent / "parity_gist.db"
    beam_batch = BeamMemory(session_id="e2-gist-b", db_path=parity_db)
    [mid_batch] = beam_batch.remember_batch([{"content": content}])

    single_count = _gist_count(beam_single.conn, mid_single)
    batch_count = _gist_count(beam_batch.conn, mid_batch)
    assert single_count == batch_count, (
        f"gist count divergence: remember()={single_count}, "
        f"remember_batch()={batch_count}"
    )


# ---------------------------------------------------------------------------
# Robustness — enrichment failures don't tear down the batch
# ---------------------------------------------------------------------------


def test_enrichment_exception_does_not_break_batch(temp_db):
    """If any single row's enrichment helper raises, the working_memory
    insert + embedding write must still succeed for ALL rows. The
    underlying helpers swallow exceptions internally (best-effort
    pattern), but we test the contract end-to-end so a future refactor
    that strips a try/except doesn't silently regress data integrity."""
    beam = BeamMemory(session_id="e2-fault", db_path=temp_db)
    # Inject a failure into _ingest_graph_and_veracity for one specific
    # content; verify all rows still landed in working_memory.
    original = beam._ingest_graph_and_veracity
    call_count = {"n": 0}

    def faulty(memory_id, content, source, veracity):
        call_count["n"] += 1
        if "boom" in content:
            raise RuntimeError("simulated extraction failure")
        return original(memory_id, content, source, veracity)

    beam._ingest_graph_and_veracity = faulty  # type: ignore
    try:
        ids = beam.remember_batch([
            {"content": "ok row 1"},
            {"content": "row with boom inside"},
            {"content": "ok row 3"},
        ])
    except Exception:
        # If the batch propagates the failure, that's an acceptable
        # contract (best-effort means we choose to roll forward); the
        # important property is that working_memory was written. Check
        # that explicitly even if remember_batch re-raised.
        pass

    # All three rows should be in working_memory regardless of
    # enrichment failure on row 2.
    wm_count = beam.conn.execute(
        "SELECT COUNT(*) FROM working_memory WHERE session_id = ?",
        ("e2-fault",),
    ).fetchone()[0]
    assert wm_count == 3, (
        f"enrichment failure tore down working_memory inserts: "
        f"only {wm_count}/3 rows present"
    )
    assert call_count["n"] >= 1, (
        "enrichment helper never called — patch didn't take effect"
    )
