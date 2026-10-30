"""
Mnemosyne Plugin for Hermes Agent
Entry point at repo root for `hermes plugins install` compatibility.

IMPORTANT: this file is the Hermes plugin shim at the repository root, NOT
the mnemosyne package. With the repo root on sys.path (e.g. cwd at the repo
root), `import mnemosyne` binds this stub, which exposes only
__version__, __author__, register(), and register_memory_provider(). The real
mnemosyne package lives at mnemosyne/mnemosyne/, so `mnemosyne.core` is
unavailable here: `import mnemosyne.core` raises ModuleNotFoundError and
attribute access `mnemosyne.core` raises a loud ImportError (see the
__getattr__ guard below). That is intentional plugin-layout behavior, not a
broken install — install mnemosyne (pip install <repo root>) or run with the
repo's mnemosyne/ package directory on sys.path so mnemosyne.core resolves to
the real package.
"""

import sys
from pathlib import Path

# Ensure this directory is on path so `hermes_plugin` is discoverable.
# Unconditional insert: when the repo is checked out under
# $HERMES_HOME/plugins/ (the root-repo layout), an ambient sys.path entry for
# that parent dir can shadow this checkout — making `import mnemosyne`
# resolve to THIS plugin __init__ (the stub) instead of the mnemosyne core
# subpackage. hermes_memory_provider's `from mnemosyne.core...` imports then
# fail with "No module named 'mnemosyne.core'" and the provider silently does
# not load. Always promoting the real repo root keeps the plugin's own core
# authoritative regardless of how the process was launched (Hermes runtime,
# pytest namespace detection, etc.).
_repo_root = Path(__file__).resolve().parent
sys.path.insert(0, str(_repo_root))

# Re-export __version__ / __author__ from the inner mnemosyne subpackage so
# `from mnemosyne import __version__` works in either install layout:
#   - Hermes plugin tree: outer `mnemosyne/` is the resolved package, inner
#     `mnemosyne/mnemosyne/` is the subpackage `mnemosyne.mnemosyne`.
#   - pip / repo-direct install: inner `mnemosyne/` is the resolved package
#     directly and this stub is never loaded.
# Without this re-export, `hermes mnemosyne version` (and any other caller
# doing `from mnemosyne import __version__`) crashed with ImportError under
# the Hermes plugin layout. See issue #53.
try:
    from .mnemosyne import __version__, __author__
except ImportError:
    __version__ = "unknown"
    __author__ = "Abdias J"

# The Hermes memory provider loader (plugins/memory/__init__.py) loads a
# provider module and then either:
#   1. calls mod.register(collector) — the collector's
#      register_memory_provider(provider) captures the active provider, or
#   2. instantiates a top-level MemoryProvider subclass.
# The `register` symbol below is therefore the loader's entry point for this
# module (the provider implementation lives in hermes_memory_provider/).
#
# When hermes_plugin is importable (a full Hermes deployment), `register` must
# still dispatch: the memory loader ALWAYS calls mod.register(collector), so
# if register were simply hermes_plugin's own callable, a memory-provider
# collector would be routed down the legacy plugin path and would never
# receive MnemosyneMemoryProvider (review feedback from dplush on #565).
# Dispatch is therefore driven by the ctx shape — a memory-provider collector
# is uniquely identifiable by its register_memory_provider method — while any
# other (legacy plugin) context keeps the hermes_plugin registration path
# intact. See tests/test_init_register_shadowing.py and
# tests/test_loader_registers_provider.py.
try:
    from hermes_plugin import register as _legacy_register
except ImportError:
    _legacy_register = None


def register(ctx):
    """Loader entry point: dispatch between the memory-provider bridge and the
    legacy hermes_plugin registration path based on the ctx shape.

    - A memory-provider collector (has ``register_memory_provider``) →
      register exactly one MnemosyneMemoryProvider via the bridge.
    - Any other ctx (legacy Hermes plugin context) → hermes_plugin.register,
      when the SDK is importable.
    """
    if hasattr(ctx, "register_memory_provider"):
        register_memory_provider(ctx)
    elif _legacy_register is not None:
        return _legacy_register(ctx)
    else:
        # No hermes_plugin SDK available: only the memory-loader contract can
        # apply in this layout, so route through the bridge.
        register_memory_provider(ctx)

__all__ = ["register", "__version__", "__author__"]


# ---- Memory Provider bridge ----
# plugins/memory/__init__.py discovers this directory by text-scanning the
# top-level __init__.py for `register_memory_provider` or `MemoryProvider`
# (_is_memory_provider_dir), then drives loading through `register` (above)
# or a MemoryProvider subclass. This symbol keeps the discovery marker
# present and exposes the delegation as a stable module-level API even in
# install layouts where `register` is supplied by hermes_plugin.
def register_memory_provider(ctx):
    """Bridge to hermes_memory_provider for memory provider discovery."""
    try:
        from .hermes_memory_provider import register_memory_provider
    except ModuleNotFoundError as exc:
        if exc.name != f"{__package__}.hermes_memory_provider":
            raise  # Transitive dependency missing inside the module — let it propagate
        return  # Bridge module genuinely absent — tools/hooks still load via hermes_plugin
    register_memory_provider(ctx)


# This file is the Hermes plugin shim at the repository root, NOT the
# mnemosyne package itself. With the repo root on sys.path (e.g. cwd at the
# repo root), `import mnemosyne` binds this stub: it exposes only
# __version__, __author__, register(), and register_memory_provider(). The
# real mnemosyne package lives at mnemosyne/mnemosyne/, so mnemosyne.core is
# unavailable here — `import mnemosyne.core` raises ModuleNotFoundError and
# attribute access `mnemosyne.core` raises the ImportError below. That is
# intentional plugin-layout behavior, not a broken install: install mnemosyne
# (pip install <repo root>) or run with the repo's mnemosyne/ package
# directory on sys.path so mnemosyne.core resolves to the real package.
# See tests/test_init_register_shadowing.py and
# tests/test_loader_registers_provider.py for the loader contract this stub
# satisfies.
_STUB_MISSING_SUBPACKAGES = frozenset({"core"})


def __getattr__(name: str):
    """Loud failure for real-package subpackages this stub does not provide.

    Attribute access such as ``mnemosyne.core`` on this shim raises
    ImportError with an actionable message instead of a confusing partial
    import (a stub that imports fine but lacks .core).
    """
    if name in _STUB_MISSING_SUBPACKAGES:
        repo_root = Path(__file__).resolve().parent
        raise ImportError(
            f"mnemosyne.{name} is not available through this module. "
            f"{__file__} is the Hermes plugin shim at the repository root "
            f"({repo_root}), not the mnemosyne package itself: `import mnemosyne` "
            f"from here binds a partial stub "
            f"(__version__, __author__, register, register_memory_provider "
            f"only). Install mnemosyne (pip install {repo_root}) or run with "
            f"the repo's mnemosyne/ package directory on sys.path so "
            f"mnemosyne.core resolves to the real package. The repo-root "
            f"shadow is intentional for Hermes plugin discovery, not a broken "
            f"install."
        )
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
