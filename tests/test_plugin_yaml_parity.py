"""Parity between plugin.yaml's declared tool surface and the runtime registry.

Guards the defect where the *declared* surface (hermes_memory_provider/plugin.yaml
provides_tools) drifts from the *registered* runtime surface
(MnemosyneMemoryProvider.get_tool_schemas()). A tool added to the provider
without a matching declaration (or vice versa) leaves Hermes advertising a
surface that does not match what the provider actually implements.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

REPO = Path(__file__).parent.parent


def _plugin_yaml_tools():
    """provides_tools from plugin.yaml, parsed without requiring PyYAML."""
    text = (REPO / "hermes_memory_provider" / "plugin.yaml").read_text()
    block = text.split("provides_tools:")[1].split("provides_hooks:")[0]
    return re.findall(r"^\s*-\s*(mnemosyne_\w+)\s*$", block, re.M)


# Deliberate deferral (merge follow-up 9c401acb): the provider still registers
# these tools, but mnemosyne.tool_schemas has no _SCHEMA for them in either
# tree, so declaring them in plugin.yaml would break upstream's
# test_plugin_yaml_tools_all_have_schemas. They stay registered at runtime and
# deferred from the declared surface until upstream ships their schemas.
DEFERRED_DECLARATION = {
    "mnemosyne_apply_pending",
    "mnemosyne_model_card",
    "mnemosyne_model_refresh",
    "mnemosyne_recall_diagnostics",
    "mnemosyne_resolve_conflicts",
    "mnemosyne_task_progress",
}


def test_registered_tools_are_declared_in_plugin_yaml():
    """Every runtime-registered schema must be declared in plugin.yaml.

    Exceptions: only the explicitly DEFERRED_DECLARATION set above. Any other
    new still undeclared tool registered by the provider must fail here.
    """
    from hermes_memory_provider import MnemosyneMemoryProvider

    provider = MnemosyneMemoryProvider()
    registered = {s["name"] for s in provider.get_tool_schemas()}
    declared = set(_plugin_yaml_tools())

    missing = registered - declared
    unexpected = missing - DEFERRED_DECLARATION
    assert not unexpected, (
        f"registered tool(s) missing from plugin.yaml provides_tools: "
        f"{sorted(unexpected)}"
    )
    truly_missing = missing - unexpected
    assert truly_missing <= DEFERRED_DECLARATION, (
        f"undeclared drift beyond the recorded deferral policy: "
        f"{sorted(truly_missing)}"
    )


def test_declared_tools_are_registered_at_runtime():
    """Every name in plugin.yaml provides_tools must be registered at runtime."""
    from hermes_memory_provider import MnemosyneMemoryProvider

    provider = MnemosyneMemoryProvider()
    registered = {s["name"] for s in provider.get_tool_schemas()}
    declared = set(_plugin_yaml_tools())

    unknown = declared - registered
    assert not unknown, (
        f"plugin.yaml declares tool(s) not registered at runtime: "
        f"{sorted(unknown)}"
    )