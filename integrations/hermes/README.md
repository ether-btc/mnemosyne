<div align="center">

<img src="https://raw.githubusercontent.com/AxDSan/mnemosyne/main/assets/mnemosyne.jpg" alt="Mnemosyne" width="40%">

# Mnemosyne for Hermes Agent

*Local-first memory provider for Hermes Agent. 23 tools. Zero cloud. Zero latency.*

[![PyPI](https://img.shields.io/pypi/v/mnemosyne-hermes.svg)](https://pypi.org/project/mnemosyne-hermes/)
[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/AxDSan/mnemosyne/blob/main/LICENSE)
[![Stars](https://img.shields.io/github/stars/AxDSan/mnemosyne.svg?style=social)](https://github.com/AxDSan/mnemosyne)

</div>

**Mnemosyne** gives Hermes Agent a local-first memory layer that captures conversation, tool calls, execution paths, decisions, outcomes, and corrections. Then surfaces it all with intent-aware hybrid recall. SQLite on your machine. No cloud. No API keys. No latency.

---

## The Problem

Agent workflows lose context across sessions. A few ways this bites:

- Prior decisions and constraints vanish between sessions
- Tool-call context isn't preserved in raw transcripts
- Failures get repeated because nobody remembered the fix
- Project context gets buried in long chat history
- Cross-session memory becomes noise without structure
- Conversation-only memory misses the execution path: what the agent *did*, not just what was *said*

## What Mnemosyne Changes

Mnemosyne adds structured, local-first, agent-native memory to Hermes through the `mnemosyne` memory provider.

It gives Hermes:

- **Automatic capture**: every turn, in the background, after the response is sent. Conversation, decisions, tool calls, outcomes.
- **Hybrid search**: vector similarity + FTS5 full-text + importance scoring. All tunable per-query. Bias toward recency, relevance, or both.
- **Episodic consolidation**: `mnemosyne_sleep` compresses old working memories into long-term summaries so the working set stays small and recall stays sharp.
- **Knowledge graph**: subject-predicate-object triples with BFS graph traversal. Link memories semantically.
- **Multi-agent validation**: agents can attest, update, or invalidate each other's memories with provenance tracking.
- **Shared surface**: compact cross-agent metadata for multi-agent workflows.
- **Zero cloud**: SQLite on your machine. No network calls. No API keys. No quota limits.

Hermes' built-in `MEMORY.md` and `USER.md` files remain active. Mnemosyne is additive: it does not mirror, edit, replace, or remove those files.

## How It Works

Mnemosyne runs on three stages:

### 1. Capture

After Hermes completes a turn, the Mnemosyne provider stores the full interaction (user message, assistant response, tool calls, and available execution context) in a local SQLite database with vector embeddings.

Each memory gets tagged with importance (0.0-1.0), scope (session or global), veracity (stated, inferred, tool, or imported), and optional metadata. Memories can carry expiration dates and named entities for fuzzy recall.

This is how Hermes builds memory from what it says *and* what it does.

### 2. Recall

Recall is intentional. Agents decide when to recall, what scope, and how many results. There is no automatic retrieval dumping context into every prompt.

When `mnemosyne_recall` fires, Mnemosyne runs hybrid search: vector similarity finds semantic matches, FTS5 full-text finds keyword matches, and importance scoring boosts what matters. All three weights are tunable per-query so you can bias toward recency, relevance, or both.

Returned context can include prior decisions, constraints, failure modes, project patterns, and execution outcomes: without stuffing irrelevant history into the prompt.

### 3. Consolidate

`mnemosyne_sleep` compresses old working memories into episodic summaries. Think of it as a nightly cleanup that knows what to keep and what to summarize. The working set stays small. Recall stays sharp. Long-running agents don't drown in their own history.

---

## Quickstart

**Prerequisites:** Hermes Agent, Python 3.10+, no API keys needed.

```bash
pip install mnemosyne-hermes
hermes memory setup          # select "mnemosyne"

# Or manually:
hermes config set memory.provider mnemosyne
```

Done. Hermes discovers the plugin and all 23 tools surface automatically.

Verify:

```bash
hermes memory status
```

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

Or in `~/.hermes/config.yaml`:

```yaml
memory:
  provider: mnemosyne
  mnemosyne:
    auto_sleep: true
    sleep_threshold: 30
```

## Tools

23 tools. All surfaced through Hermes' tool system.

**Core memory:** `remember`, `recall`, `sleep`, `stats`, `get`, `update`, `forget`, `invalidate`, `validate`

**Knowledge graph:** `triple_add`, `triple_query`, `graph_query`, `graph_link`

**Multi-agent:** `shared_remember`, `shared_recall`, `shared_forget`, `shared_stats`

**Working notes:** `scratchpad_write`, `scratchpad_read`, `scratchpad_clear`

**Ops:** `export`, `import`, `diagnose`

## Test the Memory Loop

Ask Hermes to do a multi-step task:

> "Investigate why the payment sync test is failing and fix it."

Hermes inspects files, runs commands, identifies a failing fixture, makes a decision, applies a fix, and observes the result.

After the turn, Mnemosyne stores the full execution path: the failure, the decision, the fix, the outcome, and the pattern.

In a new session:

> "A similar payment sync test is failing again. Check prior fixes before changing anything."

Hermes calls `mnemosyne_recall`, finds the relevant prior failure and fix, and doesn't repeat the mistake.

## Fail-Soft By Design

If Mnemosyne's database is unavailable or disk is full, the provider logs the error and Hermes continues answering. Memory is additive: it never blocks the user.

Memory issues are logged but never surface as user-facing errors.

## Contributing

We welcome contributions. See the [Contributing Guidelines](https://github.com/AxDSan/mnemosyne/blob/main/CONTRIBUTING.md) for code style, standards, and submitting pull requests.

To build from source:

```bash
git clone https://github.com/AxDSan/mnemosyne.git
cd mnemosyne

pip install -e .
pip install -e integrations/hermes
```

## Support

- [Documentation](https://github.com/AxDSan/mnemosyne#readme)
- [Discord](https://discord.gg/3bDyGmE2)
- [Issues](https://github.com/AxDSan/mnemosyne/issues)

## License

MIT
