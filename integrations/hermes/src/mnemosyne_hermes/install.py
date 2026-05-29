"""Installer CLI for the Mnemosyne Hermes memory provider."""

from __future__ import annotations

import argparse
import importlib
import os
import shutil
import sys
from pathlib import Path

PLUGIN_NAME = "mnemosyne"
EXCLUDED_DIRS = {"__pycache__", ".pytest_cache", ".ruff_cache"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}


def hermes_home() -> Path:
    """Return the Hermes home directory used for user-installed plugins."""
    return Path(os.environ.get("HERMES_HOME") or "~/.hermes").expanduser()


def plugin_source_dir() -> Path:
    """Return the installed mnemosyne_hermes package directory."""
    return Path(__file__).resolve().parent


def plugin_target_dir(hermes_home_path: str | Path | None = None) -> Path:
    """Return the Hermes memory plugin destination for Mnemosyne."""
    base = Path(hermes_home_path).expanduser() if hermes_home_path else hermes_home()
    return base / "plugins" / PLUGIN_NAME


def _ignore_copy_names(_directory: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    for name in names:
        path = Path(name)
        if name in EXCLUDED_DIRS or path.suffix in EXCLUDED_SUFFIXES:
            ignored.add(name)
    return ignored


def check_mnemosyne_core() -> bool:
    """Verify mnemosyne-memory core library is installed."""
    try:
        importlib.import_module("mnemosyne.core.beam")
        import mnemosyne
        print(f"  mnemosyne-memory {mnemosyne.__version__} installed")
        return True
    except ImportError:
        return False


def install_plugin(
    *,
    hermes_home_path: str | Path | None = None,
    force: bool = False,
) -> Path:
    """Install the Mnemosyne provider into Hermes' user plugin directory."""
    source = plugin_source_dir()
    target = plugin_target_dir(hermes_home_path)

    if target.exists():
        if not force:
            raise FileExistsError(
                f"{target} already exists. Re-run with --force to replace it."
            )
        shutil.rmtree(target)

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, ignore=_ignore_copy_names)

    # Also create a convenience plugin.yaml in the target if not present
    plugin_yaml = target / "plugin.yaml"
    if not plugin_yaml.exists():
        plugin_yaml.write_text(
            f"name: {PLUGIN_NAME}\n"
            "version: auto\n"
            'description: "Mnemosyne — local-first AI memory for Hermes"\n'
            "pip_dependencies:\n"
            "  - mnemosyne-memory>=3.1\n"
        )

    return target


def uninstall_plugin(*, hermes_home_path: str | Path | None = None) -> Path:
    """Remove the Mnemosyne provider from Hermes' user plugin directory."""
    target = plugin_target_dir(hermes_home_path)
    if target.exists():
        shutil.rmtree(target)
    return target


def is_installed(*, hermes_home_path: str | Path | None = None) -> bool:
    """Return whether the Mnemosyne provider is installed for Hermes discovery."""
    target = plugin_target_dir(hermes_home_path)
    return (target / "__init__.py").is_file() and (target / "plugin.yaml").is_file()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mnemosyne-hermes",
        description="Install the Mnemosyne memory provider for Hermes Agent.",
    )
    parser.add_argument(
        "--hermes-home",
        help="Hermes home directory. Defaults to HERMES_HOME or ~/.hermes.",
    )

    subparsers = parser.add_subparsers(dest="command")

    install = subparsers.add_parser(
        "install",
        help="Install Mnemosyne into Hermes' memory provider plugin directory.",
    )
    install.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing Mnemosyne plugin directory.",
    )

    subparsers.add_parser(
        "uninstall",
        help="Remove Mnemosyne from Hermes' memory provider plugin directory.",
    )
    subparsers.add_parser(
        "status",
        help="Show whether Mnemosyne is installed for Hermes memory discovery.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the mnemosyne-hermes installer CLI."""
    parser = _parser()
    args = parser.parse_args(argv)
    command = args.command or "install"

    try:
        if command == "install":
            # Check core library first
            if not check_mnemosyne_core():
                print(
                    "  mnemosyne-memory NOT found. Install it first:\n"
                    "    pip install mnemosyne-memory",
                    file=sys.stderr,
                )
                return 1

            target = install_plugin(
                hermes_home_path=args.hermes_home,
                force=getattr(args, "force", False),
            )
            print(f"Installed Mnemosyne Hermes provider to {target}")
            print("Next steps:")
            print("  hermes config set memory.provider mnemosyne")
            print("  hermes memory setup")
            print("  hermes memory status")
            return 0

        if command == "uninstall":
            target = uninstall_plugin(hermes_home_path=args.hermes_home)
            print(f"Removed Mnemosyne Hermes provider from {target}")
            return 0

        if command == "status":
            target = plugin_target_dir(args.hermes_home)
            if is_installed(hermes_home_path=args.hermes_home):
                print(f"Mnemosyne Hermes provider is installed at {target}")
                print(f"  Core library: {'OK' if check_mnemosyne_core() else 'MISSING'}")
                return 0
            print(f"Mnemosyne Hermes provider is not installed at {target}")
            return 1

    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
