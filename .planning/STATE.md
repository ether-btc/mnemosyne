# Project State

**Updated:** 2026-05-05
**Current Phase:** 2 — Smarter Compression
**Phase Status:** ✅ Complete (shipped to main)

## Progress

| Phase | Status | Started | Ship Date |
|-------|--------|---------|-----------|
| 1 | ✅ Complete | 2026-05-05 | 2026-05-05 |
| 2 | ✅ Complete | 2026-05-05 | 2026-05-05 |
| 3 | Planned | - | - |

## Implementation Summary

### Phase 1: Core Degradation Engine
- 6 waves: schema, config, degrade_episodic(), recall weighting, sleep integration, tests
- 39 tests passing (10 degradation tests)

### Phase 2: Smart Compression
- `_extract_key_signal()`: sentence-level entity scoring
- 12 regex patterns (proper nouns, acronyms, tech terms, security, infra, urgency, preferences)
- Config: `MNEMOSYNE_SMART_COMPRESS=1` (on by default), `MNEMOSYNE_TIER3_MAX_CHARS=300`
- 4 tests: entity preservation, no-sentences fallback, short content passthrough, e2e
- 43 tests total passing

### Bug Fixes
- 🐛 `local_llm.summarize()` → `local_llm.summarize_memories()`
- 🐛 SQLite connection conflicts in batch test

### Commits
- `8ca39cd` — feat: tiered episodic degradation (Phase 1, Waves 1-5)
- `839ced2` — fix: Wave 6 — summarize_memories call + 10 tests
- `9a00c12` — chore: remove hallucinated Phase 2 from roadmap
- `4799360` — feat: Phase 2 — smart compression for tier 2→3 degradation

### Blockers
None.
