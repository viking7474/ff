"""Page-layer home for the Winfox RDP framework.

This module is the new namespace home for the page layer.

To keep risk low while preserving runtime behavior, the current `RDPPage`
implementation subclasses the legacy implementation from ``camoufox.rdp_api``.
That means:

1. `_Mouse` and `_Keyboard` are physically moved here already
2. `RDPPage` now lives in the new namespace as a concrete class
3. the remaining inherited methods can be peeled off incrementally in later
   refactor batches without destabilizing the framework
"""

import asyncio
import base64
import json
import mimetypes
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from camoufox.humanize import generate_path as _generate_path, hover_delay as _hover_delay
from camoufox.rdp_api import RDPPage as _LegacyRDPPage
from geckordp.actors.root import RootActor
from geckordp.actors.screenshot import ScreenshotActor

from .locator import _Locator

if TYPE_CHECKING:
    from camoufox.rdp_api import RDPPage as _LegacyRDPPage


class _Mouse:
    def __init__(self, page: "_LegacyRDPPage"):
        self._page = page
        import random as _r

        self._x: float = _r.uniform(300, 700)
        self._y: float = _r.uniform(200, 500)

    async def _raw_move(self, x: float, y: float) -> None:
        self._page._ensure_open()
        if self._page._bridge and self._page._bridge.is_connected and self._page._tab_id is not None:
            await self._page._bridge.send_command("moveTo", {"tabId": self._page._tab_id, "x": x, "y": y})

    async def _follow_path(self, path):
        for x, y, delay in path:
            await self._raw_move(x, y)
            await asyncio.sleep(delay)
        if path:
            self._x, self._y = path[-1][0], path[-1][1]

    async def click(self, x: float, y: float, button: int = 0) -> None:
        self._page._ensure_open()
        dx = x - self._x
        dy = y - self._y
        if dx * dx + dy * dy >= 4:
            await self.move_smooth(x, y)

        if self._page._bridge and self._page._bridge.is_connected and self._page._tab_id is not None:
            await self._page._bridge.send_command(
                "click", {"tabId": self._page._tab_id, "x": self._x, "y": self._y, "button": button}
            )
        else:
            await self._page.evaluate(f"document.elementFromPoint({self._x},{self._y})?.click()")

    async def move(self, x: float, y: float) -> None:
        self._page._ensure_open()
        await self._raw_move(x, y)
        self._x, self._y = x, y

    async def move_smooth(self, x: float, y: float, target_width: float = 50.0) -> None:
        self._page._ensure_open()
        path = _generate_path(self._x, self._y, x, y, target_width)
        await self._follow_path(path)

    async def click_smooth(self, x: float, y: float, button: int = 0, target_width: float = 50.0) -> None:
        self._page._ensure_open()
        await self.move_smooth(x, y, target_width)
        await asyncio.sleep(_hover_delay())
        await self.click(self._x, self._y, button)

    async def down(self, x: float, y: float, button: int = 0) -> None:
        self._page._ensure_open()
        if self._page._bridge and self._page._bridge.is_connected and self._page._tab_id is not None:
            await self._page._bridge.send_command(
                "mouseDown", {"tabId": self._page._tab_id, "x": x, "y": y, "button": button}
            )

    async def up(self, x: float, y: float, button: int = 0) -> None:
        self._page._ensure_open()
        if self._page._bridge and self._page._bridge.is_connected and self._page._tab_id is not None:
            await self._page._bridge.send_command(
                "mouseUp", {"tabId": self._page._tab_id, "x": x, "y": y, "button": button}
            )

    async def wheel(self, delta_x: float, delta_y: float) -> None:
        self._page._ensure_open()
        if self._page._bridge and self._page._bridge.is_connected and self._page._tab_id is not None:
            await self._page._bridge.send_command(
                "scroll",
                {
                    "tabId": self._page._tab_id,
                    "x": self._x,
                    "y": self._y,
                    "deltaX": delta_x,
                    "deltaY": delta_y,
                },
            )

    async def wheel_smooth(self, delta_y: float) -> None:
        self._page._ensure_open()
        from camoufox.humanize import scroll_sequence

        events = scroll_sequence(delta_y)
        for dy, delay in events:
            if abs(dy) > 0.5:
                await self.wheel(0, dy)
            await asyncio.sleep(delay)


