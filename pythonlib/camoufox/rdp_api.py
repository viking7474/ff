"""Compatibility facade for the legacy `camoufox.rdp_api` import path.

The active RDP framework implementation now lives under `winfox.rdp`.
This module intentionally stays thin and only re-exports the public RDP
surface so existing imports keep working while the codebase transitions.
"""

from winfox.rdp import RDPBrowser, RDPContext, RDPDialog, RDPFrame, RDPPage

__all__ = [
    "RDPBrowser",
    "RDPPage",
    "RDPFrame",
    "RDPContext",
    "RDPDialog",
]
