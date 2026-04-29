"""Compatibility wrapper for the legacy async Playwright API."""

from .legacy.async_api import AsyncCamoufox, AsyncNewBrowser, AsyncNewContext

__all__ = ["AsyncCamoufox", "AsyncNewBrowser", "AsyncNewContext"]