class _Keyboard:
    def __init__(self, page: "_LegacyRDPPage"):
        self._page = page

    async def type(self, text: str, instant: bool = False) -> None:
        self._page._ensure_open()
        if not self._page._bridge or not self._page._bridge.is_connected or self._page._tab_id is None:
            return

        if instant or not text:
            await self._page._bridge.send_command("type", {"tabId": self._page._tab_id, "text": text})
            return

        from camoufox.humanize import typing_sequence
        for ch, delay in typing_sequence(text):
            try:
                await self._page._bridge.send_command("type", {"tabId": self._page._tab_id, "text": ch})
            except Exception:
                break
            await asyncio.sleep(delay)

    async def press(self, key: str) -> None:
        self._page._ensure_open()
        if self._page._bridge and self._page._bridge.is_connected and self._page._tab_id is not None:
            await self._page._bridge.send_command("keyPress", {"tabId": self._page._tab_id, "key": key})


class RDPPage(_LegacyRDPPage):
    """Concrete page class in the new `winfox.rdp.page` namespace.

    Runtime behavior is intentionally inherited for now. This keeps smoke/stress
    stability while letting the codebase move away from `camoufox.rdp_api` as
    the canonical home for page-layer concepts.
    """

    @property
    def url(self) -> str:
        if self._closed:
            return self._url
        try:
            result = self._eval_sync("window.location.href")
            if isinstance(result, str):
                self._url = result
        except Exception:
            pass
        return self._url

    @property
    def url_cached(self) -> str:
        return self._url

    async def url_fresh(self) -> str:
        self._ensure_open()
        try:
            result = await self.evaluate("window.location.href")
            if isinstance(result, str):
                self._url = result
        except Exception:
            pass
        return self._url

    async def title(self) -> str:
        self._ensure_open()
        result = await self.evaluate("document.title")
        return result if isinstance(result, str) else ""

    async def content(self) -> str:
        self._ensure_open()
        return await self.evaluate("document.documentElement.outerHTML") or ""

    async def evaluate(self, expression: str) -> Any:
        self._ensure_open()
        expr = expression.strip()
        auto_called = False
        if (
            expr.startswith("() =>")
            or expr.startswith("async () =>")
            or expr.startswith("function")
        ) and not expr.endswith("()"):
            expr = f"({expr})()"
            auto_called = True

        if auto_called:
            expr = f"(function(){{var v=({expr});return typeof v==='object'&&v!==null?JSON.stringify(v):v}})()"

        if "//# sourceURL=" not in expr:
            expr += "\n//# sourceURL=resource://gre/modules/AppConstants.sys.mjs"

        result = await asyncio.to_thread(self._eval_sync, expr)
        if auto_called and isinstance(result, str):
            try:
                return json.loads(result)
            except (json.JSONDecodeError, ValueError):
                pass
        return result

    async def query_selector(self, selector: str) -> Optional[Dict]:
        self._ensure_open()
        result = await self.evaluate(
            f"(function(){{ var el = document.querySelector('{selector}');if(!el) return null;var r = el.getBoundingClientRect();return JSON.stringify({{x:r.x,y:r.y,w:r.width,h:r.height}}); }})()"
        )
        if result and isinstance(result, str):
            return json.loads(result)
        return None

    async def query_selector_all(self, selector: str) -> List[Dict]:
        self._ensure_open()
        sel_escaped = selector.replace("'", "\\'")
        result = await self.evaluate(
            f"(function(){{ var els = document.querySelectorAll('{sel_escaped}');var out = [];for(var i=0; i<els.length; i++) {{  var r = els[i].getBoundingClientRect();  out.push({{x:r.x,y:r.y,w:r.width,h:r.height,i:i}});}}return JSON.stringify(out); }})()"
        )
        if result and isinstance(result, str):
            return json.loads(result)
        return []

    def locator(self, selector: str) -> "_Locator":
        return _Locator(self, selector)

    def get_by_text(self, text: str, exact: bool = False) -> "_Locator":
        return _Locator(self, "", mode="text", value=text, exact=exact)

    def get_by_placeholder(self, text: str, exact: bool = False) -> "_Locator":
        return _Locator(self, "", mode="placeholder", value=text, exact=exact)

    def get_by_label(self, text: str, exact: bool = False) -> "_Locator":
        return _Locator(self, "", mode="label", value=text, exact=exact)

    def get_by_test_id(self, value: str) -> "_Locator":
        return _Locator(self, "", mode="testid", value=value, exact=True)

    def get_by_role(self, role: str, name: Optional[str] = None, exact: bool = False) -> "_Locator":
        return _Locator(self, "", mode="role", value=role, role_name=name, role_name_exact=exact)

    def first(self, selector: str) -> "_Locator":
        return _Locator(self, selector, index=0)

    def nth(self, selector: str, index: int) -> "_Locator":
        return _Locator(self, selector, index=index)

    def last(self, selector: str) -> "_Locator":
        return _Locator(self, selector, index=-1)

    async def text_content(self, selector: str) -> Optional[str]:
        self._ensure_open()
        return await self.locator(selector).text_content()

    async def inner_text(self, selector: str) -> Optional[str]:
        self._ensure_open()
        selector_escaped = selector.replace("\\", "\\\\").replace("'", "\\'")
        return await self.evaluate(
            f"(function(){{ var el = document.querySelector('{selector_escaped}'); return el ? el.innerText : null; }})()"
        )

    async def inner_html(self, selector: str) -> Optional[str]:
        self._ensure_open()
        selector_escaped = selector.replace("\\", "\\\\").replace("'", "\\'")
        return await self.evaluate(
            f"(function(){{ var el = document.querySelector('{selector_escaped}'); return el ? el.innerHTML : null; }})()"
        )

    async def all_text_contents(self, selector: str) -> List[str]:
        self._ensure_open()
        selector_escaped = selector.replace("\\", "\\\\").replace("'", "\\'")
        result = await self.evaluate(
            f"(function(){{ return JSON.stringify(Array.from(document.querySelectorAll('{selector_escaped}')).map(el => el.textContent || '')); }})()"
        )
        if isinstance(result, str):
            try:
                return json.loads(result)
            except (json.JSONDecodeError, ValueError):
                pass
        return []

    async def all_inner_texts(self, selector: str) -> List[str]:
        self._ensure_open()
        selector_escaped = selector.replace("\\", "\\\\").replace("'", "\\'")
        result = await self.evaluate(
            f"(function(){{ return JSON.stringify(Array.from(document.querySelectorAll('{selector_escaped}')).map(el => el.innerText || '')); }})()"
        )
        if isinstance(result, str):
            try:
                return json.loads(result)
            except (json.JSONDecodeError, ValueError):
                pass
        return []

    async def get_attribute(self, selector: str, name: str) -> Optional[str]:
        self._ensure_open()
        return await self.locator(selector).get_attribute(name)

    async def count(self, selector: str) -> int:
        self._ensure_open()
        return await self.locator(selector).count()

    async def exists(self, selector: str) -> bool:
        self._ensure_open()
        return (await self.count(selector)) > 0

    async def has_selector(self, selector: str) -> bool:
        self._ensure_open()
        return await self.exists(selector)

    async def is_visible(self, selector: str) -> bool:
        self._ensure_open()
        selector_escaped = selector.replace("\\", "\\\\").replace("'", "\\'")
        result = await self.evaluate(
            f"""(function(){{
                var el = document.querySelector('{selector_escaped}');
                if (!el) return false;
                var style = window.getComputedStyle(el);
                if (!style) return false;
                if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
                var r = el.getBoundingClientRect();
                return !!(r.width > 0 && r.height > 0);
            }})()"""
        )
        return bool(result)

    async def is_hidden(self, selector: str) -> bool:
        self._ensure_open()
        return not await self.is_visible(selector)

    async def wait_for_text(self, text: str, timeout: int = 5000) -> str:
        self._ensure_open()
        deadline = time.time() + (timeout / 1000)
        escaped = text.replace("\\", "\\\\").replace("'", "\\'")
        while time.time() < deadline:
            found = await self.evaluate(f"document.body && document.body.innerText.includes('{escaped}')")
            if found:
                return text
            await asyncio.sleep(0.1)
        raise TimeoutError(f"Text {text!r} not found within {timeout}ms")

    async def wait_for_selector_count(self, selector: str, n: int, timeout: int = 5000) -> int:
        self._ensure_open()
        deadline = time.time() + (timeout / 1000)
        while time.time() < deadline:
            count = await self.count(selector)
            if count == n:
                return count
            await asyncio.sleep(0.1)
        raise TimeoutError(f"Selector {selector!r} did not reach count {n} within {timeout}ms")

    async def wait_until_hidden(self, selector: str, timeout: int = 5000) -> None:
        self._ensure_open()
        await self.wait_for_selector(selector, state="hidden", timeout=timeout)

    async def wait_until_visible(self, selector: str, timeout: int = 5000) -> None:
        self._ensure_open()
        await self.wait_for_selector(selector, state="visible", timeout=timeout)

    async def click(self, selector: str) -> None:
        self._ensure_open()
        rect = await self.query_selector(selector)
        if not rect:
            raise ValueError(f"Element not found: {selector}")
        x = rect["x"] + rect["w"] / 2
        y = rect["y"] + rect["h"] / 2
        await self.mouse.click_smooth(x, y, target_width=rect.get("w", 50))

    async def hover(self, selector: str) -> None:
        self._ensure_open()
        rect = await self.query_selector(selector)
        if not rect:
            raise ValueError(f"Element not found: {selector}")
        x = rect["x"] + rect["w"] / 2
        y = rect["y"] + rect["h"] / 2
        await self.mouse.move_smooth(x, y, target_width=rect.get("w", 50))

    async def focus(self, selector: str) -> None:
        self._ensure_open()
        selector_escaped = selector.replace("\\", "\\\\").replace("'", "\\'")
        focused = await self.evaluate(
            f"""(function(){{
                var el = document.querySelector('{selector_escaped}');
                if (!el) return false;
                if (typeof el.scrollIntoView === 'function') el.scrollIntoView({{ block: 'center', inline: 'center' }});
                if (typeof el.focus === 'function') el.focus();
                return document.activeElement === el;
            }})()"""
        )
        if not focused:
            raise ValueError(f"Element not found or focus failed: {selector}")

    async def press(self, selector: str, key: str) -> None:
        self._ensure_open()
        await self.focus(selector)
        await self.keyboard.press(key)

    async def fill(self, selector: str, text: str) -> None:
        self._ensure_open()
        await self.click(selector)
        await asyncio.sleep(0.1)
        selector_escaped = selector.replace("\\", "\\\\").replace("'", "\\'")
        await self.evaluate(
            """
            (function() {
              const el = document.querySelector('%s');
              if (!el) return false;
              if ('value' in el) {
                el.value = '';
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                return true;
              }
              return false;
            })()
            """
            % selector_escaped
        )
        if self._bridge and self._bridge.is_connected and self._tab_id is not None:
            await self._bridge.send_command("type", {"tabId": self._tab_id, "text": text})
        else:
            raise ConnectionError("Extension bridge not connected, cannot fill with trusted events")

    async def set_input_files(self, selector: str, paths) -> int:
        self._ensure_open()
        if isinstance(paths, (str, Path)):
            path_list = [str(paths)]
        else:
            path_list = [str(path) for path in paths]

        if not path_list:
            raise ValueError("set_input_files requires at least one path")

        file_payloads = []
        for path in path_list:
            if not os.path.exists(path):
                raise FileNotFoundError(path)
            with open(path, "rb") as file_handle:
                raw = file_handle.read()
            file_payloads.append(
                {
                    "name": os.path.basename(path),
                    "type": mimetypes.guess_type(path)[0] or "application/octet-stream",
                    "data": base64.b64encode(raw).decode("ascii"),
                }
            )

        selector_escaped = selector.replace("\\", "\\\\").replace("'", "\\'")
        payload_json = json.dumps(file_payloads)
        result = await self.evaluate(
            f"""
            (() => {{
              const input = document.querySelector('{selector_escaped}');
              if (!input) return JSON.stringify({{ ok: false, error: 'not-found' }});
              if (!(input instanceof HTMLInputElement) || input.type !== 'file') {{
                return JSON.stringify({{ ok: false, error: 'not-file-input' }});
              }}
              const payloads = {payload_json};
              if (!input.multiple && payloads.length > 1) {{
                return JSON.stringify({{ ok: false, error: 'multiple-not-supported' }});
              }}
              const transfer = new DataTransfer();
              for (const item of payloads) {{
                const binary = atob(item.data);
                const bytes = new Uint8Array(binary.length);
                for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
                const file = new File([bytes], item.name, {{ type: item.type }});
                transfer.items.add(file);
              }}
              input.files = transfer.files;
              input.dispatchEvent(new Event('input', {{ bubbles: true }}));
              input.dispatchEvent(new Event('change', {{ bubbles: true }}));
              return JSON.stringify({{ ok: true, count: input.files.length }});
            }})()
            """
        )

        if isinstance(result, str):
            try:
                result = json.loads(result)
            except (json.JSONDecodeError, ValueError):
                pass
        if not isinstance(result, dict) or not result.get("ok"):
            error = result.get("error") if isinstance(result, dict) else "unknown"
            raise RuntimeError(f"set_input_files failed: {error}")
        return int(result.get("count", 0))


__all__ = [
    "RDPPage",
    "_Mouse",
    "_Keyboard",
]
