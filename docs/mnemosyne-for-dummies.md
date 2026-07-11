# Mnemosyne for Dummies
## A complete guide to understanding your AI memory system

---

## Part 1: What Even Is This Thing?

Mnemosyne is a **memory system for AI agents**. Think of it as a brain that sits next to your AI, remembering everything that happens so the AI doesn't have to.

**The problem it solves:** AI agents are amnesiacs. Every conversation starts from zero. They don't remember what you told them yesterday, what they built last week, or that you prefer short answers. Mnemosyne fixes that. It stores facts, conversations, preferences, and decisions in a SQLite database and retrieves them on demand.

**The name:** Mnemosyne is the Greek goddess of memory, mother of the Muses. The logo is her symbol.

**What it's NOT:** It's not a chatbot. It's not a database for your app. It's not a vector database (though it has one inside). It's specifically designed for AI agent memory — short-term, long-term, and everything in between.

---

## Part 2: The Big Picture — BEAM Architecture

BEAM stands for **B**iological **E**pisodic **A**ssociative **M**emory. It's inspired by how human memory actually works. You don't have one bucket of "memories" — you have different types:

```
┌─────────────────────────────────────────────────┐
│                  YOUR AGENT                      │
│  "Hey, remember when we deployed v3.12.0?"      │
└────────────────────┬────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────┐
│              Mnemosyne.recall()                  │
│         "What do I know about deploy?"           │
└────────────────────┬────────────────────────────┘
                     │
        ┌────────────┼────────────┐
        ▼            ▼            ▼
┌───────────┐ ┌──────────┐ ┌──────────┐
│  FTS5     │ │ sqlite-  │ │ Graph    │
│  (text)   │ │ vec      │ │ Traversal│
│           │ │ (meaning)│ │ (links)  │
└─────┬─────┘ └────┬─────┘ └────┬─────┘
      │             │            │
      └─────────────┼────────────┘
                    │
                    ▼
         ┌──────────────────┐
         │  Hybrid Ranking  │
         │  (combines all   │
         │   three signals) │
         └────────┬─────────┘
                  │
                  ▼
         ┌──────────────────┐
         │  Results: top 40 │
         │  most relevant   │
         │  memories        │
         └──────────────────┘
```

**Three search engines, one query:**
1. **FTS5** (Full-Text Search) — finds words. "deploy" matches "deployed v3.12.0"
2. **sqlite-vec** (Vector Search) — finds meaning. "ship" matches "deploy" even though the words are different
3. **Graph Traversal** — follows links. If memory A references memory B, B comes back too

---

## Part 3: The Memory Journey

Every memory goes through a lifecycle. Here's the complete path:

### Step 1: Remember (Store)

```python
from mnemosyne import Mnemosyne
m = Mnemosyne()

# Store a fact
m.remember("User prefers dark mode")
m.remember("Deployed v3.12.0 to production at 2pm")
m.remember("The CI pipeline takes 12 minutes")
```

What happens behind the scenes:
1. Text is stored in `working_memory` table (SQLite)
2. FTS5 index is updated automatically (for keyword search)
3. Vector embedding is generated (for semantic search)
4. Entities are extracted (names, dates, versions)
5. If the fact looks like a preference or identity, it goes to `canonical_facts`

### Step 2: Recall (Retrieve)

```python
# Search for anything related to "deploy"
results = m.recall("deploy", top_k=10)

for r in results:
    print(r["content"])  # "Deployed v3.12.0 to production at 2pm"
    print(r["score"])    # 0.87 — how relevant this is
```

What happens:
1. Your query "deploy" is converted to a vector embedding
2. FTS5 finds memories containing the word "deploy" or "deployed"
3. sqlite-vec finds memories with similar meaning (like "ship", "release")
4. Graph traversal follows links from matching memories
5. All results are scored and ranked by relevance
6. Top N results come back

### Step 3: Consolidate (Sleep)

```python
# Run the nightly cleanup
m.sleep()
```

What happens:
1. Old working memories are analyzed for patterns
2. Related memories are grouped into "episodes" (scenes)
3. Episodes are summarized into long-term storage
4. Working memory is trimmed (old stuff gets cleaned up)
5. The LLM (if enabled) can create richer summaries

**Think of it like this:** Your working memory is like today's notes. Sleep moves the important stuff to your journal. The journal is organized by topic and time. The scratchpad is sticky notes you'll throw away.

