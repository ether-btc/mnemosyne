#!/usr/bin/env python3
"""
Auto-generate docs/api/ files from live code.

Usage:
    python3 scripts/generate-docs.py

Writes canonical copies to docs/api/ inside the mnemosyne repo.
Also writes to the website sibling repo (../mnemosyne-docs/src/) if present.
All website writes are optional — canonical copies are always written.
"""
from __future__ import annotations

import json
import os
import sys

# ---------------------------------------------------------------
# Tool schema definitions (23 real tools — verified against
# hermes_memory_provider/__init__.py::ALL_TOOL_SCHEMAS and
# mnemosyne/mcp_tools.py::_TOOL_HANDLERS, v3.4.0)
# ---------------------------------------------------------------
ALL_TOOL_SCHEMAS = [
    {"name": "mnemosyne_remember", "description": "Store a durable memory", "params": {"content": "string", "importance": "float=0.5", "source": "string=user", "scope": "string=session", "valid_until": "string=", "extract_entities": "bool=false", "extract": "bool=false", "metadata": "dict={}", "veracity": "string=unknown"}},
    {"name": "mnemosyne_recall", "description": "Search memories by vector+FTS hybrid ranking", "params": {"query": "string", "limit": "int=5", "temporal_weight": "float=0.0", "query_time": "string=", "temporal_halflife": "float=24", "vec_weight": "float=null", "fts_weight": "float=null", "importance_weight": "float=null"}},
    {"name": "mnemosyne_forget", "description": "Permanently delete a memory by ID", "params": {"memory_id": "string"}},
    {"name": "mnemosyne_get", "description": "Retrieve a single memory by ID (no search)", "params": {"memory_id": "string"}},
    {"name": "mnemosyne_update", "description": "Update content or importance of an existing memory", "params": {"memory_id": "string", "content": "string=", "importance": "float="}},
    {"name": "mnemosyne_validate", "description": "Attest, update, or invalidate a memory (collaborative ownership)", "params": {"memory_id": "string", "action": "enum[attest,update,invalidate,delete]", "validator": "string=", "new_content": "string=", "note": "string=", "bank": "enum[private,surface]=private"}},
    {"name": "mnemosyne_invalidate", "description": "Mark a memory as expired/superseded", "params": {"memory_id": "string", "replacement_id": "string="}},
    {"name": "mnemosyne_import", "description": "Import memories from JSON file or provider (Hindsight, Mem0)", "params": {"input_path": "string=", "provider": "string=", "api_key": "string=", "user_id": "string=", "agent_id": "string=", "base_url": "string=", "dry_run": "bool=false", "channel_id": "string=", "force": "bool=false"}},
    {"name": "mnemosyne_export", "description": "Export all memories to a JSON file", "params": {"output_path": "string"}},
    {"name": "mnemosyne_diagnose", "description": "PII-safe diagnostics: deps, DB state, vector readiness", "params": {}},
    {"name": "mnemosyne_stats", "description": "Memory statistics: working count, episodic count, BEAM tiers", "params": {}},
    {"name": "mnemosyne_sleep", "description": "Run consolidation cycle (compress old working memories)", "params": {"all_sessions": "bool=false", "dry_run": "bool=false"}},
    {"name": "mnemosyne_triple_add", "description": "Add a fact triple to the knowledge graph", "params": {"subject": "string", "predicate": "string", "object": "string", "valid_from": "string="}},
    {"name": "mnemosyne_triple_query", "description": "Query the temporal knowledge graph", "params": {"subject": "string=", "predicate": "string=", "object": "string="}},
    {"name": "mnemosyne_graph_link", "description": "Declare a semantic edge between two memories", "params": {"source_id": "string", "target_id": "string", "relationship": "string", "weight": "float=0.5"}},
    {"name": "mnemosyne_graph_query", "description": "Multi-hop BFS traversal from a seed memory", "params": {"seed_memory_id": "string", "max_hops": "int=2", "edge_type": "string=", "min_weight": "float=0.0"}},
    {"name": "mnemosyne_shared_remember", "description": "Store compact cross-agent surface memory", "params": {"content": "string", "kind": "string=meta", "importance": "float=0.8", "veracity": "string=unknown", "metadata": "dict"}},
    {"name": "mnemosyne_shared_recall", "description": "Search only the shared surface DB", "params": {"query": "string", "limit": "int=5"}},
    {"name": "mnemosyne_shared_forget", "description": "Delete one working shared-surface memory by ID", "params": {"memory_id": "string"}},
    {"name": "mnemosyne_shared_stats", "description": "Return shared surface DB path and counts", "params": {}},
    {"name": "mnemosyne_scratchpad_write", "description": "Write a temporary note to the scratchpad", "params": {"content": "string"}},
    {"name": "mnemosyne_scratchpad_read", "description": "Read the scratchpad entries", "params": {}},
    {"name": "mnemosyne_scratchpad_clear", "description": "Clear all scratchpad entries", "params": {}},
]

# NOTE: 23 MCP tools with real handler implementations in mcp_tools.py.
# mnemosyne_end was removed — it had no handler, no schema in the provider,
# and would raise ValueError("Unknown tool") if called.

