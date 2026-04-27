"""CLI entrypoint for the Winfox Python package.

This intentionally reuses the existing package-management CLI implementation
from the historical Camoufox package while presenting a Winfox-branded entry
point for the new framework namespace.
"""

from camoufox.__main__ import cli as _legacy_cli
from camoufox.pkgman import rprint


def cli() -> None:
    rprint(
        "Winfox Python CLI. Legacy package-management commands are routed through the historical Camoufox implementation.",
        fg="yellow",
    )
    _legacy_cli()


if __name__ == "__main__":
    cli()
