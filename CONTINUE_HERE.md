# Mnemosyne — Session Status (May 13, 2026)

## Session Summary
Full audit of Mnemosyne health, consolidated all 56 stalled sessions, identified and fixed critical bugs.

## What Was Done
1. **Disk cleanup**: Root filesystem 94% → 69% (8.5 GB free)
   - apt: removed broken `packages.hermes-pm.io` /gopass repo
   - apt: upgraded 12 packages
   - cargo: `cargo clean` freed 3.3GB (stale build artifacts)
   - npm cache: cleaned
   - containers: purged 2 unused `rust:slim` images (1.7GB)
   - state snapshots: removed old pre-update backup (388MB)
   - sessions: gzip compressed 345/800 sessions (70% savings)

2. **Mnemosyne consolidation fix**:
   - Discovered consolidation was DEAD for 6 days (May 7-13)
   - Root cause: `source=` → `chunk_source=` typo in `_summarize_chunk()` (local_llm.py:515)
   - Bug affected ALL 56 sessions with multi-chunk summaries
   - Fixed the typo, ran consolidation: 360 → 0 working memories, 113 → 179 episodic
   - 100% LLM-processed, 0 degraded entries

3. **rust_cave_001 wired**:
   - Added `MNEMOSYNE_USE_CAVEMAN` env var support to `summarize_memories()`
   - Caveman pre-compresses memory text before LLM summarization
   - Prevents context window overflow on Qwen2.5-1.5B (7,000+ char prompts)
   - Graceful fallback to uncompressed text

4. **Systemd/Env wiring**:
   - Added `EnvironmentFile=` to `hermes-gateway.service`
   - Enabled `MNEMOSYNE_AUTO_SLEEP_ENABLED=true`
   - Caveman active in gateway process

## GitHub Filing
- **PR #114** (upstream AxDSan/mnemosyne): Second-pass `_summarize_chunk` fix — source= → chunk_source= https://github.com/AxDSan/mnemosyne/pull/114
- **Issue #115** (upstream): Consolidation health check and monitoring https://github.com/AxDSan/mnemosyne/issues/115
- **Issue #116** (upstream): Add rust_cave_001 auto-detection https://github.com/AxDSan/mnemosyne/issues/116
- **Issue #3** (rust-cave-001): Caveman integration tracking https://github.com/ether-btc/rust-cave-001/issues/3

## Known Gaps / Next Steps
1. **session_search → .json.gz compatibility**: Verify it reads compressed session files. 345 sessions are .json.gz now — may be invisible to cross-session recall.
2. **Triple extraction stalled**: 8,490 triples all from May 9. New sessions don't generate triples. Need to wire triple extraction into the sleep() consolidation flow.
3. **Three competing recall systems**: session_search (flat files) vs lcm.db (DAG) vs mnemosyne.db (vector+FTS+episodic). Architectural decision needed.
4. **Consolidation health monitoring**: No cron/systemd timer to detect broken consolidation. Issue #115 filed; a simple Python script + systemd timer could check if MAX(created_at) in episodic_memory > 12h old.
5. **Mnemosyne upstream**: PR #114 is open. Monitor for merge. Fork is at `feature/self-healing-quality-pipeline` with additional caveman wiring.
