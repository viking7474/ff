__all__ = [
    "Camoufox",
    "NewBrowser",
    "NewContext",
    "AsyncCamoufox",
    "AsyncNewBrowser",
    "AsyncNewContext",
    "RDPBrowser",
    "RDPPage",
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

    if name in {"RDPBrowser", "RDPPage"}:
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
                from . import async_api as _async_api

                return getattr(_async_api, name)
            from . import sync_api as _sync_api

            return getattr(_sync_api, name)
        except Exception as exc:  # pragma: no cover - legacy best effort
            raise AttributeError(name) from exc

    raise AttributeError(name)
