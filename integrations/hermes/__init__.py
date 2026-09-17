"""Directory-plugin entry point for the Hermes plugin catalog.

The catalog installs this directory and loads it directly; the real
implementation comes from the ``mnemosyne-hermes`` PyPI package, which the
plugin installer puts into the Hermes venv from ``pyproject.toml``
dependencies (per hermes-agent#113851).
"""

from mnemosyne_hermes import register, register_memory_provider  # noqa: F401

__all__ = ["register", "register_memory_provider"]
