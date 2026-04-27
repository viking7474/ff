from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from camoufox.rdp_api import RDPBrowser, RDPPage


class RDPContext:
    """Minimal browser context wrapper backed by an isolated child browser."""

    def __init__(self, parent_browser: "RDPBrowser", browser: "RDPBrowser"):
        self._parent_browser = parent_browser
        self._browser = browser
        self._closed = False

    @property
    def browser(self) -> "RDPBrowser":
        return self._browser

    @property
    def profile_path(self) -> Optional[str]:
        return self._browser._profile_path

    @property
    def rdp_port(self) -> int:
        return self._browser._rdp_port

    @property
    def ws_port(self) -> int:
        return self._browser._ws_port

    def is_closed(self) -> bool:
        return self._closed

    async def new_page(self) -> "RDPPage":
        if self._closed:
            raise RuntimeError("Context is closed")
        return await self._browser.new_page()

    def pages(self) -> List["RDPPage"]:
        if self._closed:
            return []
        return self._browser.list_pages()

    async def get_active_page(self) -> Optional["RDPPage"]:
        if self._closed:
            return None
        return await self._browser.get_active_page()

    async def save_state(self) -> Dict[str, Any]:
        if self._closed:
            raise RuntimeError("Context is closed")
        return await self._browser.save_state()

    async def load_state(self, state: Dict[str, Any], clear_existing: bool = True) -> Dict[str, int]:
        if self._closed:
            raise RuntimeError("Context is closed")
        return await self._browser.load_state(state, clear_existing=clear_existing)

    async def save_state_to_file(self, path: str) -> str:
        if self._closed:
            raise RuntimeError("Context is closed")
        return await self._browser.save_state_to_file(path)

    async def load_state_from_file(self, path: str, clear_existing: bool = True) -> Dict[str, int]:
        if self._closed:
            raise RuntimeError("Context is closed")
        return await self._browser.load_state_from_file(path, clear_existing=clear_existing)

    async def close(self) -> None:
        if self._closed:
            return
        await self._browser.close()
        self._closed = True
        self._parent_browser._unregister_context(self)

    async def __aenter__(self) -> "RDPContext":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()