### Step 4: Forget (Delete)

```python
m.forget("memory_id_here")
```

Simple: removes a memory by its ID. The memory is gone from working memory, but consolidated versions in episodic memory remain.

---

## Part 4: The Four BEAM Tiers

Mnemosyne organizes memories into four tiers, each with a different purpose:

| Tier | Name | What it stores | How long | Example |
|------|------|---------------|----------|---------|
| **L0** | Raw Traces | Exact conversation logs | Configurable | "User said: 'I prefer dark mode'" |
| **L1** | Working Memory | Facts, preferences, atoms | 7 days (default) | "User prefers dark mode" |
| **L2** | Episodic Memory | Summarized scenes, task narratives | 30-180 days | "March 2026: Deployed v3.12.0. 40 commits, 9 contributors..." |
| **L3** | Persona | Who the user is, behavioral rules | Permanent | "AJ uses short sentences. No em-dashes. Direct and warm." |
| **L4** | Skills/SOPs | How to do things, reusable workflows | Permanent | "How to deploy Mnemosyne: step 1, step 2..." |

**L0-L3** answer "what do I know?" — these are declarative memories.
**L4** answers "how do I do X?" — these are procedural memories. (L4 is a separate product, not yet in Mnemosyne core.)

---

## Part 5: Key Files — What Lives Where

```
mnemosyne/
├── mnemosyne/
│   ├── __init__.py          # Public API: Mnemosyne(), remember(), recall(), forget()
│   ├── core/
│   │   ├── beam.py          # ← THE BRAIN. 8,732 lines. The main engine.
│   │   │                    #    BeamMemory class, recall(), remember(), sleep(),
│   │   │                    #    recall_enhanced(), get_context(), consolidate()
│   │   ├── memory.py        # ← The friendly wrapper. Mnemosyne class.
│   │   │                    #    Thin wrapper around beam.py. What users actually call.
│   │   ├── config.py        # ← Config system. config.yaml, DEFAULTS, auto-seed.
│   │   ├── embeddings.py    # ← Text → vectors. embed(), embed_query().
│   │   │                    #    Uses fastembed (local) or API (remote).
│   │   ├── profiles.py      # ← Named config profiles (speed, quality, etc.)
│   │   ├── sync.py          # ← Bidirectional sync between devices
│   │   ├── canonical.py     # ← Single-truth facts (name, preferences)
│   │   ├── episodic_graph.py# ← Memory graph — links between memories
│   │   ├── polyphonic_recall.py # ← Multi-voice recall (different perspectives)
│   │   └── shmr.py          # ← Belief harmonization (resolve contradictions)
│   ├── cli.py               # ← CLI commands: mnemosyne store, recall, sleep, migrate
│   └── mcp_tools.py         # ← MCP server tools (for Claude, Codex, etc.)
├── integrations/
│   └── hermes/              # ← Hermes Agent plugin (mnemosyne-hermes on PyPI)
│       └── src/mnemosyne_hermes/
│           ├── __init__.py  # ← MemoryProvider — the bridge between Hermes and Mnemosyne
│           ├── tools.py     # ← Hermes tool schemas (mnemosyne_remember, recall, etc.)
│           └── install.py   # ← Installer: copies provider into Hermes plugins dir
├── tests/                   # ← 2,000+ tests
├── CHANGELOG.md             # ← Every release documented
└── pyproject.toml           # ← Package metadata, version, dependencies
```

### The Four Most Important Files

**1. `beam.py`** — The brain. 8,732 lines of pure memory engine. This is where everything actually happens. If you need to understand how recall works, go here. If you need to trace a bug, start here. It's massive but well-organized.

**2. `memory.py`** — The friendly face. This is what users (and Hermes) actually interact with. It's a thin wrapper around beam.py that adds convenience methods and the config auto-seed. 1,053 lines.

**3. `config.py`** — The settings system. Added in v3.12.0. Manages config.yaml, auto-seeds defaults, handles hot-reload, and bridges env vars to config keys. 700+ lines.

**4. `__init__.py`** (integrations/hermes) — The Hermes bridge. This is the `MemoryProvider` class that Hermes discovers and uses. It translates Hermes events into Mnemosyne calls. 1,100+ lines.

---

## Part 6: The Config System

### Where config.yaml lives

```
~/.hermes/mnemosyne/config.yaml        # Default location
$MNEMOSYNE_DATA_DIR/config.yaml        # If MNEMOSYNE_DATA_DIR is set
```

