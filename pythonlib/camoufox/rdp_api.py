"""
RDPBrowser: Camoufox automation via Firefox RDP + WebExtension.
Zero-detection-surface alternative to Playwright/Juggler.

Usage:
    from camoufox.rdp_api import RDPBrowser

    async with RDPBrowser() as browser:
        page = await browser.new_page()
        await page.goto("https://example.com")
        html = await page.content()
        await page.click("#button")
        await page.fill("#input", "text")
        await page.mouse.wheel(0, 500)
        await page.screenshot("shot.png")
"""

import asyncio
import base64
import ctypes
import inspect
import json
import logging
import mimetypes
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from concurrent.futures import Future
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse


# Windows Job Object for killing process trees
_kernel32 = ctypes.windll.kernel32 if os.name == "nt" else None


def _create_job_object():
    """Create a Windows Job Object that kills all children when closed."""
    if not _kernel32:
        return None
    import ctypes.wintypes as wt

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wt.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wt.DWORD),
            ("Affinity", ctypes.POINTER(ctypes.c_ulong)),
            ("PriorityClass", wt.DWORD),
            ("SchedulingClass", wt.DWORD),
        ]

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    job = _kernel32.CreateJobObjectW(None, None)
    if not job:
        return None
    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
    if not _kernel32.SetInformationJobObject(
        job, 9, ctypes.byref(info), ctypes.sizeof(info)
    ):
        _kernel32.CloseHandle(job)
        return None
    return job


from geckordp.actors.addon.addons import AddonsActor
from geckordp.actors.descriptors.tab import TabActor
from geckordp.actors.events import Events
from geckordp.actors.memory import MemoryActor
from geckordp.actors.resources import Resources
from geckordp.actors.root import RootActor
from geckordp.actors.screenshot import ScreenshotActor
from geckordp.actors.string import StringActor
from geckordp.actors.targets.window_global import WindowGlobalActor
from geckordp.actors.watcher import WatcherActor
from geckordp.actors.web_console import WebConsoleActor
from geckordp.rdp_client import RDPClient

logger = logging.getLogger(__name__)
logging.getLogger("geckordp").setLevel(logging.CRITICAL)

EXTENSION_DIR = str(Path(__file__).parent / "extension")
DEFAULT_RDP_PORT = 6000
DEFAULT_WS_PORT = 8775


def _get_default_binary() -> str:
    try:
        from .pkgman import launch_path

        return str(launch_path())
    except Exception:
        return ""


def _write_user_prefs(profile_dir: str, prefs: Dict[str, Any]) -> None:
    user_js = os.path.join(profile_dir, "user.js")
    with open(user_js, "a", encoding="utf-8") as f:
        for key, value in prefs.items():
            if isinstance(value, bool):
                val_str = "true" if value else "false"
            elif isinstance(value, str):
                val_str = f'"{value}"'
            else:
                val_str = str(value)
            f.write(f'user_pref("{key}", {val_str});\n')


def _check_port(host: str, port: int) -> bool:
    """Synchronous TCP port check (Windows-compatible)."""
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1.0)
    try:
        sock.connect((host, port))
        sock.close()
        return True
    except (ConnectionRefusedError, OSError, socket.timeout):
        return False


async def _wait_for_port(host: str, port: int, timeout: float = 60.0) -> None:
    """Wait for a TCP port to accept connections. Uses sync socket in thread for Windows compatibility."""
    deadline = time.time() + timeout
    delay = 0.2
    while time.time() < deadline:
        is_open = await asyncio.to_thread(_check_port, host, port)
        if is_open:
            return
        await asyncio.sleep(delay)
        delay = min(delay * 1.5, 2.0)
    raise TimeoutError(f"Port {port} not ready within {timeout}s")


