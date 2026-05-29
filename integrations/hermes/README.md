<div align="center">

# Mnemosyne for Hermes

*Local-first memory provider for Hermes Agent. 23 tools. Zero cloud. Zero latency.*

[![PyPI](https://img.shields.io/pypi/v/mnemosyne-hermes.svg)](https://pypi.org/project/mnemosyne-hermes/)
[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/AxDSan/mnemosyne/blob/main/LICENSE)
[![Stars](https://img.shields.io/github/stars/AxDSan/mnemosyne.svg?style=social)](https://github.com/AxDSan/mnemosyne)

</div>

**Mnemosyne** is a Hermes-native memory provider that stores everything locally — SQLite with vector search, hybrid recall, episodic consolidation, and a temporal knowledge graph. No API keys. No cloud. No network calls. Your memory stays on your machine.

---

## Quick Start

```bash
pip install mnemosyne-hermes
hermes memory setup          # select "mnemosyne"

# Or manually:
hermes config set memory.provider mnemosyne
```

That's it. Hermes discovers the plugin automatically.

---

## What You Get

- **23 memory tools.** `remember`, `recall`, `sleep`, `validate`, `graph_query`, `triple_add`, `scratchpad_write`, and more. All surfaced through the Hermes tool system.
- **Hybrid search.** Vector similarity + FTS5 full-text + temporal scoring. Tunable per-query.
- **Episodic consolidation.** `mnemosyne_sleep` compresses working memory into long-term summaries — keeps context small, recall sharp.
- **Knowledge graph.** `mnemosyne_triple_add` / `mnemosyne_triple_query` for structured facts. `mnemosyne_graph_query` traverses linked memories via BFS.
- **Multi-agent validation.** `mnemosyne_validate` lets agents attest, update, or invalidate each other's memories with provenance tracking.
- **Shared surface.** `mnemosyne_shared_remember` stores compact cross-agent metadata.

---

## Configuration

No required config. Everything defaults to `~/.mnemosyne/`. Optional overrides:

| Variable | Default | Description |
|---|---|---|
| `MNEMOSYNE_HOME` | `~/.mnemosyne` | Storage directory |
| `MNEMOSYNE_VEC_WEIGHT` | `0.5` | Vector similarity weight in hybrid recall |
| `MNEMOSYNE_FTS_WEIGHT` | `0.3` | Full-text search weight |
| `MNEMOSYNE_IMPORTANCE_WEIGHT` | `0.2` | Importance score weight |
| `MNEMOSYNE_AUTO_SLEEP_ENABLED` | `false` | Auto-consolidate after N turns |
| `MNEMOSYNE_AUTO_SLEEP_THRESHOLD` | `50` | Turns between auto-consolidation |
| `MNEMOSYNE_PROFILE_ISOLATION` | `false` | Separate DB per Hermes profile |

---

## Links

- [Mnemosyne GitHub](https://github.com/AxDSan/mnemosyne) — core library, benchmarks, docs, BEAM ICLR 2026
- [Hermes Memory Providers](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory-providers) — full comparison table
- [Hermes Plugin Guide](https://hermes-agent.nousresearch.com/docs/developer-guide/memory-provider-plugin) — developer docs
