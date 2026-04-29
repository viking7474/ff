"""Compatibility wrapper for the legacy sync Playwright API."""

from .legacy.sync_api import Camoufox, NewBrowser, NewContext

__all__ = ["Camoufox", "NewBrowser", "NewContext"]
