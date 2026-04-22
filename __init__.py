"""
Mnemosyne Plugin for Hermes Agent
Entry point at repo root for `hermes plugins install` compatibility.
"""

import sys
from pathlib import Path

# Ensure this directory is on path so `hermes_plugin` is always importable
_repo_root = Path(__file__).resolve().parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from hermes_plugin import register
__all__ = ["register"]