# ---------------------------------------------------------------
# Config schema (env vars — derived from actual os.environ.get /
# _env_truthy / _env_disabled / _env_float calls in beam.py,
# embeddings.py, mcp_tools.py, and hermes_memory_provider/__init__.py)
# ---------------------------------------------------------------
CONFIG_ENTRIES = [
    {"key": "MNEMOSYNE_DATA_DIR", "env": "MNEMOSYNE_DATA_DIR", "default": "~/.hermes/mnemosyne/data", "desc": "Directory for database, logs, models, and stats"},
    {"key": "MNEMOSYNE_EMBEDDING_MODEL", "env": "MNEMOSYNE_EMBEDDING_MODEL", "default": "BAAI/bge-small-en-v1.5", "desc": "fastembed model for vector embeddings"},
    {"key": "MNEMOSYNE_EMBEDDING_DIM", "env": "MNEMOSYNE_EMBEDDING_DIM", "default": "384", "desc": "Override embedding vector dimension"},
    {"key": "MNEMOSYNE_EMBEDDING_API_KEY", "env": "MNEMOSYNE_EMBEDDING_API_KEY", "default": "", "desc": "API key for cloud embedding provider"},
    {"key": "MNEMOSYNE_EMBEDDING_API_URL", "env": "MNEMOSYNE_EMBEDDING_API_URL", "default": "", "desc": "API endpoint for cloud embeddings"},
    {"key": "MNEMOSYNE_NO_EMBEDDINGS", "env": "MNEMOSYNE_NO_EMBEDDINGS", "default": "false", "desc": "Disable dense vector retrieval entirely"},
    {"key": "MNEMOSYNE_EMBEDDINGS_VIA_API", "env": "MNEMOSYNE_EMBEDDINGS_VIA_API", "default": "false", "desc": "Force cloud API mode for embeddings"},
    {"key": "MNEMOSYNE_WM_MAX_ITEMS", "env": "MNEMOSYNE_WM_MAX_ITEMS", "default": "10000", "desc": "Maximum items in working memory before eviction"},
    {"key": "MNEMOSYNE_WM_TTL_HOURS", "env": "MNEMOSYNE_WM_TTL_HOURS", "default": "24", "desc": "Hours before working memory entries expire"},
    {"key": "MNEMOSYNE_EP_LIMIT", "env": "MNEMOSYNE_EP_LIMIT", "default": "10", "desc": "Max episodic memories returned per recall"},
    {"key": "MNEMOSYNE_SLEEP_BATCH", "env": "MNEMOSYNE_SLEEP_BATCH", "default": "50", "desc": "Batch size for sleep consolidation"},
    {"key": "MNEMOSYNE_VEC_TYPE", "env": "MNEMOSYNE_VEC_TYPE", "default": "float32", "desc": "Vector storage format (float32, float16, binary)"},
    {"key": "MNEMOSYNE_VEC_WEIGHT", "env": "MNEMOSYNE_VEC_WEIGHT", "default": "0.5", "desc": "Vector similarity weight in hybrid ranking"},
    {"key": "MNEMOSYNE_FTS_WEIGHT", "env": "MNEMOSYNE_FTS_WEIGHT", "default": "0.3", "desc": "Full-text search weight in hybrid ranking"},
    {"key": "MNEMOSYNE_IMPORTANCE_WEIGHT", "env": "MNEMOSYNE_IMPORTANCE_WEIGHT", "default": "0.2", "desc": "Importance score weight in hybrid ranking"},
    {"key": "MNEMOSYNE_MCP_TOKEN", "env": "MNEMOSYNE_MCP_TOKEN", "default": "", "desc": "Bearer token for MCP server auth (required for remote deployment)"},
    {"key": "MNEMOSYNE_AUTO_SLEEP_ENABLED", "env": "MNEMOSYNE_AUTO_SLEEP_ENABLED", "default": "true", "desc": "Enable automatic sleep consolidation (Hermes provider)"},
    {"key": "MNEMOSYNE_SYNC_ROLES", "env": "MNEMOSYNE_SYNC_ROLES", "default": "user,assistant", "desc": "Conversation roles to sync into memory"},
    {"key": "MNEMOSYNE_SKIP_CONTEXTS", "env": "MNEMOSYNE_SKIP_CONTEXTS", "default": "", "desc": "Comma-separated context names to skip"},
]

# ---------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------
def _version() -> str:
    import re
    init_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mnemosyne", "__init__.py")
    if os.path.exists(init_path):
        with open(init_path) as f:
            m = re.search(r"__version__\s*=\s*['\"]([^'\"]+)['\"]", f.read())
            if m:
                return m.group(1)
    return "3.4.0"  # fallback

