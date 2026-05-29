# Mnemosyne for Hermes Agent

Local-first AI memory provider for [Hermes Agent](https://github.com/NousResearch/hermes-agent).

Powered by [Mnemosyne](https://github.com/AxDSan/mnemosyne) — SQLite with vector search, FTS5 hybrid ranking, episodic consolidation, temporal knowledge graph, and multi-agent validation. Zero cloud. Zero latency. MIT licensed.

## Quick Start

```bash
pip install mnemosyne-hermes
hermes memory setup   # select "mnemosyne"

# Or manually:
hermes config set memory.provider mnemosyne
```

## Why Mnemosyne

- **Local-first.** Your memory lives on your machine. No cloud. No API key. No network calls.
- **19 tools.** `mnemosyne_remember`, `mnemosyne_recall`, `mnemosyne_sleep`, `mnemosyne_validate`, `mnemosyne_graph_query`, and more.
- **Hybrid search.** Vector similarity + FTS5 full-text + temporal scoring. Tunable per-query.
- **Episodic consolidation.** `mnemosyne_sleep` compresses short-term working memory into long-term episodic summaries.
- **Knowledge graph.** `mnemosyne_triple_add` and `mnemosyne_triple_query` for structured fact storage.
- **Graph traversal.** `mnemosyne_graph_query` runs multi-hop BFS through linked memories.
- **Collaborative validation.** `mnemosyne_validate` lets agents attest, update, or invalidate each other's memories.
- **Cross-agent surface.** `mnemosyne_shared_remember` stores compact metadata visible across agents.

## Configuration

No required config. Defaults use `~/.mnemosyne/` for storage. Optional environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `MNEMOSYNE_HOME` | `~/.mnemosyne` | Storage directory |
| `MNEMOSYNE_DB_PATH` | auto | Custom SQLite path |
| `MNEMOSYNE_VEC_WEIGHT` | 0.5 | Vector similarity weight |
| `MNEMOSYNE_FTS_WEIGHT` | 0.3 | Full-text search weight |
| `MNEMOSYNE_IMPORTANCE_WEIGHT` | 0.2 | Importance score weight |
| `MNEMOSYNE_AUTO_SLEEP_ENABLED` | false | Auto-consolidate after N turns |
| `MNEMOSYNE_AUTO_SLEEP_THRESHOLD` | 50 | Turns between auto-consolidation |
| `MNEMOSYNE_PROFILE_ISOLATION` | false | Separate DB per Hermes profile |

## Links

- [Mnemosyne GitHub](https://github.com/AxDSan/mnemosyne) — core library, benchmarks, docs
- [Hermes Agent Memory Providers](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory-providers) — provider comparison
- [Hermes Memory Provider Plugins](https://hermes-agent.nousresearch.com/docs/developer-guide/memory-provider-plugin) — developer guide
