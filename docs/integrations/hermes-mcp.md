# Mnemosyne + Hermes Agent

Mnemosyne is the native memory provider for Hermes Agent. Two integration paths:

## Path 1: MCP (recommended for latest)

Add to your Hermes `config.yaml`:

```yaml
mcp:
  servers:
    mnemosyne:
      command: mnemosyne
      args: ["mcp"]
```

Tools register as native Hermes commands.

## Path 2: Hermes Plugin (built-in)

If you installed Mnemosyne via `deploy_hermes_provider.sh`, it's already active:

```bash
curl -sSL https://raw.githubusercontent.com/AxDSan/mnemosyne/main/deploy_hermes_provider.sh | bash
```

This symlinks the provider into `~/.hermes/plugins/mnemosyne`.

## Usage

In Hermes, use the built-in commands:
- `mnemosyne_remember` — Store a memory
- `mnemosyne_recall` — Search memories
- `mnemosyne_forget` — Remove a memory
- `mnemosyne_stats` — View memory statistics
- `mnemosyne_sleep` — Run consolidation
