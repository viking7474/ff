"""CLI entrypoint for the Winfox Python package."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version
from pathlib import Path
from typing import Optional

import rich_click as click

from .pkgman import INSTALL_DIR, launch_path, rprint


def _version() -> str:
    try:
        return pkg_version("winfox")
    except PackageNotFoundError:
        return "0.0.0"


@click.group()
def cli() -> None:
    """Winfox package utilities."""


@cli.command("version")
def version_cmd() -> None:
    rprint(f"winfox {_version()}", fg="cyan")


@cli.command("path")
@click.argument("browser_path", required=False)
def path_cmd(browser_path: Optional[str] = None) -> None:
    try:
        resolved = launch_path(None if browser_path is None else Path(browser_path))
        rprint(resolved, fg="green")
    except Exception as exc:
        rprint(str(exc), fg="red")
        raise SystemExit(1)


@cli.command("info")
def info_cmd() -> None:
    rprint(f"Package version: {_version()}", fg="cyan")
    rprint(f"Default cache dir: {INSTALL_DIR}", fg="cyan")
    rprint("Primary Python RDP namespace: winfox.rdp", fg="yellow")
    rprint("Legacy compatibility namespace: camoufox.legacy", fg="yellow")


if __name__ == "__main__":
    cli()
