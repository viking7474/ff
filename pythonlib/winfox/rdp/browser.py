"""Transitional browser module for the Winfox RDP framework.

This module establishes the official namespace home for browser-layer APIs
while the implementation is still hosted in ``camoufox.rdp_api`` during the
incremental refactor.
"""

from camoufox.rdp_api import RDPBrowser

__all__ = [
    "RDPBrowser",
]
