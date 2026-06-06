"""Tests for selectable prefetch profiles + the generic source-extension hook.

The default `general` profile must reproduce prior behavior exactly; other
profiles only change the documented knobs. The source registry lets a caller
merge extra retrieval inputs without the core knowing what they are.
"""
from __future__ import annotations

import pytest

from hermes_memory_provider import (
    MnemosyneMemoryProvider,
    PrefetchProfile,
    _resolve_profile,
    register_profile,
)


class FakeBeam:
    """Records the kwargs recall() was called with; returns fixed results."""
    author_id = "test-author"

    def __init__(self, results):
        self.results = results
        self.last_kwargs = None

    def recall(self, **kwargs):
        self.last_kwargs = kwargs
        return self.results


def _provider(profile_name, results):
    p = MnemosyneMemoryProvider()
    p._beam = FakeBeam(results)
    p._prefetch_profile = profile_name
    return p


# --- profile resolution ------------------------------------------------------

def test_unknown_profile_falls_back_to_general():
    assert _resolve_profile("does-not-exist").name == "general"
    assert _resolve_profile(None).name == "general"


def test_general_is_the_default_and_passes_no_tuning_weights():
    p = _provider("general", [
        {"content": "Paris is the capital of France", "timestamp": "2026-05-14T12:00:00Z",
         "importance": 0.9, "score": 0.9, "trust_tier": "STATED"},
    ])
    block = p.prefetch("capital of France")
    assert block.startswith("## Mnemosyne Context")
    assert "Paris is the capital of France" in block
    # general leaves recall()'s own weighting defaults untouched
    assert "importance_weight" not in p._beam.last_kwargs
    assert p._beam.last_kwargs["temporal_weight"] == 0.2


def test_social_chat_passes_its_tuning_to_recall():
    p = _provider("social-chat", [
        {"content": "the team ships on Friday", "timestamp": "2026-05-14T12:00:00Z",
         "importance": 0.9, "score": 0.4, "trust_tier": "STATED"},
    ])
    p.prefetch("when do we ship")
    assert p._beam.last_kwargs["importance_weight"] == 0.6
    assert p._beam.last_kwargs["temporal_weight"] == 0.35
    assert p._beam.last_kwargs["temporal_halflife"] == 24


# --- generic source hook -----------------------------------------------------

def test_registered_source_is_merged():
    p = _provider("general", [
        {"content": "Paris is the capital of France", "timestamp": "2026-05-14T12:00:00Z",
         "importance": 0.9, "score": 0.9, "trust_tier": "STATED"},
    ])
    register_profile(PrefetchProfile(name="t-merge", sources=("bank", "dummy")))
    p._prefetch_profile = "t-merge"
    p.register_prefetch_source(
        "dummy", lambda q, *, session_id="": [{"content": "Lake Baikal is the deepest lake"}])
    block = p.prefetch("geography")
    assert "Paris is the capital of France" in block
    assert "Lake Baikal is the deepest lake" in block
    assert "## Context (dummy)" in block


def test_bank_source_cannot_be_overridden():
    p = _provider("general", [])
    p.register_prefetch_source("bank", lambda q, *, session_id="": "nope")
    assert "bank" not in p._prefetch_sources


def test_dedup_collapses_duplicate_content_across_sources():
    p = _provider("general", [
        {"content": "Mount Everest is the tallest mountain", "timestamp": "2026-05-14T12:00:00Z",
         "importance": 0.9, "score": 0.9, "trust_tier": "STATED"},
    ])
    register_profile(PrefetchProfile(name="t-dedup", sources=("bank", "dummy"), dedup=True))
    p._prefetch_profile = "t-dedup"
    p.register_prefetch_source(
        "dummy", lambda q, *, session_id="": [{"content": "Mount Everest is the tallest mountain"}])
    block = p.prefetch("mountains")
    assert block.count("Mount Everest is the tallest mountain") == 1


# --- env precedence (back-compat with the existing content-chars override) ----

def test_env_content_chars_override_beats_profile(monkeypatch):
    monkeypatch.setenv("MNEMOSYNE_PREFETCH_CONTENT_CHARS", "20")
    long_content = "Mount Everest " * 10 + "tail"
    p = _provider("general", [
        {"content": long_content, "timestamp": "2026-05-14T12:00:00Z",
         "importance": 0.9, "score": 0.9, "trust_tier": "STATED"},
    ])
    block = p.prefetch("everest")
    assert "tail" not in block          # truncated by the env limit
    assert block.rstrip().endswith("...")
