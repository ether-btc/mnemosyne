# CEO Brief: Mnemosyne Open Issue Analysis

**Date:** 2026-07-14
**Scope:** 20 open issues (#459, #456, #453, #451, #450, #449, #446, #435, #434, #408, #403, #389, #387, #382, #372, #370, #329, #327, #326, #308)
**Repo:** mnemosyne-oss/mnemosyne

---

## Summary Metrics

| Metric | Value |
|--------|-------|
| Total issues analyzed | 20 |
| Bugs | 11 |
| Features / proposals | 9 |
| Bugs with RCA confirmed by maintainer (AxDSan) | 8 |
| Bugs with fix shipped | 1 (#456 via #457) |
| **Analyzed-implementable bugs** | **7** |
| Analyzed-upstream bugs | 1 (#329) |
| **Analyzed-implementable / Total bugs** | **7/11 = 63.6%** |
| **Analyzed-but-unfixed / Total bugs** | **6/11 = 54.5%** |
| Bugs with no maintainer response | 3 (#459, #453, #451) |

---

## Detailed Issue Table

| # | Title | Type | RCA Status | Fix Status | Category | Notes |
|---|-------|------|-----------|-----------|----------|-------|
| 459 | Packaging: make the `all` extra include sync dependencies | **bug** | ❌ Not identified (no maintainer reply) | ❌ Not shipped | implementable | Packaging defect — `all` extra omits sync deps despite docs promising it. Trivial fix. 0 comments. |
| 456 | write_approval support for mnemosyne_remember | **bug** | ✅ Identified (AxDSan: "every claim checks out") | ✅ **Shipped** (#457 merged) | **fixed** | write_approval setting was silently ignored when Mnemosyne provider active. PR #457 implements staging + approval flow. |
| 453 | onnxruntime pthread_setaffinity_np EINVAL spam in LXC | **bug** | ❌ Not identified (no maintainer reply) | ❌ Not shipped | implementable | Log spam in unprivileged LXC containers. Fix: pass `threads=N` to TextEmbedding. 0 comments. |
| 451 | FK regression: PRAGMA foreign_keys=ON breaks pre-existing DBs | **bug** (labeled) | ❌ Not identified (0 AxDSan replies; dplush confirmed) | ❌ Not shipped (#452 open) | implementable | **Critical:** #408 enabled FK enforcement but legacy `memory_embeddings` DDL references `memories(id)` while BEAM writes `working_memory` ids → every embedding insert silently fails. PR #452 by ruangraung open, not merged. |
| 435 | No way to forget/invalidate/delete canonical memories | **bug** | ✅ Identified (AxDSan: "the fix is a forget_canonical() function... I'll ship this") | ❌ Not shipped | implementable | Canonical memories have no delete path. AxDSan acknowledged, deferred to "next patch cycle." 6 comments. |
| 434 | Overuse of canonical memories (skill instructions stored as canonical) | **bug** | ✅ Identified (AxDSan: "the canonical memory extractor is too aggressive") | ❌ Not shipped | implementable | Sleep model-refresh auto-applies skill implementation details as canonical slots. Duplicates SKILL.md content → conflicting guidance. AxDSan proposed two-pronged fix but not shipped. |
| 408 | Referential integrity: missing PRAGMA foreign_keys=ON + FK on gists | **bug** | ✅ Identified (AxDSan: "this is a real issue") | ⚠️ **Partially shipped** (Part 1: PRAGMA FK enabled; Part 2: gists FK constraint not shipped) | implementable | Part 1 (9b2b747) fixed FK enforcement. Part 2 (gists FK constraint) still pending. 54 orphan gists, 58 orphan embeddings found in real deployment. |
| 389 | Polyphonic recall collapses to single result when one voice active | **bug** | ✅ Identified (AxDSan: "you're right... this is a real bug") | ❌ Not shipped | implementable | `_estimate_similarity` computes Jaccard over voice-name sets, not content. Single-voice mode → every candidate scores 1.0 → all but one dropped. |
| 387 | Stored content mutated with [DATES:]/[DURATIONS:] annotations | **bug** | ✅ Identified (AxDSan: "this is a real pain point") | ❌ Not shipped | implementable | Entity annotations appended to `content` field itself. No opt-out. Round-trips through get/recall/export. |
| 382 | WAL checkpoint blocked after session ends — thread-local SQLite leak | **bug** | ✅ Identified (AxDSan: "this is a real resource leak") | ❌ Not shipped (v3.11.2 slipped) | implementable | Thread-local connections never explicitly closed. WAL mode → checkpoint blocked → "database is locked" for all subsequent operations. Fix targeted for v3.11.2 but slipped. |
| 329 | Mnemosyne tools not callable without resuming session | **bug** | ✅ Identified (AxDSan: "Hermes-side race condition") | ❌ Not shipped (Hermes #47119 still open) | **upstream** | Intermittent failure: `mnemosyne_*` tools absent at session start. AxDSan confirmed it's a Hermes tool-injection race, not a Mnemosyne issue. Tracking upstream. |
| 450 | Session-driven memory activation model | **feature** | N/A | N/A | implementable | Replace wall-clock decay with session-epoch-based activation. Elaborate ACT-R-inspired proposal. 0 comments. |
| 449 | Dirty memory state and validation-aware recall | **feature** | N/A | N/A | implementable | Memories become "dirty" when relevant context changes but no explicit contradiction exists. Pre-recall validation step. |
| 446 | Versioned config migration framework | **feature** | N/A | N/A | implementable | Provenance-aware migration path for auto-seeded config.yaml changes. Explicit non-goals to avoid silent rewrites. |
| 403 | Survive Hermes Docker updates | **feature** | N/A | N/A | implementable | Docker update workflow clobbers Mnemosyne install. AxDSan acknowledged as real pain point. Multiple community solutions shared. |
| 372 | General-purpose health check endpoint | **feature** | N/A | N/A | implementable | No built-in health endpoint. Community built custom v7 healthcheck in production. AxDSan acknowledged. |
| 370 | Bootstrap command to import pre-Mnemosyne session history | **feature** | N/A | N/A | implementable | Cold-start problem: Mnemosyne empty after install, users perceive it as broken. 750+ session files in one deployment. |
| 327 | Hermes identity mapping layer | **feature** | N/A | N/A | implementable | Family memory mixing: "Remember my name is ___" overwrites between users. AxDSan: "high strategic value, now real urgency." Active design discussion. |
| 326 | Background prefetch cache for Mnemosyne provider | **feature** | N/A | N/A | implementable | Expensive recall on pre-LLM path adds latency. AxDSan: "strategically the right direction." Waiting on Hermes-side contract RFC. |
| 308 | Phase 2 async/monitored reindex | **feature** | N/A | N/A | **deferred** | Phase 1 (sync reindex) shipped in #311. Phase 2 (async, progress, cancellation) deferred until demand justifies it. |

---

## Key Findings

### Analyzed-but-unfixed gap
**7 bugs** have been root-cause-analyzed by AxDSan but remain unfixed (6 of which are implementable in Mnemosyne, 1 is upstream). This represents **63.6%** of all open bugs — a significant gap between analysis and delivery.

### Most impactful unresolved bugs
1. **#451 (FK regression)** — Critical: embedding storage silently fails on any database created by legacy `memory.py` DDL. PR #452 exists but is unmerged. 841 FK violations confirmed in production.
2. **#382 (WAL checkpoint blocked)** — WAL mode leaves database locked after any non-primary session. Fix committed to v3.11.2 but slipped.
3. **#434/#435 (Canonical memory issues)** — Canonical memories are over-created and cannot be deleted. Directly impacts agent behavior quality.
4. **#408 Part 2 (gists FK)** — 54 orphan gists + 58 orphan embeddings in a 1-week deployment. Part 1 shipped, Part 2 stalled.

### Upstream dependency
- **#329** (tools not callable) is blocked on Hermes Agent #47119 — no movement since mid-June.

### No maintainer attention
- **#459** (packaging all extra), **#453** (LXC log spam), **#451** (FK regression) have received zero AxDSan replies. #451 is the most concerning as it's a labeled bug with a submitted fix PR.

### Positive signals
- **#456** (write_approval) was identified, analyzed, implemented, and merged as PR #457 — a clean end-to-end cycle.
- **#327** (identity mapping) has active design discussion with AxDSan and a committed implementation plan.
- **#308** (async reindex) Phase 1 shipped successfully; Phase 2 deferred by design.