class _ExtensionBridge:
    def __init__(self, port: int):
        self._port = port
        self._server = None
        self._ws = None
        self._pending: Dict[str, asyncio.Future] = {}
        self._connected = asyncio.Event()

    async def start(self):
        try:
            import websockets

            self._server = await websockets.serve(
                self._handler, "127.0.0.1", self._port
            )
            logger.info(f"Extension bridge listening on ws://127.0.0.1:{self._port}")
        except ImportError:
            logger.warning("websockets not installed, extension input unavailable")

    async def _handler(self, ws):
        self._ws = ws
        self._connected.set()
        logger.info("Extension connected")
        try:
            async for raw in ws:
                data = json.loads(raw)
                if data.get("type") == "hello":
                    logger.info(f"Extension hello: {data.get('extensionId')}")
                    continue
                msg_id = data.get("id")
                if msg_id and msg_id in self._pending:
                    self._pending[msg_id].set_result(data)
        except Exception:
            pass
        finally:
            for fut in list(self._pending.values()):
                if not fut.done():
                    fut.set_exception(ConnectionError("Extension bridge disconnected"))
            self._pending.clear()
            self._ws = None
            self._connected.clear()

    async def send_command(self, cmd: str, params: dict, timeout: float = 10.0) -> Any:
        if not self._ws:
            if not self._connected.is_set():
                try:
                    await asyncio.wait_for(self._connected.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    raise ConnectionError("Extension not connected")

        msg_id = str(uuid.uuid4())[:8]
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = fut

        await self._ws.send(json.dumps({"id": msg_id, "cmd": cmd, "params": params}))

        try:
            result = await asyncio.wait_for(fut, timeout=timeout)
        finally:
            self._pending.pop(msg_id, None)

        if result.get("error"):
            raise RuntimeError(f"Extension error: {result['error']}")
        return result.get("result")

    async def stop(self):
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        for fut in list(self._pending.values()):
            if not fut.done():
                fut.set_exception(ConnectionError("Extension bridge stopped"))
        self._pending.clear()
        self._connected.clear()
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    @property
    def is_connected(self) -> bool:
        return self._ws is not None


class RDPDialog:
    def __init__(
        self,
        page: "RDPPage",
        dialog_id: int,
        dialog_type: str,
        message: str,
        default_value: Optional[str] = None,
    ):
        self._page = page
        self._id = dialog_id
        self.type = dialog_type
        self.message = message
        self.default_value = default_value
        self.handled = False
        self.accepted: Optional[bool] = None
        self.prompt_text: Optional[str] = None

    def _update_from_state(self, state: Dict[str, Any]) -> None:
        self.handled = bool(state.get("handled", self.handled))
        self.accepted = state.get("accepted", self.accepted)
        self.prompt_text = state.get("promptText", self.prompt_text)

    async def accept(self, prompt_text: Optional[str] = None) -> None:
        if self.handled:
            return
        state = await self._page._resolve_dialog(self._id, accepted=True, prompt_text=prompt_text)
        if isinstance(state, dict):
            self._update_from_state(state)
        else:
            self.handled = True
            self.accepted = True
            self.prompt_text = prompt_text

    async def dismiss(self) -> None:
        if self.handled:
            return
        state = await self._page._resolve_dialog(self._id, accepted=False, prompt_text=None)
        if isinstance(state, dict):
            self._update_from_state(state)
        else:
            self.handled = True
            self.accepted = False
            self.prompt_text = None


class RDPFrame:
    def __init__(self, page: "RDPPage", metadata: Dict[str, Any]):
        self._page = page
        self.index = metadata.get("index", 0)
        self.name = metadata.get("name")
        self.id = metadata.get("id")
        self.src = metadata.get("src")
        self.url = metadata.get("url")
        self.same_origin = bool(metadata.get("same_origin"))

    def _ensure_same_origin(self) -> None:
        if not self.same_origin:
            raise RuntimeError("Cross-origin frame access is not supported")

    async def _frame_position(self) -> Dict[str, Any]:
        self._ensure_same_origin()
        result = await self._page.evaluate(
            f"""
            (() => {{
              const frame = document.querySelectorAll('iframe, frame')[{self.index}];
              if (!frame) return JSON.stringify({{ ok: false, error: 'frame-not-found' }});
              const r = frame.getBoundingClientRect();
              return JSON.stringify({{ ok: true, x: r.x, y: r.y, w: r.width, h: r.height }});
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
                    raise RuntimeError(f"Frame position lookup failed: {payload.get('error', 'unknown')}")
                return payload
        raise RuntimeError("Frame position lookup failed")

    async def _target_point(self, selector: str) -> Dict[str, float]:
        self._ensure_same_origin()
        selector_escaped = selector.replace("\\", "\\\\").replace("'", "\\'")
        element_rect = await self._page._frame_eval_body(
            self.index,
            f"""
            const el = doc.querySelector('{selector_escaped}');
            if (!el) return null;
            const r = el.getBoundingClientRect();
            if (r.width === 0 && r.height === 0) return null;
            return JSON.stringify({{x:r.x,y:r.y,w:r.width,h:r.height}});
            """,
        )
        if not element_rect:
            raise ValueError(f"Element not found: {selector}")
        if isinstance(element_rect, str):
            try:
                element_rect = json.loads(element_rect)
            except (json.JSONDecodeError, ValueError):
                raise RuntimeError("Frame element geometry decode failed")
        frame_rect = await self._frame_position()
        return {
            "x": frame_rect["x"] + element_rect["x"] + element_rect["w"] / 2,
            "y": frame_rect["y"] + element_rect["y"] + element_rect["h"] / 2,
            "w": element_rect["w"],
        }

    async def evaluate(self, expression: str) -> Any:
        self._ensure_same_origin()
        return await self._page._frame_evaluate(self.index, expression)

    async def wait_for_text(self, text: str, timeout: int = 5000) -> str:
        self._ensure_same_origin()
        deadline = time.time() + (timeout / 1000)
        text_escaped = text.replace("\\", "\\\\").replace("'", "\\'")
        while time.time() < deadline:
            found = await self._page._frame_eval_body(
                self.index,
                f"return !!(doc.body && doc.body.innerText.includes('{text_escaped}'));",
            )
            if found:
                return text
            await asyncio.sleep(0.1)
        raise TimeoutError(f"Text {text!r} not found within {timeout}ms")

    async def query_selector(self, selector: str) -> Optional[Dict[str, Any]]:
        self._ensure_same_origin()
        selector_escaped = selector.replace("\\", "\\\\").replace("'", "\\'")
        result = await self._page._frame_eval_body(
            self.index,
            f"""
            const el = doc.querySelector('{selector_escaped}');
            if (!el) return null;
            const r = el.getBoundingClientRect();
            return JSON.stringify({{x:r.x,y:r.y,w:r.width,h:r.height}});
            """,
        )
        if isinstance(result, str):
            try:
                return json.loads(result)
            except (json.JSONDecodeError, ValueError):
                return None
        return result

    async def text_content(self, selector: str) -> Optional[str]:
        self._ensure_same_origin()
        selector_escaped = selector.replace("\\", "\\\\").replace("'", "\\'")
        return await self._page._frame_eval_body(
            self.index,
            f"""
            const el = doc.querySelector('{selector_escaped}');
            return el ? el.textContent : null;
            """,
        )

    async def inner_text(self, selector: str) -> Optional[str]:
        self._ensure_same_origin()
        selector_escaped = selector.replace("\\", "\\\\").replace("'", "\\'")
        return await self._page._frame_eval_body(
            self.index,
            f"""
            const el = doc.querySelector('{selector_escaped}');
            return el ? el.innerText : null;
            """,
        )

    async def inner_html(self, selector: str) -> Optional[str]:
        self._ensure_same_origin()
        selector_escaped = selector.replace("\\", "\\\\").replace("'", "\\'")
        return await self._page._frame_eval_body(
            self.index,
            f"""
            const el = doc.querySelector('{selector_escaped}');
            return el ? el.innerHTML : null;
            """,
        )

    async def get_attribute(self, selector: str, name: str) -> Optional[str]:
        self._ensure_same_origin()
        selector_escaped = selector.replace("\\", "\\\\").replace("'", "\\'")
        name_escaped = name.replace("\\", "\\\\").replace("'", "\\'")
        return await self._page._frame_eval_body(
            self.index,
            f"""
            const el = doc.querySelector('{selector_escaped}');
            return el ? el.getAttribute('{name_escaped}') : null;
            """,
        )

    async def count(self, selector: str) -> int:
        self._ensure_same_origin()
        selector_escaped = selector.replace("\\", "\\\\").replace("'", "\\'")
        result = await self._page._frame_eval_body(
            self.index,
            f"return doc.querySelectorAll('{selector_escaped}').length;",
        )
        try:
            return int(result)
        except Exception:
            return 0

    async def exists(self, selector: str) -> bool:
        self._ensure_same_origin()
        return (await self.count(selector)) > 0

    async def is_visible(self, selector: str) -> bool:
        self._ensure_same_origin()
        selector_escaped = selector.replace("\\", "\\\\").replace("'", "\\'")
        result = await self._page._frame_eval_body(
            self.index,
            f"""
            const el = doc.querySelector('{selector_escaped}');
            if (!el) return false;
            const style = win.getComputedStyle(el);
            if (!style) return false;
            if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
            const r = el.getBoundingClientRect();
            return !!(r.width > 0 && r.height > 0);
            """,
        )
        return bool(result)

    async def is_hidden(self, selector: str) -> bool:
        self._ensure_same_origin()
        return not await self.is_visible(selector)

    async def wait_for_selector(
        self, selector: str, timeout: int = 5000, state: str = "visible"
    ) -> Optional[Dict[str, Any]]:
        self._ensure_same_origin()
        selector_escaped = selector.replace("\\", "\\\\").replace("'", "\\'")
        deadline = time.time() + (timeout / 1000)
        while time.time() < deadline:
            result = await self._page._frame_eval_body(
                self.index,
                f"""
                const el = doc.querySelector('{selector_escaped}');
                if ({json.dumps(state)} === 'hidden') {{
                  return !el ? 'ok' : null;
                }}
                if (!el) return null;
                const r = el.getBoundingClientRect();
                if ({json.dumps(state)} === 'visible' && r.width === 0 && r.height === 0) return null;
                return JSON.stringify({{x:r.x,y:r.y,w:r.width,h:r.height}});
                """,
            )
            if result == "ok":
                return {}
            if isinstance(result, str) and result:
                try:
                    return json.loads(result)
                except (json.JSONDecodeError, ValueError):
                    return {"raw": result}
            await asyncio.sleep(0.1)
        return None

    async def hover(self, selector: str) -> None:
        point = await self._target_point(selector)
        await self._page.mouse.move_smooth(point["x"], point["y"], target_width=point.get("w", 50))

    async def click(self, selector: str) -> None:
        point = await self._target_point(selector)
        await self._page.mouse.click_smooth(point["x"], point["y"], target_width=point.get("w", 50))

    async def focus(self, selector: str) -> None:
        self._ensure_same_origin()
        selector_escaped = selector.replace("\\", "\\\\").replace("'", "\\'")
        exists = await self._page._frame_eval_body(
            self.index,
            f"""
            const el = doc.querySelector('{selector_escaped}');
            if (!el) return false;
            if (typeof el.scrollIntoView === 'function') el.scrollIntoView({{ block: 'center', inline: 'center' }});
            if (typeof el.focus === 'function') el.focus();
            return true;
            """,
        )
        if exists:
            return
        raise ValueError(f"Element not found or focus failed: {selector}")

    async def press(self, selector: str, key: str) -> None:
        selector_escaped = selector.replace("\\", "\\\\").replace("'", "\\'")
        if len(key) == 1:
            key_escaped = key.replace("\\", "\\\\").replace("'", "\\'")
            appended = await self._page._frame_eval_body(
                self.index,
                f"""
                const el = doc.querySelector('{selector_escaped}');
                if (!el) return null;
                if (typeof el.scrollIntoView === 'function') el.scrollIntoView({{ block: 'center', inline: 'center' }});
                if (typeof el.focus === 'function') el.focus();
                if ('value' in el) {{
                  el.value = (el.value || '') + '{key_escaped}';
                  el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                  el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                  return true;
                }}
                return false;
                """,
            )
            if appended is None:
                raise ValueError(f"Element not found: {selector}")
            if appended:
                return
        await self.focus(selector)
        await self._page.keyboard.press(key)

    def locator(self, selector: str) -> "_FrameLocator":
        return _FrameLocator(self, selector)


class RDPPage:
    """Page handle with Playwright-like API over Firefox RDP."""

    def __init__(
        self,
        browser: "RDPBrowser",
        client: RDPClient,
        tab_actor_id: str,
        target_actor_id: str,
        console_actor_id: str,
        browsing_context_id: Optional[int] = None,
        bridge: Optional[_ExtensionBridge] = None,
        tab_id: Optional[int] = None,
    ):
        self._browser = browser
        self._client = client
        self._loop = asyncio.get_running_loop()
        self._tab_actor_id = tab_actor_id
        self._target_actor_id = target_actor_id
        self._console_actor_id = console_actor_id
        self._browsing_context_id = browsing_context_id
        self._bridge = bridge
        self._tab_id = tab_id
        self._url = ""
        self._console_started = False
        self._target_ver = 0
        self._watcher_id = None
        self._persistent_target_cb = None
        self._persistent_console_cb = None
        self._persistent_console_id = None
        self._event_listeners: Dict[str, List[Any]] = {}
        self._closed = False
        self._nav_lock = asyncio.Lock()
        self._last_emitted_event: Dict[str, tuple] = {}
        self._network_events_started = False
        self._network_event_task: Optional[asyncio.Task] = None
        self._request_event_ts = 0
        self._spy_event_ts = 0
        self._seen_network_events: set[tuple] = set()
        self._seen_network_event_order: List[tuple] = []
        self._dialog_shim_ready = False
        self._dialog_last_id = 0
        self._interception_block_patterns: List[str] = []
        self._interception_header_rules: List[Dict[str, Any]] = []
        self.mouse = _Mouse(self)
        self.keyboard = _Keyboard(self)

    def is_closed(self) -> bool:
        return self._closed

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("Page is closed")

    async def _ensure_bridge_ready(self, timeout: float = 10.0) -> bool:
        return await self._browser._ensure_bridge_connected(timeout=timeout)

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
              dialog.handled = true;
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

                request_result = await self._bridge.send_command(
                    "getRequestEvents", {"since": self._request_event_ts}, timeout=5
                )
                requests = request_result.get("requests", []) if request_result else []
                for req in requests:
                    self._request_event_ts = max(self._request_event_ts, req.get("timestamp", 0))
                    signature = (req.get("requestId"), "request", req.get("timestamp", 0))
                    if not self._remember_network_event(signature):
                        continue
                    payload = self._make_network_event_payload("request", req)
                    payload["state"] = payload["state"] or "request"
                    self._emit_event("request", payload)

                spy_result = await self._bridge.send_command(
                    "getSpiedRequests", {"since": self._spy_event_ts}, timeout=5
                )
                network_events = spy_result.get("requests", []) if spy_result else []
                for item in network_events:
                    self._spy_event_ts = max(self._spy_event_ts, item.get("timestamp", 0))
                    state = item.get("state")
                    signature = (item.get("requestId"), state, item.get("timestamp", 0))
                    if not self._remember_network_event(signature):
                        continue
                    response_payload = self._make_network_event_payload("response", item)
                    if state == "failed":
                        self._emit_event(
                            "requestfailed",
                            {
                                **response_payload,
                                "event": "requestfailed",
                                "error": item.get("error"),
                            },
                        )
                        continue
                    self._emit_event("response", response_payload)
                    self._emit_event(
                        "requestfinished",
                        {
                            **response_payload,
                            "event": "requestfinished",
                            "state": "finished",
                        },
                    )

                await asyncio.sleep(0.2)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("RDPBrowser network event poller failed")

    def _detach_persistent_console_listener(self) -> None:
        if self._persistent_console_id and self._persistent_console_cb:
            try:
                self._client.remove_event_listener(
                    self._persistent_console_id,
                    Events.WebConsole.DOCUMENT_EVENT,
                    self._persistent_console_cb,
                )
            except Exception:
                pass
        self._persistent_console_id = None
        self._persistent_console_cb = None

    def _attach_persistent_console_listener(self, console_id: str) -> None:
        if not console_id or self._closed:
            return
        if self._persistent_console_id == console_id and self._persistent_console_cb:
            return

        self._detach_persistent_console_listener()
        WebConsoleActor(self._client, console_id).start_listeners(
            [WebConsoleActor.Listeners.DOCUMENT_EVENTS]
        )

        def _on_doc_event(data):
            evt_url = data.get("url", "")
            if evt_url:
                self._url = evt_url
            name = data.get("name", "")
            payload = self._make_event_payload(
                "domcontentloaded" if name == "dom-interactive" else "load",
                name=name,
                url=evt_url,
            )
            if name == "dom-interactive":
                self._emit_event_threadsafe("domcontentloaded", payload)
            if name == "dom-complete":
                self._emit_event_threadsafe("load", payload)

        self._client.add_event_listener(
            console_id, Events.WebConsole.DOCUMENT_EVENT, _on_doc_event
        )
        self._persistent_console_id = console_id
        self._persistent_console_cb = _on_doc_event

    def _watch_target(self, target: Dict[str, Any]) -> None:
        if self._closed:
            return
        if target.get("isTopLevelTarget"):
            new_actor = target.get("actor", "")
            new_console = target.get("consoleActor", "")
            if new_console and new_console != self._console_actor_id:
                self._console_actor_id = new_console
                self._console_started = False
                self._attach_persistent_console_listener(new_console)
            if new_actor:
                self._target_actor_id = new_actor
            bc = target.get("browsingContextID")
            if bc is not None:
                self._browsing_context_id = bc
            new_url = target.get("url", "")
            if new_url and new_url.startswith("http"):
                self._url = new_url
                self._emit_event_threadsafe(
                    "framenavigated",
                    self._make_event_payload(
                        "framenavigated",
                        name="target-available",
                        url=new_url,
                    ),
                )
            self._target_ver += 1
            logger.debug(
                f"Persistent watcher: target updated v{self._target_ver} -> {new_console}"
            )

    async def _idle_mouse_loop(self):
        """Subtle micro-movements while waiting, mimicking human idle behavior."""
        import random as _r

        try:
            while True:
                await asyncio.sleep(_r.uniform(0.4, 1.5))
                dx = _r.gauss(0, 15)
                dy = _r.gauss(0, 10)
                nx = max(50, min(self.mouse._x + dx, 1800))
                ny = max(50, min(self.mouse._y + dy, 900))
                try:
                    await self.mouse._raw_move(nx, ny)
                    self.mouse._x = nx
                    self.mouse._y = ny
                except Exception:
                    pass
        except asyncio.CancelledError:
            pass

    async def simulate_tab_switch(self, duration: Optional[float] = None) -> None:
        """Simulate the user switching to another tab/window.

        Minimizes the browser window, waits `duration` seconds (5-25 default),
        then restores it. Produces native window.blur, document.visibilitychange
        (hidden), rAF throttling, and on restore: focus + visibilitychange (visible).
        Anti-bot systems (PerimeterX, Shopee SFU, Akamai) track these as a
        strong signal of human behavior. Real users switch tabs 3-8x per session.

        Call only from idle periods -- do not call during navigation or
        extraction, since the tab gets throttled while minimized.
        """
        import random as _r

        if not self._bridge or not self._bridge.is_connected:
            return

        if duration is None:
            duration = _r.uniform(5.0, 25.0)

        try:
            await self._bridge.send_command("minimizeWindow", {}, timeout=5)
        except Exception:
            return

        await asyncio.sleep(duration)

        try:
            await self._bridge.send_command("restoreWindow", {}, timeout=5)
        except Exception:
            pass

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _with_idle_mouse(self):
        """Run idle mouse movements in background during a wait."""
        task = asyncio.create_task(self._idle_mouse_loop())
        try:
            yield
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    def _start_persistent_watcher(self):
        """Set up a tab-level watcher that auto-updates actors on any
        navigation (goto, click, JS redirect, etc.)."""
        tab = TabActor(self._client, self._tab_actor_id)
        watcher_ctx = tab.get_watcher()
        self._watcher_id = watcher_ctx["actor"]
        watcher = WatcherActor(self._client, self._watcher_id)
        watcher.watch_targets(WatcherActor.Targets.FRAME)

        self._attach_persistent_console_listener(self._console_actor_id)

        def _on_target(data):
            self._watch_target(data.get("target", {}))

        self._client.add_event_listener(
            self._watcher_id, Events.Watcher.TARGET_AVAILABLE_FORM, _on_target
        )
        self._persistent_target_cb = _on_target

    def dispose(self) -> None:
        self._closed = True
        if self._network_event_task:
            self._network_event_task.cancel()
            self._network_event_task = None
        self._detach_persistent_console_listener()
        if self._watcher_id and self._persistent_target_cb:
            try:
                self._client.remove_event_listener(
                    self._watcher_id,
                    Events.Watcher.TARGET_AVAILABLE_FORM,
                    self._persistent_target_cb,
                )
            except Exception:
                pass
        self._persistent_target_cb = None

    async def bring_to_front(self) -> None:
        self._ensure_open()
        if not self._bridge or not self._bridge.is_connected or self._tab_id is None:
            raise ConnectionError("Extension bridge not connected or tab ID unavailable")
        await self._bridge.send_command("activateTab", {"tabId": self._tab_id}, timeout=5)

    async def close(self) -> None:
        if self._closed:
            return
        await self._browser._close_page(self)

    def _refresh_target(self):
        tab = TabActor(self._client, self._tab_actor_id)
        target = tab.get_target()
        if target and isinstance(target, dict):
            new_console = target.get("consoleActor", "")
            if new_console and new_console != self._console_actor_id:
                self._console_actor_id = new_console
                self._console_started = False
            self._target_actor_id = target.get("actor", self._target_actor_id)
            self._browsing_context_id = target.get(
                "browsingContextID", self._browsing_context_id
            )

    def _ensure_console(self):
        if not self._console_started:
            console = WebConsoleActor(self._client, self._console_actor_id)
            console.start_listeners([])
            self._console_started = True

    def _eval_sync(self, expression: str, timeout: float = 10.0) -> Any:
        self._ensure_console()

        fut = Future()

        def on_result(data):
            try:
                fut.set_result(data)
            except Exception:
                pass

        console_id = self._console_actor_id
        self._client.add_event_listener(
            console_id, Events.WebConsole.EVALUATION_RESULT, on_result
        )

        try:
            console = WebConsoleActor(self._client, console_id)
            response = console.evaluate_js_async(expression)

            # geckordp returns error dict (not None) on stale actors
            _is_error = response is None or (
                isinstance(response, dict) and "error" in response
            )
            if _is_error:
                self._client.remove_event_listener(
                    console_id, Events.WebConsole.EVALUATION_RESULT, on_result
                )
                self._console_started = False
                self._refresh_target()
                self._ensure_console()
                console_id = self._console_actor_id
                self._client.add_event_listener(
                    console_id, Events.WebConsole.EVALUATION_RESULT, on_result
                )
                console = WebConsoleActor(self._client, console_id)
                response = console.evaluate_js_async(expression)
                if response is None or (
                    isinstance(response, dict) and "error" in response
                ):
                    return None

            data = fut.result(timeout=timeout)
        except Exception:
            return None
        finally:
            self._client.remove_event_listener(
                console_id, Events.WebConsole.EVALUATION_RESULT, on_result
            )

        val = data.get("result")
        if isinstance(val, dict):
            if val.get("type") == "longString":
                actor_id = val.get("actor", "")
                length = val.get("length", 0)
                sa = StringActor(self._client, actor_id)
                full = sa.substring(0, length)
                if isinstance(full, str):
                    return full
                if isinstance(full, dict):
                    return full.get("substring", val.get("initial", ""))
                return val.get("initial", "")
            if val.get("type") == "undefined":
                return None
        return val

    @property
    def url(self) -> str:
        if self._closed:
            return self._url
        # Live evaluate for backward compat (CAPTCHA loops rely on fresh value).
        # Events also update _url during goto/reload for faster access.
        try:
            result = self._eval_sync("window.location.href")
            if isinstance(result, str):
                self._url = result
        except Exception:
            pass
        return self._url

    @property
    def url_cached(self) -> str:
        """Return cached URL (updated by goto/reload events). Zero round-trips."""
        return self._url

    async def url_fresh(self) -> str:
        self._ensure_open()
        """Async explicit evaluate for exact URL."""
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
            found = await self.evaluate(
                f"document.body && document.body.innerText.includes('{escaped}')"
            )
            if found:
                return text
            await asyncio.sleep(0.1)
        raise TimeoutError(f"Text {text!r} not found within {timeout}ms")

    async def wait_for_selector_count(
        self, selector: str, n: int, timeout: int = 5000
    ) -> int:
        self._ensure_open()
        deadline = time.time() + (timeout / 1000)
        while time.time() < deadline:
            count = await self.count(selector)
            if count == n:
                return count
            await asyncio.sleep(0.1)
        raise TimeoutError(
            f"Selector {selector!r} did not reach count {n} within {timeout}ms"
        )

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

    async def wait_for_url(self, pattern: str, timeout: int = 30000) -> str:
        self._ensure_open()
        deadline = time.time() + (timeout / 1000)
        while time.time() < deadline:
            current = await self.url_fresh()
            if pattern in current:
                return current
            await asyncio.sleep(0.1)
        raise TimeoutError(f"URL did not match pattern {pattern!r} within {timeout}ms")

    async def expect_popup(self, timeout: int = 5000) -> "RDPPage":
        self._ensure_open()
        existing_pages = self._browser.list_pages()
        return await self._browser.wait_for_new_page(timeout=timeout, existing_pages=existing_pages)

    async def _enumerate_frames(self) -> List[Dict[str, Any]]:
        self._ensure_open()
        result = await self.evaluate(
            """
            (() => {
              const frames = Array.from(document.querySelectorAll('iframe, frame')).map((frame, index) => {
                try {
                  return {
                    index,
                    name: frame.name || null,
                    id: frame.id || null,
                    src: frame.getAttribute('src') || null,
                    url: frame.contentWindow.location.href,
                    same_origin: true,
                  };
                } catch (e) {
                  return {
                    index,
                    name: frame.name || null,
                    id: frame.id || null,
                    src: frame.getAttribute('src') || null,
                    url: null,
                    same_origin: false,
                  };
                }
              });
              return JSON.stringify(frames);
            })()
            """
        )
        if isinstance(result, str):
            try:
                return json.loads(result)
            except (json.JSONDecodeError, ValueError):
                return []
        return []

    async def _frame_eval_body(self, index: int, body: str) -> Any:
        self._ensure_open()
        result = await self.evaluate(
            f"""
            (() => {{
              const frame = document.querySelectorAll('iframe, frame')[{index}];
              if (!frame) return JSON.stringify({{ ok: false, error: 'frame-not-found' }});
              try {{
                const win = frame.contentWindow;
                const doc = win.document;
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

    async def _frame_evaluate(self, index: int, expression: str) -> Any:
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
        result = await self.evaluate(
            f"""
            (() => {{
              const frame = document.querySelectorAll('iframe, frame')[{index}];
              if (!frame) return JSON.stringify({{ ok: false, error: 'frame-not-found' }});
              try {{
                const win = frame.contentWindow;
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

    async def frame(
        self,
        index: Optional[int] = None,
        name: Optional[str] = None,
        url_contains: Optional[str] = None,
    ) -> Optional[RDPFrame]:
        self._ensure_open()
        for frame in await self.frames():
            if index is not None and frame.index != index:
                continue
            if name is not None and frame.name != name:
                continue
            if url_contains is not None and (not frame.url or url_contains not in frame.url):
                continue
            return frame
        return None

    async def is_active(self) -> bool:
        self._ensure_open()
        if not self._bridge or not self._bridge.is_connected or self._tab_id is None:
            return False
        try:
            result = await self._bridge.send_command("getActiveTab", {}, timeout=3)
            return bool(result and result.get("tabId") == self._tab_id)
        except Exception:
            return False

    async def goto(
        self, url: str, wait_until: str = "load", timeout: int = 30000
    ) -> None:
        self._ensure_open()
        async with self._nav_lock:
            await self._goto_impl(url, wait_until=wait_until, timeout=timeout)

    async def _goto_impl(
        self, url: str, wait_until: str = "load", timeout: int = 30000
    ) -> None:
        loop = asyncio.get_running_loop()
        load_done = asyncio.Event()
        deadline = time.time() + (timeout / 1000)
        console_listeners: list = []

        goal = (
            "dom-complete"
            if wait_until in ("load", "networkidle")
            else "dom-interactive"
        )

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
            WebConsoleActor(self._client, console_id).start_listeners(
                [WebConsoleActor.Listeners.DOCUMENT_EVENTS]
            )
            self._client.add_event_listener(
                console_id, Events.WebConsole.DOCUMENT_EVENT, _on_doc_event
            )
            console_listeners.append(console_id)

        # Listen on current console for same-origin nav events
        await asyncio.to_thread(
            lambda: _attach_console_listener(self._console_actor_id)
        )
        self._console_started = True

        try:
            # Snapshot target version before navigating
            ver_before = self._target_ver

            # Navigate via BrowsingContext.fixupAndLoadURIString with user activation.
            # Sends sec-fetch-user:?1 without any DOM manipulation.
            # Falls back to TabDescriptor for about:blank or no bridge.
            navigated = False
            if self._bridge and self._bridge.is_connected and self._tab_id is not None:
                try:
                    await self._bridge.send_command(
                        "navigate", {"tabId": self._tab_id, "url": url}
                    )
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

                    # Persistent watcher updated the target (cross-process nav)
                    if self._target_ver > last_target_ver:
                        last_target_ver = self._target_ver
                        nav_started = True
                        await asyncio.to_thread(
                            lambda: _attach_console_listener(self._console_actor_id)
                        )
                        self._console_started = True

                        if load_done.is_set():
                            return
                        try:
                            state = await self.evaluate("document.readyState")
                            if state == "complete" or (
                                goal == "dom-interactive"
                                and state in ("interactive", "complete")
                            ):
                                return
                        except Exception:
                            pass
                        continue

                    remaining = max(0.1, deadline - time.time())
                    try:
                        await asyncio.wait_for(
                            load_done.wait(), timeout=min(1.0, remaining)
                        )
                        return
                    except asyncio.TimeoutError:
                        try:
                            state = await self.evaluate("document.readyState")
                            # Only trust "complete" if we saw nav start first
                            if state in ("loading", "interactive"):
                                nav_started = True
                            if nav_started and (
                                state == "complete"
                                or (
                                    goal == "dom-interactive"
                                    and state in ("interactive", "complete")
                                )
                            ):
                                return
                        except Exception:
                            # evaluate failed = actor stale = nav in progress
                            nav_started = True
        finally:
            for cid in console_listeners:
                try:
                    self._client.remove_event_listener(
                        cid, Events.WebConsole.DOCUMENT_EVENT, _on_doc_event
                    )
                except Exception:
                    pass

        # Post-navigation: reposition cursor and drift naturally
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

    async def _wait_for_doc_event(
        self, goal: str = "dom-complete", timeout_s: float = 30.0
    ) -> None:
        self._ensure_open()
        """Wait for a WebConsoleActor DOCUMENT_EVENT matching *goal*.
        Used by reload() and wait_for_load_state() where no cross-process
        nav is expected so we only listen on the current console."""
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

        await asyncio.to_thread(
            lambda: WebConsoleActor(self._client, console_id).start_listeners(
                [WebConsoleActor.Listeners.DOCUMENT_EVENTS]
            )
        )
        self._console_started = True
        self._client.add_event_listener(
            console_id, Events.WebConsole.DOCUMENT_EVENT, _on_evt
        )
        try:
            async with self._with_idle_mouse():
                await asyncio.wait_for(done.wait(), timeout=timeout_s)
        except asyncio.TimeoutError:
            pass
        finally:
            try:
                self._client.remove_event_listener(
                    console_id, Events.WebConsole.DOCUMENT_EVENT, _on_evt
                )
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

        # Start doc event listener BEFORE triggering reload
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

        await asyncio.to_thread(
            lambda: WebConsoleActor(self._client, console_id).start_listeners(
                [WebConsoleActor.Listeners.DOCUMENT_EVENTS]
            )
        )
        self._console_started = True
        self._client.add_event_listener(
            console_id, Events.WebConsole.DOCUMENT_EVENT, _on_evt
        )

        try:
            await asyncio.to_thread(
                lambda: WindowGlobalActor(self._client, self._target_actor_id).reload()
            )
            self._console_started = False

            async with self._with_idle_mouse():
                await asyncio.wait_for(done.wait(), timeout=timeout_s)
        except asyncio.TimeoutError:
            pass
        finally:
            try:
                self._client.remove_event_listener(
                    console_id, Events.WebConsole.DOCUMENT_EVENT, _on_evt
                )
            except Exception:
                pass

    async def content(self) -> str:
        self._ensure_open()
        return await self.evaluate("document.documentElement.outerHTML") or ""

    async def evaluate(self, expression: str) -> Any:
        self._ensure_open()
        expr = expression.strip()
        auto_called = False
        # Playwright compat: auto-call arrow/function expressions
        if (
            expr.startswith("() =>")
            or expr.startswith("async () =>")
            or expr.startswith("function")
        ) and not expr.endswith("()"):
            expr = f"({expr})()"
            auto_called = True

        # For auto-called functions, wrap to serialize object/array results
        # (geckordp returns RDP grips for non-primitives, not actual values)
        if auto_called:
            expr = (
                f"(function(){{var v=({expr});"
                f"return typeof v==='object'&&v!==null?JSON.stringify(v):v}})()"
            )

        # Mask "debugger eval code" in Error().stack traces
        if "//# sourceURL=" not in expr:
            expr += "\n//# sourceURL=resource://gre/modules/AppConstants.sys.mjs"

        result = await asyncio.to_thread(self._eval_sync, expr)

        # Parse stringified objects/arrays back to Python
        if auto_called and isinstance(result, str):
            try:
                return json.loads(result)
            except (json.JSONDecodeError, ValueError):
                pass
        return result

    async def query_selector(self, selector: str) -> Optional[Dict]:
        self._ensure_open()
        result = await self.evaluate(
            f"(function(){{ var el = document.querySelector('{selector}');"
            f"if(!el) return null;"
            f"var r = el.getBoundingClientRect();"
            f"return JSON.stringify({{x:r.x,y:r.y,w:r.width,h:r.height}}); }})()"
        )
        if result and isinstance(result, str):
            return json.loads(result)
        return None

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
        await self._ensure_bridge_ready(timeout=5.0)
        await self.click(selector)
        await asyncio.sleep(0.1)
        # Clear existing value via DOM assignment first. The native keyPress
        # bridge currently only supports a plain `key`, not modifier combos.
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
            await self._bridge.send_command(
                "type", {"tabId": self._tab_id, "text": text}
            )
        else:
            # Practical fallback when the extension bridge is unavailable.
            selector_escaped = selector.replace("\\", "\\\\").replace("'", "\\'")
            text_escaped = text.replace("\\", "\\\\").replace("'", "\\'")
            await self.evaluate(
                f"""
                (function() {{
                  const el = document.querySelector('{selector_escaped}');
                  if (!el) return false;
                  if ('value' in el) {{
                    el.value = '{text_escaped}';
                    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    return true;
                  }}
                  return false;
                }})()
                """
            )

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

    async def screenshot(self, path: Optional[str] = None) -> bytes:
        self._ensure_open()
        if self._bridge and self._bridge.is_connected:
            result = await self._bridge.send_command("screenshot", {})
            if result and result.get("dataUrl"):
                b64 = (
                    result["dataUrl"].split(",", 1)[1]
                    if "," in result["dataUrl"]
                    else result["dataUrl"]
                )
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

    def on(self, event: str, callback) -> None:
        self._ensure_open()
        """Register a page event listener.

        Supported events: load, domcontentloaded, framenavigated,
        request, response, requestfinished, requestfailed.
        """
        self._event_listeners.setdefault(event, []).append(callback)
        if event in {"request", "response", "requestfinished", "requestfailed"}:
            self._loop.create_task(self._ensure_network_event_bridge())
        logger.debug("Event listener registered: %s", event)

    def remove_listener(self, event: str, callback) -> None:
        self._ensure_open()
        """Remove a previously-registered page event listener."""
        if event in self._event_listeners:
            try:
                self._event_listeners[event].remove(callback)
                if not self._event_listeners[event]:
                    self._event_listeners.pop(event, None)
            except ValueError:
                pass

    # --- Network capture via extension filterResponseData ---

    async def start_capture(self, patterns: list) -> None:
        self._ensure_open()
        """Start capturing HTTP responses whose URL contains any of the patterns.
        Captured via extension filterResponseData (invisible to page JS)."""
        await self._ensure_bridge_ready(timeout=5.0)
        if not self._bridge or not self._bridge.is_connected:
            raise ConnectionError("Extension bridge not connected")
        await self._bridge.send_command("startCapture", {"patterns": patterns})
        self._capture_ts = int(time.time() * 1000)
        logger.info(f"Network capture started for patterns: {patterns}")

    async def stop_capture(self) -> None:
        self._ensure_open()
        """Stop capturing network responses."""
        if self._bridge and self._bridge.is_connected:
            await self._bridge.send_command("stopCapture", {})

    async def get_captured_responses(self, clear: bool = True) -> list:
        self._ensure_open()
        """Get captured network responses. Returns list of {url, body, timestamp}."""
        if not self._bridge or not self._bridge.is_connected:
            return []
        since = getattr(self, "_capture_ts", 0)
        result = await self._bridge.send_command(
            "getCapturedResponses", {"since": since}
        )
        responses = result.get("responses", []) if result else []
        if clear and responses:
            await self._bridge.send_command("clearCaptures", {})
        return responses

    async def wait_for_response(
        self, url_pattern: str, timeout: float = 30.0
    ) -> Optional[dict]:
        self._ensure_open()
        """Wait until a captured response matching url_pattern appears.
        Returns the response dict {url, body, timestamp} or None on timeout."""
        deadline = time.time() + timeout
        since = getattr(self, "_capture_ts", 0)
        while time.time() < deadline:
            if self._bridge and self._bridge.is_connected:
                result = await self._bridge.send_command(
                    "getCapturedResponses", {"since": since}
                )
                responses = result.get("responses", []) if result else []
                for r in responses:
                    if url_pattern in r.get("url", ""):
                        return r
            await asyncio.sleep(0.5)
        return None

    async def start_spy(self, patterns: list) -> None:
        self._ensure_open()
        """Start spying on outgoing requests matching URL patterns.
        Captures request headers, body, and response body."""
        await self._ensure_bridge_ready(timeout=5.0)
        if not self._bridge or not self._bridge.is_connected:
            raise ConnectionError("Extension bridge not connected")
        await self._bridge.send_command("startSpy", {"patterns": patterns})
        self._spy_ts = int(time.time() * 1000)
        logger.info(f"Request spy started for patterns: {patterns}")

    async def stop_spy(self) -> None:
        self._ensure_open()
        """Stop spying on requests."""
        if self._bridge and self._bridge.is_connected:
            await self._bridge.send_command("stopSpy", {})

    async def get_spied_requests(self, clear: bool = False) -> list:
        self._ensure_open()
        """Get spied requests. Returns list of {url, method, headers, body, responseBody, timestamp}."""
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
        await self._ensure_bridge_ready(timeout=5.0)
        if not self._bridge or not self._bridge.is_connected:
            raise ConnectionError("Extension bridge not connected")
        return await self._bridge.send_command(
            "setInterception",
            {
                "blockPatterns": list(self._interception_block_patterns),
                "headerRules": list(self._interception_header_rules),
            },
            timeout=10,
        )

    async def set_request_block_patterns(self, patterns: List[str]) -> Dict[str, Any]:
        self._ensure_open()
        self._interception_block_patterns = list(patterns)
        return await self._apply_interception_rules()

    async def set_extra_http_headers(
        self, headers: Dict[str, Any], patterns: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        self._ensure_open()
        self._interception_header_rules = [
            {
                "patterns": patterns or ["http"],
                "headers": {str(k): str(v) for k, v in headers.items()},
            }
        ]
        return await self._apply_interception_rules()

    async def clear_interception(self) -> Dict[str, Any]:
        self._ensure_open()
        self._interception_block_patterns = []
        self._interception_header_rules = []
        await self._ensure_bridge_ready(timeout=5.0)
        if not self._bridge or not self._bridge.is_connected:
            raise ConnectionError("Extension bridge not connected")
        return await self._bridge.send_command("clearInterception", {}, timeout=10)

    async def wait_for_load_state(
        self, state: str = "load", timeout: int = 30000
    ) -> None:
        self._ensure_open()
        async with self._nav_lock:
            await self._wait_for_load_state_impl(state=state, timeout=timeout)

    async def _wait_for_load_state_impl(
        self, state: str = "load", timeout: int = 30000
    ) -> None:
        # Quick check: already at target state?
        target = "complete" if state in ("load", "networkidle") else "interactive"
        try:
            current = await self.evaluate("document.readyState")
            if current == target or current == "complete":
                return
        except Exception:
            pass
        goal = "dom-complete" if state in ("load", "networkidle") else "dom-interactive"
        await self._wait_for_doc_event(goal=goal, timeout_s=timeout / 1000)

    def _get_memory_actor_id(self) -> str:
        tab = TabActor(self._client, self._tab_actor_id)
        target = tab.get_target()
        return target.get("memoryActor", "")

    async def clear_cookies(self, domain: Optional[str] = None) -> int:
        self._ensure_open()
        """Clear cookies via the WebExtension bridge.
        Returns the number of cookies removed.
        If domain is given, only cookies for that domain are removed.
        """
        if not self._bridge or not self._bridge.is_connected:
            logger.warning("clear_cookies: bridge not connected")
            return 0
        params = {}
        if domain:
            params["domain"] = domain
        try:
            result = await self._bridge.send_command("clearCookies", params, timeout=10)
            removed = result.get("removed", 0) if result else 0
            logger.info(
                f"Cleared {removed} cookies" + (f" for {domain}" if domain else "")
            )
            return removed
        except Exception as e:
            logger.error(f"clear_cookies failed: {e}")
            return 0

    async def force_gc(self) -> None:
        self._ensure_open()
        """Force garbage + cycle collection on the current tab."""

        def _gc():
            actor_id = self._get_memory_actor_id()
            if not actor_id:
                return
            mem = MemoryActor(self._client, actor_id)
            mem.attach()
            mem.force_garbage_collection()
            mem.force_cycle_collection()
            mem.detach()

        await asyncio.to_thread(_gc)

    async def memory_usage(self) -> Optional[Dict]:
        self._ensure_open()
        """Return memory measurement for the current tab."""

        def _measure():
            actor_id = self._get_memory_actor_id()
            if not actor_id:
                return None
            mem = MemoryActor(self._client, actor_id)
            mem.attach()
            result = mem.measure()
            mem.detach()
            return result

        return await asyncio.to_thread(_measure)

    async def wait_for_network_idle(
        self, idle_ms: int = 500, timeout: int = 30000
    ) -> None:
        self._ensure_open()
        """Wait until no network requests are pending for *idle_ms* ms.
        Uses WatcherActor NETWORK_EVENT resource tracking."""
        loop = asyncio.get_running_loop()
        idle_event = asyncio.Event()
        pending: set = set()
        timer_handle: list = [None]

        def _reschedule():
            if timer_handle[0]:
                timer_handle[0].cancel()
                timer_handle[0] = None
            if not pending:
                timer_handle[0] = loop.call_later(idle_ms / 1000, idle_event.set)

        def _on_available(data):
            actors = [
                item.get("actor", "")
                for item in data.get("array", [])
                if isinstance(item, dict)
                and item.get("resourceType") == "network-event"
                and item.get("actor")
            ]
            if actors:

                def _add():
                    pending.update(actors)
                    _reschedule()

                loop.call_soon_threadsafe(_add)

        def _on_updated(data):
            actors = [
                item.get("actor", "")
                for item in data.get("array", [])
                if isinstance(item, dict)
                and item.get("resourceType") == "network-event"
                and item.get("actor")
            ]
            if actors:

                def _remove():
                    for a in actors:
                        pending.discard(a)
                    _reschedule()

                loop.call_soon_threadsafe(_remove)

        tab = TabActor(self._client, self._tab_actor_id)
        watcher_ctx = tab.get_watcher()
        watcher_id = watcher_ctx["actor"]

        def _setup_watcher():
            w = WatcherActor(self._client, watcher_id)
            w.watch_targets(WatcherActor.Targets.FRAME)
            w.watch_resources([Resources.NETWORK_EVENT])

        await asyncio.to_thread(_setup_watcher)

        self._client.add_event_listener(
            watcher_id, Events.Watcher.RESOURCES_AVAILABLE_ARRAY, _on_available
        )
        self._client.add_event_listener(
            watcher_id, Events.Watcher.RESOURCES_UPDATED_ARRAY, _on_updated
        )

        # If network is already idle, start timer immediately
        _reschedule()

        try:
            async with self._with_idle_mouse():
                await asyncio.wait_for(idle_event.wait(), timeout=timeout / 1000)
        except asyncio.TimeoutError:
            pass
        finally:
            if timer_handle[0]:
                timer_handle[0].cancel()
            try:
                self._client.remove_event_listener(
                    watcher_id,
                    Events.Watcher.RESOURCES_AVAILABLE_ARRAY,
                    _on_available,
                )
            except Exception:
                pass
            try:
                self._client.remove_event_listener(
                    watcher_id,
                    Events.Watcher.RESOURCES_UPDATED_ARRAY,
                    _on_updated,
                )
            except Exception:
                pass

    async def wait_for_selector(
        self, selector: str, timeout: int = 30000, state: str = "visible"
    ) -> Optional[Dict]:
        """Wait for an element matching selector to appear/hide.
        Uses MutationObserver + lightweight global-variable poll.
        state: 'visible', 'attached', or 'hidden'.
        Returns element rect or None on timeout."""
        sel_escaped = selector.replace("'", "\\'")

        # Use a namespaced store to avoid detectable global variable patterns
        wfs_key = f"_s{int(time.time() * 1000) % 100000}"

        if state == "hidden":
            setup_js = (
                f"(function(){{"
                f"  if(!window._ws)window._ws={{}};"
                f"  if (!document.querySelector('{sel_escaped}')) {{ window._ws['{wfs_key}']='ok'; return '{wfs_key}'; }}"
                f"  var obs = new MutationObserver(function(){{"
                f"    if (!document.querySelector('{sel_escaped}')) {{ obs.disconnect(); window._ws['{wfs_key}']='ok'; }}"
                f"  }});"
                f"  obs.observe(document.body||document.documentElement,"
                f"    {{childList:true,subtree:true,attributes:true}});"
                f"  setTimeout(function(){{ obs.disconnect(); if(!window._ws['{wfs_key}']) window._ws['{wfs_key}']='timeout'; }},{timeout});"
                f"  return '{wfs_key}';"
                f"}})()"
            )
        else:
            vis_check = (
                "if(r.width===0&&r.height===0) return null;"
                if state == "visible"
                else ""
            )
            setup_js = (
                f"(function(){{"
                f"  if(!window._ws)window._ws={{}};"
                f"  function chk(){{"
                f"    var el=document.querySelector('{sel_escaped}');"
                f"    if(!el) return null;"
                f"    var r=el.getBoundingClientRect(); {vis_check}"
                f"    return JSON.stringify({{x:r.x,y:r.y,w:r.width,h:r.height}});"
                f"  }}"
                f"  var hit=chk(); if(hit){{ window._ws['{wfs_key}']=hit; return '{wfs_key}'; }}"
                f"  var obs=new MutationObserver(function(){{"
                f"    var hit=chk(); if(hit){{ obs.disconnect(); window._ws['{wfs_key}']=hit; }}"
                f"  }});"
                f"  obs.observe(document.body||document.documentElement,"
                f"    {{childList:true,subtree:true,attributes:true}});"
                f"  setTimeout(function(){{ obs.disconnect(); if(!window._ws['{wfs_key}']) window._ws['{wfs_key}']='timeout'; }},{timeout});"
                f"  return '{wfs_key}';"
                f"}})()"
            )

        try:
            await self.evaluate(setup_js)
        except Exception:
            return None

        deadline = time.time() + (timeout / 1000)
        while time.time() < deadline:
            try:
                val = await self.evaluate(f"(window._ws||{{}})['{wfs_key}']")
                if val and val != "null":
                    await self.evaluate(
                        f"try{{delete window._ws['{wfs_key}']}}catch(e){{}}"
                    )
                    if val == "timeout":
                        return None
                    if val == "ok":
                        return {}
                    if isinstance(val, str):
                        return json.loads(val)
                    return val
            except Exception:
                pass
            await asyncio.sleep(0.1)
        # Cleanup on timeout
        try:
            await self.evaluate(f"try{{delete window._ws['{wfs_key}']}}catch(e){{}}")
        except Exception:
            pass
        return None

    def locator(self, selector: str) -> "_Locator":
        """Create a Playwright-compatible locator."""
        return _Locator(self, selector)

    def first(self, selector: str) -> "_Locator":
        return _Locator(self, selector, index=0)

    def nth(self, selector: str, index: int) -> "_Locator":
        return _Locator(self, selector, index=index)

    def last(self, selector: str) -> "_Locator":
        return _Locator(self, selector, index=-1)

    async def query_selector_all(self, selector: str) -> List[Dict]:
        """Return list of element rects matching selector."""
        sel_escaped = selector.replace("'", "\\'")
        result = await self.evaluate(
            f"(function(){{ var els = document.querySelectorAll('{sel_escaped}');"
            f"var out = [];"
            f"for(var i=0; i<els.length; i++) {{"
            f"  var r = els[i].getBoundingClientRect();"
            f"  out.push({{x:r.x,y:r.y,w:r.width,h:r.height,i:i}});"
            f"}}"
            f"return JSON.stringify(out); }})()"
        )
        if result and isinstance(result, str):
            return json.loads(result)
        return []


class _Locator:
    """Playwright-compatible locator for RDPPage."""

    def __init__(self, page: "RDPPage", selector: str, index: Optional[int] = None):
        self._page = page
        self._selector = selector
        self._index = index

    def _to_css_and_js(self) -> str:
        """Convert Playwright-style selector to JS find expression."""
        sel = self._selector
        # Handle text= and text=/regex/ selectors
        if sel.startswith("text="):
            text = sel[5:]
            if text.startswith("/") and "/" in text[1:]:
                # Regex: text=/pattern/flags
                index_expr = self._index if self._index is not None else 0
                if self._index == -1:
                    return (
                        f"(function(){{ var re = new RegExp({text}); var out=[];"
                        f"var tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);"
                        f"while(tw.nextNode()) {{ if(re.test(tw.currentNode.textContent)) out.push(tw.currentNode.parentElement); }}"
                        f"return out.length ? out[out.length-1] : null; }})()"
                    )
                return (
                    f"(function(){{ var re = new RegExp({text}); var out=[];"
                    f"var tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);"
                    f"while(tw.nextNode()) {{ if(re.test(tw.currentNode.textContent)) out.push(tw.currentNode.parentElement); }}"
                    f"return out.length>{index_expr} ? out[{index_expr}] : null; }})()"
                )
            else:
                text_escaped = text.replace("\\", "\\\\").replace("'", "\\'")
                index_expr = self._index if self._index is not None else 0
                if self._index == -1:
                    return (
                        f"(function(){{ var out=[]; var tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);"
                        f"while(tw.nextNode()) {{ if(tw.currentNode.textContent.includes('{text_escaped}')) out.push(tw.currentNode.parentElement); }}"
                        f"return out.length ? out[out.length-1] : null; }})()"
                    )
                return (
                    f"(function(){{ var out=[]; var tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);"
                    f"while(tw.nextNode()) {{ if(tw.currentNode.textContent.includes('{text_escaped}')) out.push(tw.currentNode.parentElement); }}"
                    f"return out.length>{index_expr} ? out[{index_expr}] : null; }})()"
                )
        # Handle css= prefix
        if sel.startswith("css:") or sel.startswith("css="):
            sel = sel[4:]
        sel_escaped = sel.replace(chr(39), chr(92) + chr(39))
        if self._index is None:
            return f"document.querySelector('{sel_escaped}')"
        if self._index == -1:
            return f"(function(){{ var els=document.querySelectorAll('{sel_escaped}'); return els.length ? els[els.length-1] : null; }})()"
        return f"(function(){{ var els=document.querySelectorAll('{sel_escaped}'); return els.length>{self._index} ? els[{self._index}] : null; }})()"

    def first(self) -> "_Locator":
        return _Locator(self._page, self._selector, index=0)

    def nth(self, index: int) -> "_Locator":
        return _Locator(self._page, self._selector, index=index)

    def last(self) -> "_Locator":
        return _Locator(self._page, self._selector, index=-1)

    async def wait_for(self, state: str = "visible", timeout: int = 5000) -> None:
        find_js = self._to_css_and_js()
        wfs_key = f"_l{int(time.time() * 1000) % 100000}"

        if state == "hidden":
            setup_js = (
                f"(function(){{"
                f"  if(!window._ws)window._ws={{}};"
                f"  if (({find_js}) === null) {{ window._ws['{wfs_key}']='ok'; return; }}"
                f"  var obs = new MutationObserver(function(){{"
                f"    if (({find_js}) === null) {{ obs.disconnect(); window._ws['{wfs_key}']='ok'; }}"
                f"  }});"
                f"  obs.observe(document.body||document.documentElement,"
                f"    {{childList:true,subtree:true,attributes:true}});"
                f"  setTimeout(function(){{ obs.disconnect(); if(!window._ws['{wfs_key}']) window._ws['{wfs_key}']='timeout'; }},{timeout});"
                f"}})()"
            )
        else:
            vis = (
                "if(r.width===0&&r.height===0) return null; "
                if state == "visible"
                else ""
            )
            setup_js = (
                f"(function(){{"
                f"  if(!window._ws)window._ws={{}};"
                f"  function chk(){{"
                f"    var el={find_js}; if(!el) return null;"
                f"    var r=el.getBoundingClientRect(); {vis}"
                f"    return JSON.stringify({{x:r.x,y:r.y,w:r.width,h:r.height}});"
                f"  }}"
                f"  var hit=chk(); if(hit){{ window._ws['{wfs_key}']=hit; return; }}"
                f"  var obs=new MutationObserver(function(){{"
                f"    var hit=chk(); if(hit){{ obs.disconnect(); window._ws['{wfs_key}']=hit; }}"
                f"  }});"
                f"  obs.observe(document.body||document.documentElement,"
                f"    {{childList:true,subtree:true,attributes:true}});"
                f"  setTimeout(function(){{ obs.disconnect(); if(!window._ws['{wfs_key}']) window._ws['{wfs_key}']='timeout'; }},{timeout});"
                f"}})()"
            )

        await self._page.evaluate(setup_js)

        deadline = time.time() + (timeout / 1000)
        while time.time() < deadline:
            val = await self._page.evaluate(f"(window._ws||{{}})['{wfs_key}']")
            if val and val != "null":
                await self._page.evaluate(
                    f"try{{delete window._ws['{wfs_key}']}}catch(e){{}}"
                )
                if val == "timeout":
                    raise TimeoutError(
                        f"Locator '{self._selector}' not {state} within {timeout}ms"
                    )
                return
            await asyncio.sleep(0.1)
        try:
            await self._page.evaluate(
                f"try{{delete window._ws['{wfs_key}']}}catch(e){{}}"
            )
        except Exception:
            pass
        raise TimeoutError(f"Locator '{self._selector}' not {state} within {timeout}ms")

    async def click(self, timeout: int = 5000) -> None:
        find_js = self._to_css_and_js()
        deadline = time.time() + (timeout / 1000)
        while time.time() < deadline:
            try:
                js = (
                    f"(function(){{ var el = {find_js}; if(!el) return null; "
                    f"var r = el.getBoundingClientRect(); "
                    f"if(r.width===0&&r.height===0) return null; "
                    f"return JSON.stringify({{x:r.x+r.width/2,y:r.y+r.height/2,w:r.width}}); }})()"
                )
                result = await self._page.evaluate(js)
                if result and isinstance(result, str):
                    pos = json.loads(result)
                    await self._page.mouse.click_smooth(
                        pos["x"], pos["y"], target_width=pos.get("w", 50)
                    )
                    return
            except Exception:
                pass
            await asyncio.sleep(0.3)
        raise TimeoutError(
            f"Locator '{self._selector}' not clickable within {timeout}ms"
        )

    async def text_content(self) -> Optional[str]:
        find_js = self._to_css_and_js()
        result = await self._page.evaluate(
            f"(function(){{ var el = {find_js}; return el ? el.textContent : null; }})()"
        )
        return result

    async def inner_text(self) -> Optional[str]:
        find_js = self._to_css_and_js()
        result = await self._page.evaluate(
            f"(function(){{ var el = {find_js}; return el ? el.innerText : null; }})()"
        )
        return result

    async def get_attribute(self, name: str) -> Optional[str]:
        find_js = self._to_css_and_js()
        name_escaped = name.replace("'", "\\'")
        result = await self._page.evaluate(
            f"(function(){{ var el = {find_js}; return el ? el.getAttribute('{name_escaped}') : null; }})()"
        )
        return result

    async def count(self) -> int:
        sel = self._selector
        if sel.startswith("text="):
            # Can't easily count text matches, return 0 or 1
            text = sel[5:]
            if text.startswith("/") and "/" in text[1:]:
                result = await self._page.evaluate(
                    f"(function(){{ var re = new RegExp({text}); var n=0; var tw=document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT); while(tw.nextNode()){{ if(re.test(tw.currentNode.textContent)) n++; }} return n; }})()"
                )
                return result or 0
            text_escaped = text.replace("\\", "\\\\").replace("'", "\\'")
            result = await self._page.evaluate(
                f"(function(){{ var n=0; var tw=document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT); while(tw.nextNode()){{ if(tw.currentNode.textContent.includes('{text_escaped}')) n++; }} return n; }})()"
            )
            return result or 0
        if sel.startswith("css:") or sel.startswith("css="):
            sel = sel[4:]
        sel_escaped = sel.replace("'", "\\'")
        result = await self._page.evaluate(
            f"document.querySelectorAll('{sel_escaped}').length"
        )
        return result or 0

    async def exists(self) -> bool:
        return (await self.count()) > 0

    async def is_visible(self) -> bool:
        find_js = self._to_css_and_js()
        result = await self._page.evaluate(
            f"""(function(){{
                var el = {find_js};
                if (!el) return false;
                var style = window.getComputedStyle(el);
                if (!style) return false;
                if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
                var r = el.getBoundingClientRect();
                return !!(r.width > 0 && r.height > 0);
            }})()"""
        )
        return bool(result)

    async def is_hidden(self) -> bool:
        return not await self.is_visible()


class _FrameLocator:
    """Playwright-like locator for RDPFrame (same-origin only)."""

    def __init__(self, frame: RDPFrame, selector: str, index: Optional[int] = None):
        self._frame = frame
        self._selector = selector
        self._index = index

    def _selector_expr(self) -> str:
        sel = self._selector.replace("\\", "\\\\").replace("'", "\\'")
        if self._index is None:
            return f"doc.querySelector('{sel}')"
        if self._index == -1:
            return f"(function(){{ const els=doc.querySelectorAll('{sel}'); return els.length ? els[els.length-1] : null; }})()"
        return f"(function(){{ const els=doc.querySelectorAll('{sel}'); return els.length>{self._index} ? els[{self._index}] : null; }})()"

    def first(self) -> "_FrameLocator":
        return _FrameLocator(self._frame, self._selector, index=0)

    def nth(self, index: int) -> "_FrameLocator":
        return _FrameLocator(self._frame, self._selector, index=index)

    def last(self) -> "_FrameLocator":
        return _FrameLocator(self._frame, self._selector, index=-1)

    async def wait_for(self, state: str = "visible", timeout: int = 5000) -> None:
        result = await self._frame.wait_for_selector(self._selector, timeout=timeout, state=state)
        if result is None:
            raise TimeoutError(f"Frame locator '{self._selector}' not {state} within {timeout}ms")

    async def text_content(self) -> Optional[str]:
        expr = self._selector_expr()
        return await self._frame._page._frame_eval_body(
            self._frame.index,
            f"const el = {expr}; return el ? el.textContent : null;",
        )

    async def inner_text(self) -> Optional[str]:
        expr = self._selector_expr()
        return await self._frame._page._frame_eval_body(
            self._frame.index,
            f"const el = {expr}; return el ? el.innerText : null;",
        )

    async def get_attribute(self, name: str) -> Optional[str]:
        name_escaped = name.replace("\\", "\\\\").replace("'", "\\'")
        expr = self._selector_expr()
        return await self._frame._page._frame_eval_body(
            self._frame.index,
            f"const el = {expr}; return el ? el.getAttribute('{name_escaped}') : null;",
        )

    async def count(self) -> int:
        sel = self._selector.replace("\\", "\\\\").replace("'", "\\'")
        result = await self._frame._page._frame_eval_body(
            self._frame.index,
            f"return doc.querySelectorAll('{sel}').length;",
        )
        try:
            return int(result)
        except Exception:
            return 0

    async def exists(self) -> bool:
        return (await self.count()) > 0

    async def is_visible(self) -> bool:
        expr = self._selector_expr()
        result = await self._frame._page._frame_eval_body(
            self._frame.index,
            f"""
            const el = {expr};
            if (!el) return false;
            const style = win.getComputedStyle(el);
            if (!style) return false;
            if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
            const r = el.getBoundingClientRect();
            return !!(r.width > 0 && r.height > 0);
            """,
        )
        return bool(result)

    async def is_hidden(self) -> bool:
        return not await self.is_visible()

    async def click(self) -> None:
        await self._frame.click(self._selector)

    async def hover(self) -> None:
        await self._frame.hover(self._selector)

    async def focus(self) -> None:
        await self._frame.focus(self._selector)

    async def press(self, key: str) -> None:
        await self._frame.press(self._selector, key)


from camoufox.humanize import (
    generate_path as _generate_path,
    hover_delay as _hover_delay,
)


class _Mouse:
    def __init__(self, page: RDPPage):
        self._page = page
        import random as _r

        self._x: float = _r.uniform(300, 700)
        self._y: float = _r.uniform(200, 500)

    async def _raw_move(self, x: float, y: float) -> None:
        self._page._ensure_open()
        if (
            self._page._bridge
            and self._page._bridge.is_connected
            and self._page._tab_id is not None
        ):
            await self._page._bridge.send_command(
                "moveTo", {"tabId": self._page._tab_id, "x": x, "y": y}
            )

    async def _follow_path(self, path):
        for x, y, delay in path:
            await self._raw_move(x, y)
            await asyncio.sleep(delay)
        if path:
            self._x, self._y = path[-1][0], path[-1][1]

    async def click(self, x: float, y: float, button: int = 0) -> None:
        self._page._ensure_open()
        """Click at (x, y) with humanized movement first.

        Always moves the cursor with sigma-lognormal before clicking, so
        callers cannot accidentally produce a teleport. If the cursor is
        already at the target (distance < 2px), move_smooth is a no-op.
        Use click_smooth() for additional hover delay (visual confirmation pause).
        """
        dx = x - self._x
        dy = y - self._y
        if dx * dx + dy * dy >= 4:  # distance >= 2px
            await self.move_smooth(x, y)

        if (
            self._page._bridge
            and self._page._bridge.is_connected
            and self._page._tab_id is not None
        ):
            await self._page._bridge.send_command(
                "click", {"tabId": self._page._tab_id, "x": self._x, "y": self._y, "button": button}
            )
        else:
            await self._page.evaluate(f"document.elementFromPoint({self._x},{self._y})?.click()")

    async def move(self, x: float, y: float) -> None:
        self._page._ensure_open()
        """Instant move (no animation). Use move_smooth() for human-like."""
        await self._raw_move(x, y)
        self._x, self._y = x, y

    async def move_smooth(self, x: float, y: float, target_width: float = 50.0) -> None:
        self._page._ensure_open()
        """Human-like mouse movement with sub-movements, overshoot, tremor."""
        path = _generate_path(self._x, self._y, x, y, target_width)
        await self._follow_path(path)

    async def click_smooth(
        self, x: float, y: float, button: int = 0, target_width: float = 50.0
    ) -> None:
        self._page._ensure_open()
        """Human-like: move to target, hover delay, click."""
        await self.move_smooth(x, y, target_width)
        await asyncio.sleep(_hover_delay())
        await self.click(self._x, self._y, button)

    async def down(self, x: float, y: float, button: int = 0) -> None:
        self._page._ensure_open()
        if (
            self._page._bridge
            and self._page._bridge.is_connected
            and self._page._tab_id is not None
        ):
            await self._page._bridge.send_command(
                "mouseDown",
                {"tabId": self._page._tab_id, "x": x, "y": y, "button": button},
            )

    async def up(self, x: float, y: float, button: int = 0) -> None:
        self._page._ensure_open()
        if (
            self._page._bridge
            and self._page._bridge.is_connected
            and self._page._tab_id is not None
        ):
            await self._page._bridge.send_command(
                "mouseUp",
                {"tabId": self._page._tab_id, "x": x, "y": y, "button": button},
            )

    async def wheel(self, delta_x: float, delta_y: float) -> None:
        self._page._ensure_open()
        """Single wheel event. Use wheel_smooth() for human-like scrolling."""
        if (
            self._page._bridge
            and self._page._bridge.is_connected
            and self._page._tab_id is not None
        ):
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
        """Human-like scroll: bursts with momentum decay and reading pauses."""
        from camoufox.humanize import scroll_sequence

        events = scroll_sequence(delta_y)
        for dy, delay in events:
            if abs(dy) > 0.5:
                await self.wheel(0, dy)
            await asyncio.sleep(delay)


class _Keyboard:
    def __init__(self, page: RDPPage):
        self._page = page

    async def type(self, text: str, instant: bool = False) -> None:
        self._page._ensure_open()
        """Type text character-by-character with log-normal inter-key delays.

        Shopee SFU SDK tracks 5 keyboard events with timestamps. Typing the
        whole string at once produces 0ms inter-key intervals (bot signature).
        Set instant=True to bypass humanization (for non-detected contexts).
        """
        if (
            not self._page._bridge
            or not self._page._bridge.is_connected
            or self._page._tab_id is None
        ):
            return

        if instant or not text:
            await self._page._bridge.send_command(
                "type", {"tabId": self._page._tab_id, "text": text}
            )
            return

        from camoufox.humanize import typing_sequence
        for ch, delay in typing_sequence(text):
            try:
                await self._page._bridge.send_command(
                    "type", {"tabId": self._page._tab_id, "text": ch}
                )
            except Exception:
                break
            await asyncio.sleep(delay)

    async def press(self, key: str) -> None:
        self._page._ensure_open()
        if (
            self._page._bridge
            and self._page._bridge.is_connected
            and self._page._tab_id is not None
        ):
            await self._page._bridge.send_command(
                "keyPress", {"tabId": self._page._tab_id, "key": key}
            )


class RDPBrowser:
    """
    Camoufox browser via Firefox RDP + WebExtension.
    Zero detection surface. Passes PerimeterX, Shopee, Akamai.

    Robust initialization: TCP port probe + retry logic eliminates
    race conditions when launching multiple instances.
    """

    # Limit concurrent browser initializations to avoid disk/CPU thrashing
    _init_semaphore: Optional[asyncio.Semaphore] = None

    @classmethod
    def _get_semaphore(cls) -> asyncio.Semaphore:
        if cls._init_semaphore is None:
            cls._init_semaphore = asyncio.Semaphore(2)
        return cls._init_semaphore

    def __init__(
        self,
        executable_path: Optional[str] = None,
        headless: bool = False,
        proxy: Optional[Dict[str, str]] = None,
        viewport: Optional[Dict[str, int]] = None,
        locale: Optional[str] = None,
        timezone: Optional[str] = None,
        rdp_port: int = DEFAULT_RDP_PORT,
        ws_port: int = DEFAULT_WS_PORT,
        firefox_user_prefs: Optional[Dict[str, Any]] = None,
        profile_path: Optional[str] = None,
        extension_dir: str = EXTENSION_DIR,
        fingerprint: Optional[Dict[str, Any]] = None,
    ):
        self._fingerprint = fingerprint

        # Derive viewport, timezone, locale from fingerprint if not explicit
        if fingerprint:
            if not viewport:
                ow = fingerprint.get("window.outerWidth", 1920)
                oh = fingerprint.get("window.outerHeight", 1040)
                dpr = fingerprint.get("window.devicePixelRatio", 1.0)
                # Firefox --width/--height are physical pixels. With DPR > 1
                # the CSS viewport = physical / DPR. Multiply by DPR so the
                # actual CSS viewport matches the spoofed outerWidth/Height.
                if dpr and dpr > 1.0:
                    ow = int(ow * dpr)
                    oh = int(oh * dpr)
                viewport = {"width": ow, "height": oh}
            if not timezone:
                timezone = fingerprint.get("timezone")
            if not locale:
                lang = fingerprint.get("locale:language", "en")
                region = fingerprint.get("locale:region", "US")
                locale = f"{lang}-{region}, {lang}, en-US, en"

        self._executable = executable_path or _get_default_binary()
        self._headless = headless
        self._proxy = proxy
        self._viewport = viewport or {"width": 1920, "height": 1080}
        self._locale = locale
        self._timezone = timezone
        self._rdp_port = rdp_port
        self._ws_port = ws_port
        self._user_prefs = firefox_user_prefs or {}
        self._profile_path = profile_path
        self._extension_dir = extension_dir
        self._proc: Optional[subprocess.Popen] = None
        self._job = None  # Windows Job Object for process tree cleanup
        self._client: Optional[RDPClient] = None
        self._bridge: Optional[_ExtensionBridge] = None
        self._temp_profile = False
        self._temp_dirs: List[str] = []
        self._pages: List[RDPPage] = []
        self._pages_by_tab_actor: Dict[str, RDPPage] = {}
        self._pages_by_tab_id: Dict[int, RDPPage] = {}
        self._bridge_repair_attempted = False

    async def _get_active_tab_id(self) -> Optional[int]:
        await self._ensure_bridge_connected(timeout=5.0)
        if self._bridge and self._bridge.is_connected:
            try:
                result = await self._bridge.send_command("getActiveTab", {}, timeout=3)
                if result:
                    return result.get("tabId")
            except Exception:
                pass
        return None

    def _snapshot_tabs(self) -> Dict[str, Dict[str, Any]]:
        root = RootActor(self._client)
        tabs = root.list_tabs() or []
        return {
            tab.get("actor", ""): tab
            for tab in tabs
            if isinstance(tab, dict) and tab.get("actor")
        }

    def _register_page(self, page: RDPPage) -> RDPPage:
        existing = self._pages_by_tab_actor.get(page._tab_actor_id)
        if existing and existing is not page:
            try:
                existing.dispose()
            except Exception:
                pass
            self._unregister_page(existing)
        self._pages_by_tab_actor[page._tab_actor_id] = page
        if page._tab_id is not None:
            self._pages_by_tab_id[page._tab_id] = page
        if page not in self._pages:
            self._pages.append(page)
        return page

    def _unregister_page(self, page: RDPPage) -> None:
        self._pages_by_tab_actor.pop(page._tab_actor_id, None)
        if page._tab_id is not None:
            self._pages_by_tab_id.pop(page._tab_id, None)
        try:
            self._pages.remove(page)
        except ValueError:
            pass

    def _build_page_from_tab(self, tab_actor_id: str, tab_id: Optional[int] = None) -> RDPPage:
        existing = self._pages_by_tab_actor.get(tab_actor_id)
        if existing and not existing.is_closed():
            if tab_id is not None and existing._tab_id != tab_id:
                if existing._tab_id is not None:
                    self._pages_by_tab_id.pop(existing._tab_id, None)
                existing._tab_id = tab_id
                self._pages_by_tab_id[tab_id] = existing
            return existing

        tab = TabActor(self._client, tab_actor_id)
        target = tab.get_target()
        if not target or not isinstance(target, dict) or not target.get("actor"):
            raise RuntimeError(f"Failed to resolve target for tab actor {tab_actor_id}")
        page = RDPPage(
            browser=self,
            client=self._client,
            tab_actor_id=tab_actor_id,
            target_actor_id=target.get("actor", ""),
            console_actor_id=target.get("consoleActor", ""),
            browsing_context_id=target.get("browsingContextID"),
            bridge=self._bridge,
            tab_id=tab_id,
        )
        page._start_persistent_watcher()
        return self._register_page(page)

    def list_pages(self) -> List[RDPPage]:
        self._pages = [page for page in self._pages if not page.is_closed()]
        return list(self._pages)

    async def get_active_page(self) -> Optional[RDPPage]:
        await self._ensure_bridge_connected(timeout=5.0)
        if not self._bridge or not self._bridge.is_connected:
            return None
        try:
            result = await self._bridge.send_command("getActiveTab", {}, timeout=3)
        except Exception:
            return None
        if not result:
            return None
        tab_id = result.get("tabId")
        if tab_id is None:
            return None
        page = self._pages_by_tab_id.get(tab_id)
        return page if page and not page.is_closed() else None

    async def save_state(self) -> Dict[str, Any]:
        state: Dict[str, Any] = {"cookies": [], "origins": []}
        await self._ensure_bridge_connected(timeout=5.0)
        if self._bridge and self._bridge.is_connected:
            try:
                result = await self._bridge.send_command("getCookies", {}, timeout=10)
                state["cookies"] = result.get("cookies", []) if result else []
            except Exception:
                pass

        seen_origins = set()
        for page in self.list_pages():
            try:
                url = await page.url_fresh()
            except Exception:
                continue
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                continue
            origin = f"{parsed.scheme}://{parsed.netloc}"
            if origin in seen_origins:
                continue
            seen_origins.add(origin)
            try:
                local_storage = await page.get_local_storage()
            except Exception:
                local_storage = {}
            state["origins"].append(
                {
                    "origin": origin,
                    "localStorage": local_storage,
                }
            )
        return state

    async def save_state_to_file(self, path: str) -> str:
        state = await self.save_state()
        resolved = os.path.abspath(path)
        with open(resolved, "w", encoding="utf-8") as file_handle:
            json.dump(state, file_handle, indent=2)
        return resolved

    async def load_state(self, state: Dict[str, Any], clear_existing: bool = False) -> Dict[str, int]:
        cookies = state.get("cookies", []) if isinstance(state, dict) else []
        origins = state.get("origins", []) if isinstance(state, dict) else []
        cookies_set = 0
        origins_loaded = 0

        await self._ensure_bridge_connected(timeout=5.0)

        if clear_existing:
            try:
                await self._bridge.send_command("clearCookies", {}, timeout=10)
            except Exception:
                pass

        if cookies and self._bridge and self._bridge.is_connected:
            try:
                result = await self._bridge.send_command("setCookies", {"cookies": cookies}, timeout=15)
                cookies_set = int(result.get("set", 0)) if result else 0
            except Exception:
                cookies_set = 0

        for origin_entry in origins:
            origin = origin_entry.get("origin")
            local_storage = origin_entry.get("localStorage", {})
            if not origin:
                continue
            page = await self.new_page()
            try:
                await page.goto(origin)
                await page.wait_for_load_state("load")
                await page.clear_local_storage()
                if local_storage:
                    await page.set_local_storage(local_storage)
                origins_loaded += 1
            finally:
                await page.close()

        return {"cookies_set": cookies_set, "origins_loaded": origins_loaded}

    async def load_state_from_file(self, path: str, clear_existing: bool = False) -> Dict[str, int]:
        resolved = os.path.abspath(path)
        with open(resolved, "r", encoding="utf-8") as file_handle:
            state = json.load(file_handle)
        return await self.load_state(state, clear_existing=clear_existing)

    async def wait_for_new_page(
        self,
        timeout: int = 5000,
        existing_pages: Optional[List[RDPPage]] = None,
    ) -> RDPPage:
        previous_pages = existing_pages if existing_pages is not None else self.list_pages()
        previous_tab_actor_ids = {page._tab_actor_id for page in previous_pages if not page.is_closed()}
        deadline = time.time() + (timeout / 1000)

        while time.time() < deadline:
            current_pages = self.list_pages()
            for page in current_pages:
                if page.is_closed():
                    continue
                if page._tab_actor_id not in previous_tab_actor_ids:
                    return page

            try:
                new_tab_actor_id = await self._wait_for_new_tab_actor(
                    previous_tab_actor_ids,
                    timeout=min(1.0, max(0.1, deadline - time.time())),
                )
                return self._build_page_from_tab(new_tab_actor_id, await self._get_active_tab_id())
            except TimeoutError:
                await asyncio.sleep(0.1)

        raise TimeoutError(f"Timed out waiting for a new page within {timeout}ms")

    async def page_by_url(self, pattern: str) -> Optional[RDPPage]:
        for page in self.list_pages():
            try:
                current = await page.url_fresh()
            except Exception:
                continue
            if pattern in current:
                return page
        return None

    async def pages_by_url(self, pattern: str) -> List[RDPPage]:
        matches: List[RDPPage] = []
        for page in self.list_pages():
            try:
                current = await page.url_fresh()
            except Exception:
                continue
            if pattern in current:
                matches.append(page)
        return matches

    async def close_all_pages(self) -> None:
        for page in list(self.list_pages()):
            await self._close_page(page)

    async def close_other_pages(self, keep_page: RDPPage) -> None:
        for page in list(self.list_pages()):
            if page is keep_page:
                continue
            await self._close_page(page)

    async def _close_page(self, page: RDPPage) -> None:
        if page.is_closed():
            return
        remaining_pages = [p for p in self._pages if p is not page and not p.is_closed()]
        if self._bridge and self._bridge.is_connected and page._tab_id is not None:
            if remaining_pages:
                await self._bridge.send_command("closeTab", {"tabId": page._tab_id}, timeout=5)
            else:
                try:
                    await page.evaluate("window.location.replace('about:blank')")
                    await page.wait_for_load_state("load", timeout=5000)
                except Exception:
                    pass
        page.dispose()
        self._unregister_page(page)

    async def _wait_for_new_tab_actor(
        self, previous_tab_ids: set[str], timeout: float = 10.0
    ) -> str:
        deadline = time.time() + timeout
        while time.time() < deadline:
            current_tabs = await asyncio.to_thread(self._snapshot_tabs)
            current_ids = set(current_tabs.keys())
            new_ids = current_ids - previous_tab_ids
            if new_ids:
                return next(iter(new_ids))
            await asyncio.sleep(0.2)
        raise TimeoutError("Timed out waiting for a new tab actor")

    async def __aenter__(self) -> "RDPBrowser":
        await self.start()
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()

    def _prepare_extension_with_proxy(
        self, proxy_host: str, proxy_port: int, username: str, password: str
    ) -> str:
        """Copy extension to temp dir and inject proxy routing + auth."""
        ext_copy = os.path.join(self._profile_path, "_ext_with_proxy")
        if os.path.exists(ext_copy):
            shutil.rmtree(ext_copy)
        shutil.copytree(EXTENSION_DIR, ext_copy)
        bg_path = os.path.join(ext_copy, "background.js")
        with open(bg_path, "r", encoding="utf-8") as f:
            content = f.read()

        content = content.replace("let wsPort = 8775;", f"let wsPort = {self._ws_port};")

        proxy_js = (
            f"let proxyConfig = {{\n"
            f'  host: "{proxy_host}",\n'
            f"  port: {proxy_port}\n"
            f"}};\n"
            f'let proxyCredentials = {{ username: "{username}", password: "{password}" }};\n'
            f"\n"
            f"browser.proxy.onRequest.addListener(\n"
            f"  (details) => {{\n"
            f'    if (details.url.startsWith("ws://127.0.0.1") ||\n'
            f'        details.url.startsWith("http://127.0.0.1") ||\n'
            f'        details.url.startsWith("http://localhost")) {{\n'
            f'      return {{ type: "direct" }};\n'
            f"    }}\n"
            f"    return {{\n"
            f'      type: "http",\n'
            f"      host: proxyConfig.host,\n"
            f"      port: proxyConfig.port\n"
            f"    }};\n"
            f"  }},\n"
            f'  {{ urls: ["<all_urls>"] }}\n'
            f");\n"
            f"\n"
            f"browser.webRequest.onAuthRequired.addListener(\n"
            f"  (details) => {{\n"
            f"    if (details.isProxy && proxyCredentials) {{\n"
            f"      return {{ authCredentials: proxyCredentials }};\n"
            f"    }}\n"
            f"  }},\n"
            f'  {{ urls: ["<all_urls>"] }},\n'
            f'  ["blocking"]\n'
            f");\n"
        )

        content = content.replace(
            "let proxyConfig = null;\nlet proxyCredentials = null;", proxy_js
        )
        with open(bg_path, "w", encoding="utf-8") as f:
            f.write(content)
        self._temp_dirs.append(ext_copy)
        return ext_copy

    def _prepare_extension_runtime(self) -> str:
        """Copy extension to temp dir and inject runtime websocket port."""
        ext_copy = os.path.join(self._profile_path, "_ext_runtime")
        if os.path.exists(ext_copy):
            shutil.rmtree(ext_copy)
        shutil.copytree(EXTENSION_DIR, ext_copy)
        bg_path = os.path.join(ext_copy, "background.js")
        with open(bg_path, "r", encoding="utf-8") as f:
            content = f.read()
        content = content.replace("let wsPort = 8775;", f"let wsPort = {self._ws_port};")
        with open(bg_path, "w", encoding="utf-8") as f:
            f.write(content)
        self._temp_dirs.append(ext_copy)
        return ext_copy

    async def start(self) -> None:
        if not self._profile_path:
            self._profile_path = tempfile.mkdtemp(prefix="camou_rdp_")
            self._temp_profile = True
            self._temp_dirs.append(self._profile_path)

        os.makedirs(self._profile_path, exist_ok=True)

        prefs = {
            "extensions.experiments.enabled": True,
            "xpinstall.signatures.required": False,
            "extensions.autoDisableScopes": 0,
            "extensions.enabledScopes": 15,
            "browser.startup.page": 0,
            "browser.startup.homepage_override.mstone": "ignore",
            "browser.aboutwelcome.enabled": False,
            "browser.newtabpage.enabled": False,
            "browser.safebrowsing.enabled": False,
            "browser.safebrowsing.malware.enabled": False,
            "browser.safebrowsing.phishing.enabled": False,
            "network.captive-portal-service.enabled": False,
            "network.connectivity-service.enabled": False,
            "app.update.enabled": False,
            "extensions.getAddons.showPane": False,
            "extensions.getAddons.cache.enabled": False,
            # Anti-detection: force-detach debugger thread actor so WAF
            # debugger traps don't fire. Current binary reads librewolf.*
            # namespace (patch bug fixed for next build).
            "librewolf.debugger.force_detach": True,
            # Restore session history so back/forward works normally.
            # winfox.cfg defaults to 0 which is detectable.
            "browser.sessionhistory.max_entries": 50,
            # Enable async event dispatch so sendMouseEvent crosses
            # Fission process boundaries to reach content.
            "test.events.async.enabled": True,
            # Tell the extension exactly which WS port to connect to
            # (avoids scanning 8775-8790 which causes multi-instance conflicts).
            "extensions.input.ws_port": self._ws_port,
            # Fix Bug 1749009: proxy onAuthRequired + blocking breaks iframe
            # loading (COEP check on 407 response). Captcha iframes behind
            # authenticated proxies fail with NS_ERROR_DOM_CORP_FAILED.
            "browser.tabs.remote.useCrossOriginEmbedderPolicy": False,
        }
        if self._proxy:
            parsed = urlparse(
                self._proxy["server"]
                if "://" in self._proxy.get("server", "")
                else f"http://{self._proxy.get('server', '')}"
            )
            proxy_host = parsed.hostname or ""
            proxy_port = parsed.port or 8080
            if self._proxy.get("username"):
                self._extension_dir = self._prepare_extension_with_proxy(
                    proxy_host,
                    proxy_port,
                    self._proxy["username"],
                    self._proxy.get("password", ""),
                )
            else:
                prefs["network.proxy.type"] = 1
                prefs["network.proxy.http"] = proxy_host
                prefs["network.proxy.http_port"] = proxy_port
                prefs["network.proxy.ssl"] = proxy_host
                prefs["network.proxy.ssl_port"] = proxy_port
                prefs["network.proxy.no_proxies_on"] = "localhost, 127.0.0.1"
        if self._locale:
            prefs["intl.accept_languages"] = self._locale

        # prefers-color-scheme: apply from fingerprint profile (50/50 light/dark
        # avoids the 100%-dark-mode anomaly in CreepJS headlessRating).
        # Fallback for legacy profiles without the field: derive deterministically
        # from canvas:seed so the same profile always gets the same scheme.
        if self._fingerprint:
            scheme = self._fingerprint.get("_prefers_color_scheme")
            if not scheme:
                canvas_seed = int(self._fingerprint.get("canvas:seed", 0) or 0)
                scheme = "dark" if (canvas_seed & 1) else "light"
            # layout.css.prefers-color-scheme.content-override: 1=light, 2=dark
            if scheme == "dark":
                prefs["ui.systemUsesDarkTheme"] = 1
                prefs["layout.css.prefers-color-scheme.content-override"] = 2
            else:
                prefs["ui.systemUsesDarkTheme"] = 0
                prefs["layout.css.prefers-color-scheme.content-override"] = 1

        _write_user_prefs(self._profile_path, prefs)

        args = [
            self._executable,
            "--new-instance",
            "--no-remote",
            f"--start-debugger-server={self._rdp_port}",
            "--profile",
            self._profile_path,
            f"--width={self._viewport['width']}",
            f"--height={self._viewport['height']}",
        ]
        if self._headless:
            args.append("--headless")

        self._bridge = _ExtensionBridge(self._ws_port)
        await self._bridge.start()

        env = os.environ.copy()
        runtime_config = {"allowAddonNewtab": True}
        if self._fingerprint:
            # Full fingerprint config: strip _meta, chunk for Windows env var limit
            fp_config = {
                k: v for k, v in self._fingerprint.items() if not k.startswith("_")
            }
            runtime_config.update(fp_config)
            chunk_size = 2047
            if self._timezone:
                env["TZ"] = self._timezone
        elif self._timezone:
            env["TZ"] = self._timezone
        if self._timezone:
            runtime_config["timezone"] = self._timezone

        config_str = json.dumps(runtime_config)
        chunk_size = 2047
        for i in range(0, len(config_str), chunk_size):
            chunk = config_str[i : i + chunk_size]
            env[f"CAMOU_CONFIG_{(i // chunk_size) + 1}"] = chunk

        logger.info(f"Launching Camoufox RDP on port {self._rdp_port}")
        self._proc = subprocess.Popen(args, env=env)

        # Assign to Job Object so all child processes are killed on close
        if _kernel32 and self._proc:
            self._job = _create_job_object()
            if self._job:
                _kernel32.AssignProcessToJobObject(self._job, int(self._proc._handle))

        await self._connect_rdp()
        await self._install_extension()
        await self._wait_for_bridge()
        await self._apply_overrides()

    async def _connect_rdp(self, max_retries: int = 5) -> None:
        await _wait_for_port("localhost", self._rdp_port, timeout=30.0)
        for i in range(max_retries):
            try:
                client = RDPClient(timeout_sec=10)
                client.connect("localhost", self._rdp_port)
                self._client = client
                logger.info("RDP connected")
                return
            except Exception as e:
                if self._proc and self._proc.poll() is not None:
                    raise RuntimeError("Camoufox process exited unexpectedly")
                if i < max_retries - 1:
                    await asyncio.sleep(1)
                else:
                    raise ConnectionError(f"RDP connection failed: {e}")

    async def _install_extension(self, max_retries: int = 3) -> None:
        """Install the WebExtension with retry logic."""
        if not os.path.isdir(self._extension_dir):
            logger.warning(f"Extension dir not found: {self._extension_dir}")
            return

        for attempt in range(1, max_retries + 1):
            try:
                root = RootActor(self._client)
                root_data = root.get_root()
                if not root_data:
                    raise RuntimeError("get_root returned None")
                addons_id = root_data.get("addonsActor", "")
                if not addons_id:
                    raise RuntimeError("No addonsActor available")

                addons = AddonsActor(self._client, addons_id)
                ext_path = os.path.abspath(self._extension_dir)
                result = addons.install_temporary_addon(ext_path)
                logger.info(f"Extension installed (attempt {attempt}): {result}")
                return
            except Exception as e:
                logger.debug(f"Extension install attempt {attempt} failed: {e}")
                if attempt < max_retries:
                    await asyncio.sleep(1.0 * attempt)
                else:
                    logger.warning(
                        f"Extension install failed after {max_retries} attempts: {e}"
                    )

    async def _wait_for_bridge(self, timeout: float = 10.0, warn: bool = True) -> None:
        """Wait for the extension WebSocket bridge to connect."""
        if not self._bridge:
            return
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._bridge.is_connected:
                logger.info("Extension bridge connected")
                return
            await asyncio.sleep(0.5)
        if warn:
            logger.warning(f"Extension bridge not connected after {timeout}s")

    async def _ensure_bridge_connected(self, timeout: float = 10.0) -> bool:
        if self._bridge and self._bridge.is_connected:
            return True
        if not self._bridge:
            return False

        try:
            await self._wait_for_bridge(timeout=1.0, warn=False)
        except Exception:
            pass
        if self._bridge.is_connected:
            return True

        # Retry extension installation once if the bridge still did not connect.
        if not self._bridge_repair_attempted:
            self._bridge_repair_attempted = True
            try:
                await self._install_extension(max_retries=1)
            except Exception:
                pass

        try:
            await self._wait_for_bridge(timeout=min(timeout, 2.0), warn=False)
        except Exception:
            pass
        return bool(self._bridge and self._bridge.is_connected)

    async def _apply_overrides(self) -> None:
        """Apply timezone via window.setTimezone() WebIDL method (Camoufox built-in)."""
        if not self._timezone:
            return
        try:
            root = RootActor(self._client)
            tabs = root.list_tabs()
            if not tabs:
                return
            tab = TabActor(self._client, tabs[0].get("actor", ""))
            target = tab.get_target()
            console_id = target.get("consoleActor", "")
            if not console_id:
                return
            console = WebConsoleActor(self._client, console_id)
            console.start_listeners([])
            console.evaluate_js_async(f'window.setTimezone("{self._timezone}")')
            logger.info(f"Timezone override applied: {self._timezone}")
        except Exception as e:
            logger.debug(f"Timezone override via JS failed: {e}")

    def _read_stderr(self) -> str:
        try:
            if hasattr(self, "_stderr_file") and self._stderr_file:
                self._stderr_file.flush()
                with open(self._stderr_file.name, "r", errors="replace") as f:
                    return f.read()[-1000:]
        except Exception:
            pass
        return ""

    def is_alive(self) -> bool:
        """Check if the browser process is still running."""
        return self._proc is not None and self._proc.poll() is None

    def is_connected(self) -> bool:
        """Check if the RDP connection is alive."""
        if not self._client:
            return False
        try:
            return self._client.connected()
        except Exception:
            return False

    async def new_page(self) -> RDPPage:
        if not self._client:
            raise RuntimeError("RDP client is not connected")

        await self._ensure_bridge_connected(timeout=5.0)

        previous_tabs = await asyncio.to_thread(self._snapshot_tabs)

        # First page after launch: attach the existing startup tab. This keeps
        # bootstrap robust even if addon tab creation races the initial browser
        # window/tab initialization.
        if not self._pages and previous_tabs:
            first_actor = next(iter(previous_tabs))
            return self._build_page_from_tab(first_actor, await self._get_active_tab_id())

        bridge_tab_id = None

        if self._bridge and self._bridge.is_connected:
            try:
                result = await self._bridge.send_command(
                    "createTab", {"url": "about:blank", "active": True}, timeout=5
                )
                if result:
                    bridge_tab_id = result.get("tabId")
            except Exception:
                if self._pages:
                    await self._pages[-1].evaluate("window.open('about:blank', '_blank'); true")
                    try:
                        active_tab = await self._bridge.send_command(
                            "getActiveTab", {}, timeout=3
                        )
                        if active_tab:
                            bridge_tab_id = active_tab.get("tabId")
                    except Exception:
                        pass
        elif previous_tabs:
            # Fallback without extension bridge: open a new tab via window.open
            # from the most recent live page if possible, then wait for a new
            # tab actor. Only fall back to the startup tab if there is no page.
            if self._pages:
                try:
                    await self._pages[-1].evaluate("window.open('about:blank', '_blank'); true")
                    new_tab_actor_id = await self._wait_for_new_tab_actor(set(previous_tabs.keys()))
                    return self._build_page_from_tab(new_tab_actor_id, None)
                except Exception:
                    pass
            first_actor = next(iter(previous_tabs))
            return self._build_page_from_tab(first_actor, None)

        new_tab_actor_id = await self._wait_for_new_tab_actor(set(previous_tabs.keys()))
        return self._build_page_from_tab(new_tab_actor_id, bridge_tab_id)

    async def close(self) -> None:
        for page in list(self._pages):
            try:
                page.dispose()
            except Exception:
                pass
        self._pages.clear()

        if self._bridge:
            await self._bridge.stop()
            self._bridge = None

        if self._client:
            try:
                self._client.disconnect()
            except Exception:
                pass
            self._client = None

        if self._proc:
            # Graceful shutdown: terminate first to let Firefox flush cookies/state
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # Force kill if graceful shutdown failed
                if self._job and _kernel32:
                    _kernel32.TerminateJobObject(self._job, 1)
                else:
                    try:
                        self._proc.kill()
                    except Exception:
                        pass
                try:
                    self._proc.wait(timeout=3)
                except Exception:
                    pass
            if self._job and _kernel32:
                _kernel32.CloseHandle(self._job)
                self._job = None
            self._proc = None
            await asyncio.sleep(0.5)

        if self._temp_profile:
            for d in self._temp_dirs:
                try:
                    shutil.rmtree(d, ignore_errors=True)
                except Exception:
                    pass

        logger.info("RDPBrowser closed")
