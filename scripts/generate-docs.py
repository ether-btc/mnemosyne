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
# Tool schema definitions (manual — reviewed against v3.4.0 code)
# ---------------------------------------------------------------
ALL_TOOL_SCHEMAS = [
    {"name": "mnemosyne_remember", "description": "Store a durable memory", "params": {"content": "string", "importance": "float=0.5", "source": "string", "scope": "string=session", "valid_until": "string", "extract_entities": "bool", "extract": "bool", "metadata": "dict", "veracity": "string"}},
    {"name": "mnemosyne_recall", "description": "Search memories by vector+FTS hybrid ranking", "params": {"query": "string", "limit": "int=5", "temporal_weight": "float=0.0", "query_time": "string", "temporal_halflife": "float=24", "vec_weight": "float", "fts_weight": "float", "importance_weight": "float"}},
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
    {"name": "mnemosyne_end", "description": "Graceful shutdown: persist, flush caches, close connections", "params": {}},
]

# NOTE: 24 MCP tools exactly, covering every memory surface (BEAM, surface, scratchpad, graph)

# ---------------------------------------------------------------
# Config schema (env vars for mnemosyne)
# ---------------------------------------------------------------
CONFIG_ENTRIES = [
    {"key": "MNEMOSYNE_DB_PATH", "env": "MNEMOSYNE_DB_PATH", "default": "~/.mnemosyne/mnemosyne.db", "desc": "Path to the SQLite database"},
    {"key": "MNEMOSYNE_EMBEDDING_MODEL", "env": "MNEMOSYNE_EMBEDDING_MODEL", "default": "all-MiniLM-L6-v2", "desc": "SentenceTransformer model for vector embeddings"},
    {"key": "MNEMOSYNE_EMBEDDING_DEVICE", "env": "MNEMOSYNE_EMBEDDING_DEVICE", "default": "cpu", "desc": "Device for embeddings: cpu, cuda, mps"},
    {"key": "MNEMOSYNE_BEAM_ENABLED", "env": "MNEMOSYNE_BEAM_ENABLED", "default": "true", "desc": "Enable BEAM (Budget Elastic Adaptive Memory) tiering"},
    {"key": "MNEMOSYNE_BEAM_CPU_THRESHOLD", "env": "MNEMOSYNE_BEAM_CPU_THRESHOLD", "default": "5000", "desc": "Max working memories before cold tier promotion"},
    {"key": "MNEMOSYNE_BEAM_COLD_THRESHOLD", "env": "MNEMOSYNE_BEAM_COLD_THRESHOLD", "default": "10000", "desc": "Max cold memories before frozen tier promotion"},
    {"key": "MNEMOSYNE_MCP_TOKEN", "env": "MNEMOSYNE_MCP_TOKEN", "default": "", "desc": "Bearer token for MCP server auth (required for remote deployment)"},
    {"key": "MNEMOSYNE_MCP_HOST", "env": "MNEMOSYNE_MCP_HOST", "default": "0.0.0.0", "desc": "MCP server bind address"},
    {"key": "MNEMOSYNE_MCP_PORT", "env": "MNEMOSYNE_MCP_PORT", "default": "4321", "desc": "MCP server port"},
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
    marker = "<!-- GENERATED_CONFIG_TABLE -->"
    new_table = marker + "\n" + table_html + "\n<!-- /GENERATED_CONFIG_TABLE -->"
    if marker in content:
        content = content.replace(marker, new_table)
    else:
        content = content + "\n" + new_table
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