def _write_tool_schema_mdx(tools, version):
    lines = [
        "---",
        f'title: "MCP Tool Schema"',
        f"version: {version}",
        "tool_count: {}".format(len(tools)),
        'generated_at: "auto"',
        "---",
        "",
        f"# MCP Tool Schema (v{version})",
        "",
        f"Mnemosyne exposes **{len(tools)} MCP tools** for memory management, retrieval, and diagnostics.",
        "",
        "---",
        "",
    ]
    for i, t in enumerate(tools, 1):
        params = t.get("params", {})
        lines.append(f"### {i}. `{t['name']}`")
        lines.append(t['description'])
        lines.append("")
        if params:
            lines.append("| Parameter | Type | Required |")
            lines.append("|-----------|------|----------|")
            for pname, pdef in params.items():
                ptype, required = pdef, "yes"
                if "=" in pdef:
                    ptype, default = pdef.split("=", 1)
                    required = "no (default: {})".format(default)
                lines.append("| `{}` | `{}` | {} |".format(pname, ptype, required))
            lines.append("")
        else:
            lines.append("*No parameters*")
            lines.append("")
    return "\n".join(lines)

def _write_config_mdx(entries, version):
    lines = [
        "---",
        f'title: "Configuration"',
        f"version: {version}",
        'generated_at: "auto"',
        "---",
        "",
        "# Configuration",
        "",
        "Mnemosyne is configured entirely through environment variables. No config files, no YAML, no JSON.",
        "",
        "---",
        "",
        "| Variable | Default | Description |",
        "|----------|---------|-------------|",
    ]
    for e in entries:
        default = e.get("default", "")
        if default:
            default = "`{}`".format(default)
        else:
            default = "*(required)*"
        lines.append("| `{}` | {} | {} |".format(e["key"], default, e["desc"]))
    return "\n".join(lines)

def _inject_config_table(page_path, table_html):
    """Inject a generated config table into an existing page.mdx (for website only)."""
    if not os.path.exists(page_path):
        print("  ⚠️  config page not found at {} — skipping injection".format(page_path))
        return
    with open(page_path, 'r') as f:
        content = f.read()
    start_marker = "{/* GENERATED_CONFIG_TABLE */}"
    end_marker = "{/* /GENERATED_CONFIG_TABLE */}"
    new_block = start_marker + "\n" + table_html + "\n" + end_marker

    # Strip ALL existing GENERATED_CONFIG_TABLE blocks (handle duplicates, handle HTML and MDX comment markers)
    for start_v, end_v in [
        ("<!-- GENERATED_CONFIG_TABLE -->", "<!-- /GENERATED_CONFIG_TABLE -->"),
        ("{/* GENERATED_CONFIG_TABLE */}", "{/* /GENERATED_CONFIG_TABLE */}"),
    ]:
        while start_v in content and end_v in content:
            start_idx = content.index(start_v)
            end_idx = content.index(end_v, start_idx) + len(end_v)
            content = content[:start_idx] + content[end_idx:].lstrip('\n')

    # Insert a single clean block
    content = content.rstrip() + "\n\n" + new_block + "\n"
    with open(page_path, 'w') as f:
        f.write(content)

# ---------------------------------------------------------------
# Main
# ---------------------------------------------------------------
def main():
    version = _version()
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(script_dir)

    # Canonical copies: always write to docs/api/ inside the mnemosyne repo
    canonical = os.path.join(repo_root, "docs", "api")
    os.makedirs(canonical, exist_ok=True)

    # Tool schema
    schema_mdx = _write_tool_schema_mdx(ALL_TOOL_SCHEMAS, version)
    with open(os.path.join(canonical, "tool-schema.mdx"), "w") as f:
        f.write(schema_mdx)
    print("✓ tool-schema.mdx ({} tools) → docs/api/".format(len(ALL_TOOL_SCHEMAS)))

    # Config
    config_mdx = _write_config_mdx(CONFIG_ENTRIES, version)
    with open(os.path.join(canonical, "configuration.mdx"), "w") as f:
        f.write(config_mdx)
    print("✓ configuration.mdx ({} keys) → docs/api/".format(len(CONFIG_ENTRIES)))

    # Website sibling repo (optional — gracefully skip if missing)
    docs_sibling = os.path.normpath(os.path.join(repo_root, "..", "mnemosyne-docs", "src"))
    
    if os.path.isdir(docs_sibling):
        # Tool schema
        www_tool = os.path.join(docs_sibling, "app/(docs)", "api", "tool-schema", "page.mdx")
        os.makedirs(os.path.dirname(www_tool), exist_ok=True)
        with open(www_tool, "w") as f:
            f.write(schema_mdx)
        print("✓ tool-schema page → website sibling")

        # Config table injection
        www_config = os.path.join(docs_sibling, "app/(docs)", "getting-started", "configuration", "page.mdx")
        if os.path.isfile(www_config):
            _inject_config_table(www_config, "\n".join(
                "| `{}` | {} | {} |".format(e["key"], e.get("default", ""), e["desc"])
                for e in CONFIG_ENTRIES
            ))
            print("✓ config table → website sibling")
        else:
            print("⚠️  website config page not found — skip")
    else:
        print("⚠️  website sibling not found — skip (CI runner ok)")

    print("")
    print("Done. Canonical docs written to docs/api/")

if __name__ == "__main__":
    main()
