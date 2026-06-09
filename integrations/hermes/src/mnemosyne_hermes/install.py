"""Installer CLI for the Mnemosyne Hermes memory provider."""

from __future__ import annotations

import argparse
import importlib
import os
import shutil
import sys
from pathlib import Path

PLUGIN_NAME = "mnemosyne"


def hermes_home() -> Path:
    """Return the Hermes home directory used for user-installed plugins."""
    return Path(os.environ.get("HERMES_HOME") or "~/.hermes").expanduser()


def _resolve_package_dir() -> Path:
    """Return the installed mnemosyne_hermes package directory."""
    import mnemosyne_hermes
    return Path(mnemosyne_hermes.__file__).resolve().parent


def plugin_target_dir(hermes_home_path: str | Path | None = None) -> Path:
    """Return the Hermes memory plugin destination for Mnemosyne.

    Directory name matches the provider name used in
    ``memory.provider: mnemosyne`` config. Hermes discovers memory
    providers by scanning ``$HERMES_HOME/plugins/<name>/`` for
    directories whose ``__init__.py`` contains ``register_memory_provider``
    or ``MemoryProvider``.
    """
    base = Path(hermes_home_path).expanduser() if hermes_home_path else hermes_home()
    return base / "plugins" / PLUGIN_NAME


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
    """Install the Mnemosyne provider into Hermes' user plugin directory.

    Creates a symlink from ``$HERMES_HOME/plugins/mnemosyne/`` to the
    installed ``mnemosyne_hermes`` package directory. Hermes discovers
    memory providers by scanning ``$HERMES_HOME/plugins/<name>/`` for
    directories whose ``__init__.py`` contains ``register_memory_provider``
    or ``MemoryProvider``.

    The symlink approach means all relative imports (cli, tools, audit)
    resolve correctly through the real package, and ``hermes update`` /
    ``pipx upgrade mnemosyne-hermes`` automatically refreshes the target.
    """
    source = _resolve_package_dir()
    if not source.is_dir():
        raise FileNotFoundError(
            f"mnemosyne_hermes package not found at {source}"
        )

    base = Path(hermes_home_path).expanduser() if hermes_home_path else hermes_home()
    target = plugin_target_dir(hermes_home_path)

    # Migrate from old hermes-mnemosyne directory (deploy script era)
    old_plugin_dir = base / "plugins" / "hermes-mnemosyne"
    if old_plugin_dir.is_symlink() or old_plugin_dir.exists():
        if old_plugin_dir.is_symlink() or os.path.islink(str(old_plugin_dir)):
            old_plugin_dir.unlink()
        else:
            shutil.rmtree(old_plugin_dir)
        logger = print
        logger(f"  Removed old plugin directory: {old_plugin_dir}")

    # Also migrate config from old provider name
    config_path = base / "config.yaml"
    if config_path.is_file():
        try:
            config_text = config_path.read_text(encoding="utf-8")
            if "provider: hermes-mnemosyne" in config_text:
                new_text = config_text.replace("provider: hermes-mnemosyne", "provider: mnemosyne")
                config_path.write_text(new_text, encoding="utf-8")
                print("  Updated config: memory.provider hermes-mnemosyne -> mnemosyne")
        except Exception:
            pass

    if target.is_symlink() or target.exists():
        if not force:
            raise FileExistsError(
                f"{target} already exists. Re-run with --force to replace it."
            )
        # Remove existing link or directory cleanly
        if target.is_symlink():
            target.unlink()
        elif target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()

    target.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(str(source), str(target))
    return target


def uninstall_plugin(*, hermes_home_path: str | Path | None = None) -> Path:
    """Remove the Mnemosyne provider symlink from Hermes' user plugin directory."""
    target = plugin_target_dir(hermes_home_path)
    if target.is_symlink():
        target.unlink()
    elif target.exists():
        shutil.rmtree(target)
    return target


def is_installed(*, hermes_home_path: str | Path | None = None) -> bool:
    """Return whether the Mnemosyne provider symlink exists for Hermes discovery.

    Checks that the target is a symlink (or directory) with a valid
    ``__init__.py`` containing the expected symbols.
    """
    target = plugin_target_dir(hermes_home_path)
    if not target.exists():
        return False
    init_file = target / "__init__.py"
    if not init_file.is_file():
        return False
    try:
        source = init_file.read_text(errors="replace")[:4096]
        return "register_memory_provider" in source or "MnemosyneMemoryProvider" in source
    except Exception:
        return False


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
            print(f"Installed. Symlink at {target}")
            print(f"  -> {os.readlink(str(target))}")
            print("Done. Next steps:")
            print("  hermes config set memory.provider mnemosyne")
            print("  hermes memory status")
            return 0

        if command == "uninstall":
            target = uninstall_plugin(hermes_home_path=args.hermes_home)
            print(f"Removed. Symlink at {target} deleted.")
            return 0

        if command == "status":
            target = plugin_target_dir(args.hermes_home)
            if is_installed(hermes_home_path=args.hermes_home):
                print(f"Installed. Symlink at {target}")
                print(f"  -> {os.readlink(str(target))}")
                print(f"  Core library: {'OK' if check_mnemosyne_core() else 'MISSING'}")
                return 0
            print(f"Not installed (expected symlink at {target})")
            return 1

    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
