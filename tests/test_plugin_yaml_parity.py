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


def test_registered_tools_are_declared_in_plugin_yaml():
    """Every runtime-registered schema must be declared in plugin.yaml.

    Honest direction: a new tool added to the provider without a declaration
    must fail here, and the failure message lists the missing names.
    """
    from hermes_memory_provider import MnemosyneMemoryProvider

    provider = MnemosyneMemoryProvider()
    registered = {s["name"] for s in provider.get_tool_schemas()}
    declared = set(_plugin_yaml_tools())

    missing = registered - declared
    assert not missing, (
        f"registered tool(s) missing from plugin.yaml provides_tools: "
        f"{sorted(missing)}"
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