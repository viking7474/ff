"""Compatibility package surface for Camoufox.

`winfox.rdp` is the active RDP implementation. `camoufox.rdp_api` is kept as a
thin compatibility facade, while the Playwright-centric API lives under
`camoufox.legacy` and is lazily re-exported here for backward compatibility.
"""

__all__ = [
    "Camoufox",
    "NewBrowser",
    "NewContext",
    "AsyncCamoufox",
    "AsyncNewBrowser",
    "AsyncNewContext",
    "RDPBrowser",
    "RDPPage",
    "RDPFrame",
    "RDPContext",
    "RDPDialog",
    "DefaultAddons",
    "launch_options",
]


def __getattr__(name):
    if name == "DefaultAddons":
        from .addons import DefaultAddons as _DefaultAddons

        return _DefaultAddons

    if name == "launch_options":
        from .utils import launch_options as _launch_options

        return _launch_options

    if name in {"RDPBrowser", "RDPPage", "RDPFrame", "RDPContext", "RDPDialog"}:
        from . import rdp_api as _rdp_api

        return getattr(_rdp_api, name)

    if name in {
        "Camoufox",
        "NewBrowser",
        "NewContext",
        "AsyncCamoufox",
        "AsyncNewBrowser",
        "AsyncNewContext",
    }:
        try:
            if name.startswith("Async"):
                from .legacy import async_api as _async_api

                return getattr(_async_api, name)
            from .legacy import sync_api as _sync_api

            return getattr(_sync_api, name)
        except Exception as exc:  # pragma: no cover - legacy best effort
            raise AttributeError(name) from exc

    raise AttributeError(name)
