"""Compatibility wrapper for the legacy Playwright server entrypoint."""

from .legacy.server import launch_server

__all__ = ["launch_server"]
