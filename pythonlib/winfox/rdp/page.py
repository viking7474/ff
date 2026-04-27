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
import inspect
import json
import logging
import mimetypes
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from camoufox.humanize import generate_path as _generate_path, hover_delay as _hover_delay
from camoufox.rdp_api import RDPPage as _LegacyRDPPage
from geckordp.actors.events import Events
from geckordp.actors.root import RootActor
from geckordp.actors.screenshot import ScreenshotActor
from geckordp.actors.targets.window_global import WindowGlobalActor
from geckordp.actors.web_console import WebConsoleActor

from .dialog import RDPDialog
from .frame import RDPFrame
from .locator import _Locator

logger = logging.getLogger(__name__)

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

    def _make_event_payload(self, event: str, name: str = "", url: str = "") -> Dict[str, Any]:
        return {
            "event": event,
            "name": name,
            "url": url or self._url,
            "page": self,
            "tabId": self._tab_id,
            "tabActorId": self._tab_actor_id,
            "targetActorId": self._target_actor_id,
            "browsingContextID": self._browsing_context_id,
            "timestamp": int(time.time() * 1000),
        }

    def _emit_event(self, event: str, payload: Any) -> None:
        signature = (
            payload.get("url") if isinstance(payload, dict) else None,
            payload.get("targetActorId") if isinstance(payload, dict) else None,
            payload.get("browsingContextID") if isinstance(payload, dict) else None,
        )
        if self._last_emitted_event.get(event) == signature:
            return
        self._last_emitted_event[event] = signature
        callbacks = list(self._event_listeners.get(event, []))
        for callback in callbacks:
            try:
                result = callback(payload)
                if inspect.isawaitable(result):
                    self._loop.create_task(result)
            except Exception:
                logger.exception("Unhandled RDPPage event callback error for %s", event)

    def _emit_event_threadsafe(self, event: str, payload: Any) -> None:
        if self._closed:
            return
        self._loop.call_soon_threadsafe(self._emit_event, event, payload)

    def _remember_network_event(self, signature: tuple) -> bool:
        if signature in self._seen_network_events:
            return False
        self._seen_network_events.add(signature)
        self._seen_network_event_order.append(signature)
        if len(self._seen_network_event_order) > 1000:
            old = self._seen_network_event_order.pop(0)
            self._seen_network_events.discard(old)
        return True

    def _make_network_event_payload(self, event: str, item: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "event": event,
            "state": item.get("state"),
            "requestId": item.get("requestId"),
            "url": item.get("url", ""),
            "method": item.get("method", "GET"),
            "headers": item.get("headers"),
            "requestBody": item.get("body"),
            "responseHeaders": item.get("responseHeaders"),
            "responseBody": item.get("responseBody"),
            "status": item.get("status"),
            "error": item.get("error"),
            "timestamp": item.get("timestamp"),
            "page": self,
        }

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

    async def get_local_storage(self) -> Dict[str, str]:
        self._ensure_open()
        result = await self.evaluate(
            "JSON.stringify(Object.fromEntries(Object.keys(localStorage).map(k => [k, localStorage.getItem(k)])))"
        )
        if isinstance(result, str):
            try:
                return json.loads(result)
            except (json.JSONDecodeError, ValueError):
                pass
        return {}

    async def set_local_storage(self, data: Dict[str, Any]) -> None:
        self._ensure_open()
        payload = json.dumps({str(k): "" if v is None else str(v) for k, v in data.items()})
        await self.evaluate(
            f"""
            (() => {{
              const data = {payload};
              for (const [k, v] of Object.entries(data)) localStorage.setItem(k, v);
              return true;
            }})()
            """
        )

    async def clear_local_storage(self) -> None:
        self._ensure_open()
        await self.evaluate("localStorage.clear(); true")

    async def get_session_storage(self) -> Dict[str, str]:
        self._ensure_open()
        result = await self.evaluate(
            "JSON.stringify(Object.fromEntries(Object.keys(sessionStorage).map(k => [k, sessionStorage.getItem(k)])))"
        )
        if isinstance(result, str):
            try:
                return json.loads(result)
            except (json.JSONDecodeError, ValueError):
                pass
        return {}

    async def set_session_storage(self, data: Dict[str, Any]) -> None:
        self._ensure_open()
        payload = json.dumps({str(k): "" if v is None else str(v) for k, v in data.items()})
        await self.evaluate(
            f"""
            (() => {{
              const data = {payload};
              for (const [k, v] of Object.entries(data)) sessionStorage.setItem(k, v);
              return true;
            }})()
            """
        )

    async def clear_session_storage(self) -> None:
        self._ensure_open()
        await self.evaluate("sessionStorage.clear(); true")

    async def save_storage_state(self) -> Dict[str, Any]:
        self._ensure_open()
        url = await self.url_fresh()
        from urllib.parse import urlparse

        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
        return {
            "origin": origin,
            "localStorage": await self.get_local_storage(),
            "sessionStorage": await self.get_session_storage(),
        }

    async def load_storage_state(self, state: Dict[str, Any]) -> Dict[str, int]:
        self._ensure_open()
        local_storage = state.get("localStorage", {}) if isinstance(state, dict) else {}
        session_storage = state.get("sessionStorage", {}) if isinstance(state, dict) else {}
        await self.clear_local_storage()
        await self.clear_session_storage()
        if local_storage:
            await self.set_local_storage(local_storage)
        if session_storage:
            await self.set_session_storage(session_storage)
        return {
            "localStorage": len(local_storage),
            "sessionStorage": len(session_storage),
        }

    async def expect_popup(self, timeout: int = 5000) -> "RDPPage":
        self._ensure_open()
        existing_pages = self._browser.list_pages()
        try:
            return await self._browser.wait_for_new_page(timeout=timeout, existing_pages=existing_pages)
        except TimeoutError:
            active = await self._browser.get_active_page()
            if active and active is not self and not active.is_closed():
                return active

            previous_ids = {page._tab_actor_id for page in existing_pages if not page.is_closed()}
            current_pages = self._browser.list_pages()
            for page in current_pages:
                if page is self or page.is_closed():
                    continue
                if page._tab_actor_id not in previous_ids:
                    return page
            raise

    async def _enumerate_frames(self) -> List[Dict[str, Any]]:
        self._ensure_open()
        result = await self.evaluate(
            """
            (() => {
              const out = [];
              const walk = (doc, parentPath) => {
                const frames = Array.from(doc.querySelectorAll('iframe, frame'));
                frames.forEach((frame, index) => {
                  const path = parentPath.concat(index);
                  try {
                    const childDoc = frame.contentWindow.document;
                    out.push({
                      index,
                      path,
                      parent_path: parentPath.length ? parentPath : null,
                      depth: path.length - 1,
                      name: frame.name || null,
                      id: frame.id || null,
                      src: frame.getAttribute('src') || null,
                      url: frame.contentWindow.location.href,
                      same_origin: true,
                    });
                    walk(childDoc, path);
                  } catch (e) {
                    out.push({
                      index,
                      path,
                      parent_path: parentPath.length ? parentPath : null,
                      depth: path.length - 1,
                      name: frame.name || null,
                      id: frame.id || null,
                      src: frame.getAttribute('src') || null,
                      url: null,
                      same_origin: false,
                    });
                  }
                });
              };
              walk(document, []);
              return JSON.stringify(out);
            })()
            """
        )
        if isinstance(result, str):
            try:
                return json.loads(result)
            except (json.JSONDecodeError, ValueError):
                return []
        return []

    async def _frame_eval_body(self, path: List[int], body: str) -> Any:
        self._ensure_open()
        path_json = json.dumps(path)
        result = await self.evaluate(
            f"""
            (() => {{
              const path = {path_json};
              try {{
                let frame = null;
                let win = window;
                let doc = document;
                for (const idx of path) {{
                  frame = doc.querySelectorAll('iframe, frame')[idx];
                  if (!frame) return JSON.stringify({{ ok: false, error: 'frame-not-found' }});
                  win = frame.contentWindow;
                  doc = win.document;
                }}
                const result = (() => {{ {body} }})();
                return JSON.stringify({{ ok: true, value: result }});
              }} catch (e) {{
                return JSON.stringify({{ ok: false, error: 'cross-origin-frame' }});
              }}
            }})()
            """
        )
        if isinstance(result, str):
            try:
                payload = json.loads(result)
            except (json.JSONDecodeError, ValueError):
                payload = None
            if isinstance(payload, dict):
                if not payload.get("ok"):
                    error = payload.get("error", "unknown")
                    if error == "cross-origin-frame":
                        raise RuntimeError("Cross-origin frame access is not supported")
                    raise RuntimeError(f"Frame evaluation failed: {error}")
                return payload.get("value")
        return result

    async def _frame_evaluate(self, path: List[int], expression: str) -> Any:
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
        expr_json = json.dumps(expr)
        path_json = json.dumps(path)
        result = await self.evaluate(
            f"""
            (() => {{
              try {{
                const path = {path_json};
                let frame = null;
                let win = window;
                let doc = document;
                for (const idx of path) {{
                  frame = doc.querySelectorAll('iframe, frame')[idx];
                  if (!frame) return JSON.stringify({{ ok: false, error: 'frame-not-found' }});
                  win = frame.contentWindow;
                  doc = win.document;
                }}
                let value = win.eval({expr_json});
                if ({str(auto_called).lower()} && typeof value === 'object' && value !== null) {{
                  return JSON.stringify({{ ok: true, object: true, value: JSON.stringify(value) }});
                }}
                if (typeof value === 'undefined') {{
                  return JSON.stringify({{ ok: true, value: null, undefined: true }});
                }}
                return JSON.stringify({{ ok: true, object: false, value }});
              }} catch (e) {{
                return JSON.stringify({{ ok: false, error: 'cross-origin-frame' }});
              }}
            }})()
            """
        )
        if isinstance(result, str):
            try:
                payload = json.loads(result)
            except (json.JSONDecodeError, ValueError):
                payload = None
            if isinstance(payload, dict):
                if not payload.get("ok"):
                    error = payload.get("error", "unknown")
                    if error == "cross-origin-frame":
                        raise RuntimeError("Cross-origin frame access is not supported")
                    raise RuntimeError(f"Frame evaluation failed: {error}")
                if payload.get("object") and isinstance(payload.get("value"), str):
                    try:
                        return json.loads(payload["value"])
                    except (json.JSONDecodeError, ValueError):
                        return payload["value"]
                return payload.get("value")
        return result

    async def frames(self) -> List[RDPFrame]:
        self._ensure_open()
        metadata = await self._enumerate_frames()
        return [RDPFrame(self, item) for item in metadata]

    async def child_frames(self, path: Optional[List[int]] = None) -> List[RDPFrame]:
        self._ensure_open()
        parent_path = path if path is not None else None
        frames = await self.frames()
        return [frame for frame in frames if frame.parent_path == parent_path]

    async def frame(
        self,
        index: Optional[int] = None,
        name: Optional[str] = None,
        url_contains: Optional[str] = None,
        path: Optional[List[int]] = None,
    ) -> Optional[RDPFrame]:
        self._ensure_open()
        for frame in await self.frames():
            if index is not None and frame.index != index:
                continue
            if path is not None and frame.path != path:
                continue
            if name is not None and frame.name != name:
                continue
            if url_contains is not None and (not frame.url or url_contains not in frame.url):
                continue
            return frame
        return None

    async def _ensure_dialog_shim(self) -> None:
        if self._dialog_shim_ready:
            return
        await self.evaluate(
            """
            (() => {
              if (window.__rdpDialogState) return true;
              const state = {
                dialogs: [],
                nextId: 1,
                auto: { confirm: true, prompt: '' },
              };
              const pushDialog = (type, message, defaultValue = null) => {
                const id = state.nextId++;
                state.dialogs.push({
                  id,
                  type,
                  message: String(message ?? ''),
                  defaultValue,
                  handled: false,
                  accepted: null,
                  promptText: null,
                  timestamp: Date.now(),
                });
                return id;
              };
              window.__rdpDialogState = state;
              window.alert = function(message) {
                pushDialog('alert', message, null);
                return undefined;
              };
              window.confirm = function(message) {
                pushDialog('confirm', message, null);
                return state.auto.confirm;
              };
              window.prompt = function(message, defaultValue = '') {
                pushDialog('prompt', message, defaultValue == null ? '' : String(defaultValue));
                return state.auto.prompt;
              };
              return true;
            })()
            """
        )
        self._dialog_shim_ready = True

    async def _resolve_dialog(self, dialog_id: int, accepted: bool, prompt_text: Optional[str]) -> Optional[Dict[str, Any]]:
        self._ensure_open()
        await self._ensure_dialog_shim()
        prompt_value = "null" if prompt_text is None else json.dumps(prompt_text)
        result = await self.evaluate(
            f"""
            (() => {{
              const state = window.__rdpDialogState;
              if (!state) return null;
              const dialog = state.dialogs.find(d => d.id === {dialog_id});
              if (!dialog) return null;
              dialog.handled = {str(True).lower()};
              dialog.accepted = {str(accepted).lower()};
              dialog.promptText = {prompt_value};
              if (dialog.type === 'confirm') state.auto.confirm = {str(accepted).lower()};
              if (dialog.type === 'prompt' && {prompt_value} !== null) state.auto.prompt = {prompt_value};
              return JSON.stringify(dialog);
            }})()
            """
        )
        if isinstance(result, str) and result:
            try:
                return json.loads(result)
            except (json.JSONDecodeError, ValueError):
                return None
        return None

    async def expect_dialog(self, timeout: int = 5000) -> RDPDialog:
        self._ensure_open()
        await self._ensure_dialog_shim()
        deadline = time.time() + (timeout / 1000)
        while time.time() < deadline:
            result = await self.evaluate(
                f"""
                (() => {{
                  const state = window.__rdpDialogState;
                  if (!state) return null;
                  const dialog = state.dialogs.find(d => d.id > {self._dialog_last_id});
                  return dialog ? JSON.stringify(dialog) : null;
                }})()
                """
            )
            if isinstance(result, str) and result:
                try:
                    dialog = json.loads(result)
                except (json.JSONDecodeError, ValueError):
                    dialog = None
                if dialog:
                    self._dialog_last_id = max(self._dialog_last_id, dialog.get("id", 0))
                    return RDPDialog(
                        self,
                        dialog_id=dialog.get("id", 0),
                        dialog_type=dialog.get("type", "alert"),
                        message=dialog.get("message", ""),
                        default_value=dialog.get("defaultValue"),
                    )
            await asyncio.sleep(0.1)
        raise TimeoutError(f"Dialog not observed within {timeout}ms")

    async def screenshot(self, path: Optional[str] = None) -> bytes:
        self._ensure_open()
        if self._bridge and self._bridge.is_connected:
            result = await self._bridge.send_command("screenshot", {})
            if result and result.get("dataUrl"):
                b64 = result["dataUrl"].split(",", 1)[1] if "," in result["dataUrl"] else result["dataUrl"]
                data = base64.b64decode(b64)
                if path:
                    with open(path, "wb") as f:
                        f.write(data)
                return data

        def _capture():
            root = RootActor(self._client)
            root_data = root.get_root()
            sa_id = root_data.get("screenshotActor", "")
            if not sa_id:
                return b""
            sa = ScreenshotActor(self._client, sa_id)
            result = sa.capture(self._browsing_context_id or 0)
            b64_data = (
                result.get("value", {}).get("data", "")
                if isinstance(result.get("value"), dict)
                else result.get("value", "")
            )
            if isinstance(b64_data, str) and b64_data:
                b64_data = b64_data.replace("data:image/png;base64,", "")
                return base64.b64decode(b64_data)
            return b""

        data = await asyncio.to_thread(_capture)
        if path and data:
            with open(path, "wb") as f:
                f.write(data)
        return data

    async def _ensure_network_event_bridge(self) -> None:
        if self._network_events_started:
            return
        if not self._bridge or not self._bridge.is_connected:
            raise ConnectionError("Extension bridge not connected")
        await self._bridge.send_command("startSpy", {"patterns": ["http"]}, timeout=10)
        await self._bridge.send_command("startCapture", {"patterns": ["http"]}, timeout=10)
        self._request_event_ts = int(time.time() * 1000)
        self._spy_event_ts = self._request_event_ts
        self._network_events_started = True
        self._network_event_task = self._loop.create_task(self._network_event_poller())

    async def _network_event_poller(self) -> None:
        try:
            while not self._closed:
                if not self._bridge or not self._bridge.is_connected:
                    await asyncio.sleep(0.2)
                    continue

                request_result = await self._bridge.send_command("getRequestEvents", {"since": self._request_event_ts}, timeout=5)
                requests = request_result.get("requests", []) if request_result else []
                for req in requests:
                    self._request_event_ts = max(self._request_event_ts, req.get("timestamp", 0))
                    signature = (req.get("requestId"), "request", req.get("timestamp", 0))
                    if not self._remember_network_event(signature):
                        continue
                    payload = self._make_network_event_payload("request", req)
                    payload["state"] = payload["state"] or "request"
                    self._emit_event("request", payload)

                spy_result = await self._bridge.send_command("getSpiedRequests", {"since": self._spy_event_ts}, timeout=5)
                network_events = spy_result.get("requests", []) if spy_result else []
                for item in network_events:
                    self._spy_event_ts = max(self._spy_event_ts, item.get("timestamp", 0))
                    state = item.get("state")
                    signature = (item.get("requestId"), state, item.get("timestamp", 0))
                    if not self._remember_network_event(signature):
                        continue
                    response_payload = self._make_network_event_payload("response", item)
                    if state == "failed":
                        self._emit_event("requestfailed", {**response_payload, "event": "requestfailed", "error": item.get("error")})
                        continue
                    self._emit_event("response", response_payload)
                    self._emit_event("requestfinished", {**response_payload, "event": "requestfinished", "state": "finished"})

                await asyncio.sleep(0.2)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("RDPBrowser network event poller failed")

    def on(self, event: str, callback) -> None:
        self._ensure_open()
        self._event_listeners.setdefault(event, []).append(callback)
        if event in {"request", "response", "requestfinished", "requestfailed"}:
            self._loop.create_task(self._ensure_network_event_bridge())
        logger.debug("Event listener registered: %s", event)

    def remove_listener(self, event: str, callback) -> None:
        self._ensure_open()
        if event in self._event_listeners:
            try:
                self._event_listeners[event].remove(callback)
                if not self._event_listeners[event]:
                    self._event_listeners.pop(event, None)
            except ValueError:
                pass

    async def goto(self, url: str, wait_until: str = "load", timeout: int = 30000) -> None:
        self._ensure_open()
        async with self._nav_lock:
            await self._goto_impl(url, wait_until=wait_until, timeout=timeout)

    async def _goto_impl(self, url: str, wait_until: str = "load", timeout: int = 30000) -> None:
        loop = asyncio.get_running_loop()
        load_done = asyncio.Event()
        deadline = time.time() + (timeout / 1000)
        console_listeners: list = []

        goal = "dom-complete" if wait_until in ("load", "networkidle") else "dom-interactive"

        def _on_doc_event(data):
            logger.debug(f"goto DOCUMENT_EVENT: {data}")
            name = data.get("name", "")
            evt_url = data.get("url", "")
            if evt_url:
                self._url = evt_url
            payload = {"name": name, "url": evt_url, "page": self}
            if name == "dom-interactive":
                self._emit_event_threadsafe("domcontentloaded", payload)
            if name == "dom-complete":
                self._emit_event_threadsafe("load", payload)
            if name == goal or name == "dom-complete":
                loop.call_soon_threadsafe(load_done.set)

        def _attach_console_listener(console_id):
            WebConsoleActor(self._client, console_id).start_listeners([WebConsoleActor.Listeners.DOCUMENT_EVENTS])
            self._client.add_event_listener(console_id, Events.WebConsole.DOCUMENT_EVENT, _on_doc_event)
            console_listeners.append(console_id)

        await asyncio.to_thread(lambda: _attach_console_listener(self._console_actor_id))
        self._console_started = True

        try:
            ver_before = self._target_ver
            navigated = False
            if self._bridge and self._bridge.is_connected and self._tab_id is not None:
                try:
                    await self._bridge.send_command("navigate", {"tabId": self._tab_id, "url": url})
                    navigated = True
                except Exception:
                    pass

            if not navigated:
                await asyncio.to_thread(
                    lambda: self._client.send_receive(
                        {
                            "to": self._tab_actor_id,
                            "type": "navigateTo",
                            "url": url,
                            "waitForLoad": False,
                        }
                    )
                )
            self._url = url
            self._console_started = False

            last_target_ver = ver_before
            nav_started = False

            async with self._with_idle_mouse():
                while time.time() < deadline:
                    if load_done.is_set():
                        return

                    if self._target_ver > last_target_ver:
                        last_target_ver = self._target_ver
                        nav_started = True
                        await asyncio.to_thread(lambda: _attach_console_listener(self._console_actor_id))
                        self._console_started = True

                        if load_done.is_set():
                            return
                        try:
                            state = await self.evaluate("document.readyState")
                            if state == "complete" or (goal == "dom-interactive" and state in ("interactive", "complete")):
                                return
                        except Exception:
                            pass
                        continue

                    remaining = max(0.1, deadline - time.time())
                    try:
                        await asyncio.wait_for(load_done.wait(), timeout=min(1.0, remaining))
                        return
                    except asyncio.TimeoutError:
                        try:
                            state = await self.evaluate("document.readyState")
                            if state in ("loading", "interactive"):
                                nav_started = True
                            if nav_started and (state == "complete" or (goal == "dom-interactive" and state in ("interactive", "complete"))):
                                return
                        except Exception:
                            nav_started = True
        finally:
            for cid in console_listeners:
                try:
                    self._client.remove_event_listener(cid, Events.WebConsole.DOCUMENT_EVENT, _on_doc_event)
                except Exception:
                    pass

        try:
            import random as _r

            await self.mouse._raw_move(self.mouse._x, self.mouse._y)
            drift_x = self.mouse._x + _r.uniform(-80, 80)
            drift_y = self.mouse._y + _r.uniform(-60, 60)
            drift_x = max(50, min(drift_x, 1800))
            drift_y = max(50, min(drift_y, 900))
            await self.mouse.move_smooth(drift_x, drift_y)
        except Exception:
            pass

    async def _wait_for_doc_event(self, goal: str = "dom-complete", timeout_s: float = 30.0) -> None:
        self._ensure_open()
        loop = asyncio.get_running_loop()
        done = asyncio.Event()
        console_id = self._console_actor_id

        def _on_evt(data):
            name = data.get("name", "")
            evt_url = data.get("url", "")
            if evt_url:
                self._url = evt_url
            payload = self._make_event_payload(
                "domcontentloaded" if name == "dom-interactive" else "load",
                name=name,
                url=evt_url,
            )
            if name == "dom-interactive":
                self._emit_event_threadsafe("domcontentloaded", payload)
            if name == "dom-complete":
                self._emit_event_threadsafe("load", payload)
            if name == goal or name == "dom-complete":
                loop.call_soon_threadsafe(done.set)

        await asyncio.to_thread(lambda: WebConsoleActor(self._client, console_id).start_listeners([WebConsoleActor.Listeners.DOCUMENT_EVENTS]))
        self._console_started = True
        self._client.add_event_listener(console_id, Events.WebConsole.DOCUMENT_EVENT, _on_evt)
        try:
            async with self._with_idle_mouse():
                await asyncio.wait_for(done.wait(), timeout=timeout_s)
        except asyncio.TimeoutError:
            pass
        finally:
            try:
                self._client.remove_event_listener(console_id, Events.WebConsole.DOCUMENT_EVENT, _on_evt)
            except Exception:
                pass

    async def reload(self, timeout: int = 30000) -> None:
        self._ensure_open()
        async with self._nav_lock:
            await self._reload_impl(timeout=timeout)

    async def _reload_impl(self, timeout: int = 30000) -> None:
        loop = asyncio.get_running_loop()
        goal = "dom-complete"
        timeout_s = timeout / 1000
        done = asyncio.Event()
        console_id = self._console_actor_id

        def _on_evt(data):
            name = data.get("name", "")
            evt_url = data.get("url", "")
            if evt_url:
                self._url = evt_url
            payload = self._make_event_payload(
                "domcontentloaded" if name == "dom-interactive" else "load",
                name=name,
                url=evt_url,
            )
            if name == "dom-interactive":
                self._emit_event_threadsafe("domcontentloaded", payload)
            if name == "dom-complete":
                self._emit_event_threadsafe("load", payload)
            if name == goal or name == "dom-complete":
                loop.call_soon_threadsafe(done.set)

        await asyncio.to_thread(lambda: WebConsoleActor(self._client, console_id).start_listeners([WebConsoleActor.Listeners.DOCUMENT_EVENTS]))
        self._console_started = True
        self._client.add_event_listener(console_id, Events.WebConsole.DOCUMENT_EVENT, _on_evt)

        try:
            await asyncio.to_thread(lambda: WindowGlobalActor(self._client, self._target_actor_id).reload())
            self._console_started = False
            async with self._with_idle_mouse():
                await asyncio.wait_for(done.wait(), timeout=timeout_s)
        except asyncio.TimeoutError:
            pass
        finally:
            try:
                self._client.remove_event_listener(console_id, Events.WebConsole.DOCUMENT_EVENT, _on_evt)
            except Exception:
                pass

    async def wait_for_load_state(self, state: str = "load", timeout: int = 30000) -> None:
        self._ensure_open()
        async with self._nav_lock:
            await self._wait_for_load_state_impl(state=state, timeout=timeout)

    async def _wait_for_load_state_impl(self, state: str = "load", timeout: int = 30000) -> None:
        target = "complete" if state in ("load", "networkidle") else "interactive"
        try:
            current = await self.evaluate("document.readyState")
            if current == target or current == "complete":
                return
        except Exception:
            pass
        goal = "dom-complete" if state in ("load", "networkidle") else "dom-interactive"
        await self._wait_for_doc_event(goal=goal, timeout_s=timeout / 1000)

    async def start_capture(self, patterns: list) -> None:
        self._ensure_open()
        if not self._bridge or not self._bridge.is_connected:
            raise ConnectionError("Extension bridge not connected")
        await self._bridge.send_command("startCapture", {"patterns": patterns})
        self._capture_ts = int(time.time() * 1000)
        logger.info(f"Network capture started for patterns: {patterns}")

    async def stop_capture(self) -> None:
        self._ensure_open()
        if self._bridge and self._bridge.is_connected:
            await self._bridge.send_command("stopCapture", {})

    async def get_captured_responses(self, clear: bool = True) -> list:
        self._ensure_open()
        if not self._bridge or not self._bridge.is_connected:
            return []
        since = getattr(self, "_capture_ts", 0)
        result = await self._bridge.send_command("getCapturedResponses", {"since": since})
        responses = result.get("responses", []) if result else []
        if clear and responses:
            await self._bridge.send_command("clearCaptures", {})
        return responses

    async def wait_for_response(self, url_pattern: str, timeout: float = 30.0) -> Optional[dict]:
        self._ensure_open()
        deadline = time.time() + timeout
        since = getattr(self, "_capture_ts", 0)
        while time.time() < deadline:
            if self._bridge and self._bridge.is_connected:
                result = await self._bridge.send_command("getCapturedResponses", {"since": since})
                responses = result.get("responses", []) if result else []
                for r in responses:
                    if url_pattern in r.get("url", ""):
                        return r
            await asyncio.sleep(0.5)
        return None

    async def start_spy(self, patterns: list) -> None:
        self._ensure_open()
        if not self._bridge or not self._bridge.is_connected:
            raise ConnectionError("Extension bridge not connected")
        await self._bridge.send_command("startSpy", {"patterns": patterns})
        self._spy_ts = int(time.time() * 1000)
        logger.info(f"Request spy started for patterns: {patterns}")

    async def stop_spy(self) -> None:
        self._ensure_open()
        if self._bridge and self._bridge.is_connected:
            await self._bridge.send_command("stopSpy", {})

    async def get_spied_requests(self, clear: bool = False) -> list:
        self._ensure_open()
        if not self._bridge or not self._bridge.is_connected:
            return []
        since = getattr(self, "_spy_ts", 0)
        result = await self._bridge.send_command("getSpiedRequests", {"since": since})
        requests = result.get("requests", []) if result else []
        if clear and requests:
            await self._bridge.send_command("clearSpied", {})
        return requests

    async def _apply_interception_rules(self) -> Dict[str, Any]:
        self._ensure_open()
        if not self._bridge or not self._bridge.is_connected:
            raise ConnectionError("Extension bridge not connected")
        return await self._bridge.send_command(
            "setInterception",
            {
                "blockPatterns": list(self._interception_block_patterns),
                "headerRules": list(self._interception_header_rules),
                "fulfillRules": list(self._interception_fulfill_rules),
            },
            timeout=10,
        )

    async def set_request_block_patterns(self, patterns: List[str]) -> Dict[str, Any]:
        self._ensure_open()
        self._interception_block_patterns = list(patterns)
        return await self._apply_interception_rules()

    async def set_extra_http_headers(self, headers: Dict[str, Any], patterns: Optional[List[str]] = None) -> Dict[str, Any]:
        self._ensure_open()
        self._interception_header_rules = [{"patterns": patterns or ["http"], "headers": {str(k): str(v) for k, v in headers.items()}}]
        return await self._apply_interception_rules()

    async def clear_interception(self) -> Dict[str, Any]:
        self._ensure_open()
        self._interception_block_patterns = []
        self._interception_header_rules = []
        self._interception_fulfill_rules = []
        if not self._bridge or not self._bridge.is_connected:
            raise ConnectionError("Extension bridge not connected")
        return await self._bridge.send_command("clearInterception", {}, timeout=10)

    async def bg_fetch(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, Any]] = None,
        max_body: int = 100000,
    ) -> Dict[str, Any]:
        self._ensure_open()
        if not self._bridge or not self._bridge.is_connected:
            raise ConnectionError("Extension bridge not connected")
        result = await self._bridge.send_command(
            "bgFetch",
            {
                "url": url,
                "method": method,
                "headers": headers or {},
                "maxBody": max_body,
            },
            timeout=20,
        )
        return result or {}

    async def fulfill_text(self, patterns: List[str], body: str, content_type: str = "text/plain") -> Dict[str, Any]:
        self._ensure_open()
        self._interception_fulfill_rules = [{"patterns": list(patterns), "body": str(body), "contentType": str(content_type)}]
        return await self._apply_interception_rules()

    async def fulfill_json(self, patterns: List[str], data: Any) -> Dict[str, Any]:
        self._ensure_open()
        return await self.fulfill_text(patterns, json.dumps(data), content_type="application/json")

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