### How it works

```
config.yaml  >  env vars  >  hardcoded defaults
 (highest)      (middle)      (lowest)
```

A value in config.yaml beats an env var. An env var beats the default. If nothing is set, the default wins.

### Auto-seed

On first use, Mnemosyne creates config.yaml with all 106 keys and their defaults. If you have env vars set, those values are used instead of defaults. This means your existing setup never breaks.

### Hot-reload

Edit config.yaml, then run:
```bash
mnemosyne config reload
```

Most keys take effect immediately. A few (data_dir, db_path, embedding_model) need a restart.

### Key settings you might actually change

```yaml
# How many items in working memory (default: 10000)
wm_max_items: 5000

# How long working memories live (default: 168 hours = 7 days)
wm_ttl_hours: 336

# Enable enhanced recall features (default: false)
enhanced_recall: true

# Search across all sessions, not just current (default: false)
cross_session: true

# Use remote LLM for consolidation (default: false)
llm_enabled: true
llm_base_url: "https://api.openai.com/v1"
llm_api_key: "sk-..."
llm_model: "gpt-4o-mini"
```

---

## Part 7: The Hermes Plugin

### How Mnemosyne plugs into Hermes

```
┌──────────┐     ┌──────────────────┐     ┌──────────────┐
│  Hermes  │────▶│ MemoryProvider   │────▶│  Mnemosyne   │
│  Agent   │     │ (__init__.py)    │     │  (memory.py) │
└──────────┘     └──────────────────┘     └──────────────┘
                                           │
                                           ▼
                                    ┌──────────────┐
                                    │  BeamMemory  │
                                    │  (beam.py)   │
                                    └──────────────┘
                                           │
                                           ▼
                                    ┌──────────────┐
                                    │   SQLite     │
                                    │  (mnemosyne  │
                                    │   .db)       │
                                    └──────────────┘
```

1. Hermes discovers the plugin at `~/.hermes/plugins/mnemosyne/__init__.py`
2. The plugin's `register()` function calls `register_memory_provider(ctx)`
3. Hermes creates a `MemoryProvider` instance
4. On every turn, the provider calls `Mnemosyne.remember()` for new messages
5. On context injection, the provider calls `Mnemosyne.recall()` to get relevant memories
6. The provider exposes tools: `mnemosyne_remember`, `mnemosyne_recall`, `mnemosyne_forget`, etc.

### The 2-step install

```bash
# Step 1: Install the package
pipx install mnemosyne-hermes

# Step 2: Register with Hermes
mnemosyne-hermes install

# Step 3: Restart
hermes gateway restart

# Step 4: Verify
hermes memory status
```

If you skip step 2, the package is installed but Hermes can't find it. The provider files must be copied into `~/.hermes/plugins/mnemosyne/`.

### Configuring the provider

In `~/.hermes/config.yaml`:
```yaml
memory:
  memory_enabled: true       # ← Master gate. Must be true.
  provider: mnemosyne        # ← Which provider to use
```

Both must be set. `memory_enabled: false` disables ALL memory, even if you have a provider configured.

---

## Part 8: Common Operations

### Store a memory
```bash
mnemosyne store "User prefers dark mode"
```
```python
from mnemosyne import remember
remember("User prefers dark mode")
```

### Search memories
```bash
mnemosyne recall "deploy" --top-k 10
```
```python
from mnemosyne import recall
results = recall("deploy", top_k=10)
```

### Delete a memory
```bash
mnemosyne forget <memory_id>
```

### Run consolidation (sleep)
```bash
mnemosyne sleep
# Or for all sessions:
mnemosyne sleep --all-sessions
```

### Check stats
```bash
mnemosyne stats
```

### Manage config
```bash
mnemosyne config get wm_max_items    # Read a value
mnemosyne config set wm_max_items 5000  # Set a value
mnemosyne config reload              # Hot-reload changes
mnemosyne config migrate             # Export env vars to config.yaml
```

### Bank management (multi-tenant)
```bash
mnemosyne bank list                  # Show all banks
mnemosyne store --bank project-x "Deployed v3.12.0"
mnemosyne recall --bank project-x "deploy"
mnemosyne migrate --bank project-x   # Migrate old banks
```

### Sync between devices
```bash
mnemosyne sync serve                 # Start sync server
mnemosyne sync push                  # Push local changes
mnemosyne sync pull                  # Pull remote changes
mnemosyne sync status                # Check sync state
```

