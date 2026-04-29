"""Legacy Playwright/Camoufox surface.

Modules in this namespace represent the older Playwright-centric automation
path kept for reference or compatibility while the new framework lives under
`winfox.rdp`.
"""

__all__ = [
    "Camoufox",
    "NewBrowser",
    "NewContext",
    "AsyncCamoufox",
    "AsyncNewBrowser",
    "AsyncNewContext",
    "launch_server",
]


def __getattr__(name):
    if name in {"Camoufox", "NewBrowser", "NewContext"}:
        from . import sync_api as _sync_api

        return getattr(_sync_api, name)

    if name in {"AsyncCamoufox", "AsyncNewBrowser", "AsyncNewContext"}:
        from . import async_api as _async_api

        return getattr(_async_api, name)

    if name == "launch_server":
        from .server import launch_server as _launch_server

        return _launch_server

    raise AttributeError(name)
