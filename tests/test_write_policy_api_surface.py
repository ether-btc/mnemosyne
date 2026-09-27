"""Coverage for the write-policy API that the 4.0.0b3 core added (item 4).

Before the clean install these symbols did not exist in `mnemosyne.core.filters`
at all — the provider imported them and the 3.15.2 core had never heard of them.
That is precisely the class of defect that produces a plugin which loads cleanly
and then fails on first use, so the symbols now have explicit tests.

These tests are structural: they assert the API is present and that the provider
and core agree. They deliberately do not touch the live database.
"""

from __future__ import annotations

import ast
import inspect
import pathlib

import pytest

import mnemosyne
from mnemosyne.core import filters

# The nine symbols the 4.0.0b3 provider imports and the 3.15.2 core lacked.
REQUIRED = (
    "resolve_write_policy",
    "make_write_policy",
    "current_write_policy",
    "active_write_policy",
    "write_policy_operation",
    "admit_memory_write",
    "_SYSTEM_DERIVED_WRITE_CAPABILITY",
    "is_write_policy_exempt",
    "classify_memory_write",
)


def _provider_plugin_version() -> str:
    import hermes_memory_provider as hmp

    plugin_yaml = pathlib.Path(hmp.__file__).parent / "plugin.yaml"
    for line in plugin_yaml.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("version:"):
            return line.split(":", 1)[1].strip().strip("\"'")
    raise AssertionError(f"no version key in {plugin_yaml}")


def test_version_is_coherent() -> None:
    """The whole defect was a version split. Pin the coherence explicitly."""
    assert mnemosyne.__version__ == "4.0.0b3"
    assert _provider_plugin_version() == mnemosyne.__version__, (
        "plugin.yaml and mnemosyne.__version__ disagree — that is the 3.15.2/4.0.0b3 "
        "split that made the provider load cleanly and fail on first use"
    )


@pytest.mark.parametrize("name", REQUIRED)
def test_write_policy_symbol_exists(name: str) -> None:
    """Every symbol the provider imports from filters must exist."""
    assert hasattr(filters, name), f"mnemosyne.core.filters.{name} is missing"


def test_write_policy_entrypoints_are_callable() -> None:
    for name in (
        "resolve_write_policy",
        "make_write_policy",
        "current_write_policy",
        "active_write_policy",
        "write_policy_operation",
        "admit_memory_write",
        "classify_memory_write",
    ):
        assert callable(getattr(filters, name)), f"{name} is not callable"


def test_write_policy_operation_arity_is_stable() -> None:
    """Signature is the contract the provider calls against.

    `write_policy_operation(policy=None) -> Iterator[WritePolicySnapshot]` — it
    takes the snapshot, not a write kind, and returns an iterator.
    """
    sig = inspect.signature(filters.write_policy_operation)
    assert list(sig.parameters) == ["policy"]
    assert sig.parameters["policy"].default is None
    assert "Iterator" in str(sig.return_annotation)


def test_active_write_policy_returns_snapshot_or_none() -> None:
    """Must be safe to call with no policy configured."""
    result = filters.active_write_policy()
    assert result is None or isinstance(result, filters.WritePolicySnapshot)


def test_current_and_resolve_are_snapshots() -> None:
    assert isinstance(filters.resolve_write_policy(), filters.WritePolicySnapshot)
    assert isinstance(filters.current_write_policy(), filters.WritePolicySnapshot)


def test_provider_and_core_agree_on_filters_symbols() -> None:
    """The real invariant: every `from mnemosyne.core.filters import X` resolves.

    This is the check that would have caught the version split at test time
    instead of at the first tool call in production.
    """
    import hermes_memory_provider as hmp

    src = pathlib.Path(hmp.__file__).read_text(encoding="utf-8")
    missing: list[str] = []
    checked = 0
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ImportFrom) and node.module == "mnemosyne.core.filters":
            for alias in node.names:
                checked += 1
                if not hasattr(filters, alias.name):
                    missing.append(alias.name)
    assert checked > 0, "no filters import found — the AST walk itself is wrong"
    assert not missing, f"provider imports missing from filters: {missing}"


def test_every_imported_core_module_resolves() -> None:
    """Broaden the same invariant to every `from mnemosyne... import` in the provider.

    A `from pkg import name` is satisfied EITHER by an attribute on the package OR
    by a submodule of that name — `from mnemosyne.core import model_refresh` is a
    submodule import, and treating it as a missing attribute is a false positive
    (that exact mistake was made earlier in this investigation).
    """
    import importlib

    import hermes_memory_provider as hmp

    src = pathlib.Path(hmp.__file__).read_text(encoding="utf-8")
    gaps: list[str] = []
    checked = 0
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, ast.ImportFrom):
            continue
        mod = node.module or ""
        if not mod.startswith("mnemosyne"):
            continue
        try:
            target = importlib.import_module(mod)
        except Exception as exc:  # noqa: BLE001 - report, do not raise
            gaps.append(f"{mod}: {exc}")
            continue
        for alias in node.names:
            checked += 1
            if hasattr(target, alias.name):
                continue
            # Fall back to a submodule of the same name before calling it a gap.
            try:
                importlib.import_module(f"{mod}.{alias.name}")
            except Exception:  # noqa: BLE001
                gaps.append(f"{mod}.{alias.name}")
    assert checked > 0
    assert not gaps, f"provider has unresolvable mnemosyne imports: {gaps}"