---

## Part 9: The Database

Mnemosyne uses a single SQLite database file. Here's what's inside:

| Table | Purpose | Example row |
|-------|---------|-------------|
| `working_memory` | Active, recent memories | "User prefers dark mode" |
| `episodic_memory` | Consolidated, summarized scenes | "March 2026: Deployed v3.12.0..." |
| `memory_embeddings` | Vector embeddings for semantic search | [0.023, -0.451, ...] (384 floats) |
| `memory_fts5` | Full-text search index | Auto-generated by SQLite triggers |
| `canonical_facts` | Single-truth facts about the user | "name: Abdias", "prefers: short answers" |
| `memoria_persona` | L3 persona rules | "AJ uses short sentences" |
| `memory_events` | Sync event log | "CREATE event for memory_id X" |
| `sync_meta` | Sync state (device ID, cursor) | "device_id: abc-123" |
| `graph_edges` | Links between memories | "memory A references memory B" |

The database file lives at `~/.hermes/mnemosyne/data/mnemosyne.db` by default.

---

## Part 10: FAQ & Troubleshooting

### "Mnemosyne is installed but not working"
Check `hermes memory status`. If it says "Provider: (none)", your config is wrong:
```yaml
memory:
  memory_enabled: true    # ← Must be true
  provider: mnemosyne     # ← Must be set
```

### "Provider keeps disappearing after upgrade"
Hermes' `update` command reinstalls everything, wiping Mnemosyne from the venv. Use pipx:
```bash
pipx install mnemosyne-hermes
mnemosyne-hermes install --force
```

### "The config.yaml wasn't created"
It auto-creates on first use of `Mnemosyne()` or `BeamMemory()`. If you're on an older version, run:
```bash
python3 -c "from mnemosyne import Mnemosyne; Mnemosyne()"
```

### "My env vars are being ignored"
Config.yaml takes precedence over env vars. If config.yaml has `wm_max_items: 10000` and you set `MNEMOSYNE_WM_MAX_ITEMS=5000`, the config.yaml value wins. Either edit config.yaml or delete the key from it.

### "Recall is slow"
Check if embeddings are working:
```bash
python3 -c "from mnemosyne.core.embeddings import embed; print(embed(['test']))"
```
If it returns None, embeddings are disabled. Install the embeddings extra:
```bash
pipx install 'mnemosyne-memory[embeddings]'
```

### "Where's the data?"
- Database: `~/.hermes/mnemosyne/data/mnemosyne.db`
- Config: `~/.hermes/mnemosyne/config.yaml`
- Logs: `~/.hermes/mnemosyne/logs/`

### "What's the difference between mnemosyne-memory and mnemosyne-hermes?"
- `mnemosyne-memory` (v3.x) — the core engine. Standalone, no Hermes needed.
- `mnemosyne-hermes` (v0.x) — the Hermes plugin. Thin wrapper that bridges Hermes ↔ Mnemosyne.

---

## Part 11: The Development Flow

When you're working on Mnemosyne:

### Running tests
```bash
cd /root/mnemosyne
python3 -m pytest tests/ -x -q
```

### Running a specific test file
```bash
python3 -m pytest tests/test_config_profiles.py -v
```

### Checking what changed
```bash
git log --oneline -10
git diff
```

### Making a release
1. Bump version in `mnemosyne/__init__.py`
2. Update CHANGELOG.md
3. Check if the plugin needs bumping: `git log v0.4.0..HEAD --oneline -- integrations/hermes/`
4. Commit, tag, push
5. Release workflow auto-publishes to PyPI

### The two config files trap
There are TWO config.yaml files. Know which one you're touching:
- `~/.hermes/mnemosyne/config.yaml` — Mnemosyne's own config (what `mnemosyne config` manages)
- `~/.hermes/config.yaml` — Hermes' config (what `hermes config` manages)

The Hermes provider reads from Hermes' config.yaml. The Mnemosyne CLI reads from Mnemosyne's config.yaml. They're different files.

---

## That's It

You now understand:
- What Mnemosyne is (AI agent memory)
- How it works (BEAM: four tiers, three search engines)
- Where the code lives (beam.py is the brain, memory.py is the face)
- How to use it (remember, recall, forget, sleep, config)
- How to debug it (check config, check provider, check embeddings)

The rest is details. When in doubt, read `beam.py` — everything flows through it.