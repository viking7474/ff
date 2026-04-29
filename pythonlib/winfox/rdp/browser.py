"""Browser-layer home for the Winfox RDP framework.

This module now hosts a concrete `RDPBrowser` class in the new namespace while
still inheriting the remaining legacy implementation details from
``camoufox.rdp_api`` where needed. The moved methods below represent the real
browser backbone used by the framework.
"""

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from camoufox._rdp_legacy_impl import (
    RDPBrowser as _LegacyRDPBrowser,
    _create_job_object,
    _get_default_binary,
    _kernel32,
    _write_user_prefs,
    logger,
    EXTENSION_DIR,
    DEFAULT_RDP_PORT,
    DEFAULT_WS_PORT,
)
from geckordp.actors.addon.addons import AddonsActor
from geckordp.actors.descriptors.tab import TabActor
from geckordp.actors.root import RootActor
from geckordp.rdp_client import RDPClient

from .bridge import _ExtensionBridge
from .context import RDPContext
from .page import RDPPage
from .ports import _PORT_ALLOCATOR, _wait_for_port


class RDPBrowser(_LegacyRDPBrowser):
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
        if fingerprint:
            if not viewport:
                ow = fingerprint.get("window.outerWidth", 1920)
                oh = fingerprint.get("window.outerHeight", 1040)
                dpr = fingerprint.get("window.devicePixelRatio", 1.0)
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
        self._job = None
        self._client: Optional[RDPClient] = None
        self._bridge: Optional[_ExtensionBridge] = None
        self._temp_profile = False
        self._temp_dirs: List[str] = []
        self._pages: List[RDPPage] = []
        self._pages_by_tab_actor: Dict[str, RDPPage] = {}
        self._pages_by_tab_id: Dict[int, RDPPage] = {}
        self._contexts: List[RDPContext] = []
        self._context_counter = 0
        self._ports_reserved = False
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

    def contexts(self) -> List[RDPContext]:
        self._contexts = [ctx for ctx in self._contexts if not ctx.is_closed()]
        return list(self._contexts)

    def _unregister_context(self, context: RDPContext) -> None:
        try:
            self._contexts.remove(context)
        except ValueError:
            pass

    async def _find_available_port(self, start_port: int) -> int:
        return await _PORT_ALLOCATOR.find_and_reserve(start_port)

    async def _allocate_context_ports(self) -> tuple[int, int]:
        self._context_counter += 1
        rdp_port = await self._find_available_port(self._rdp_port + 100 + self._context_counter)
        ws_port = await self._find_available_port(self._ws_port + 100 + self._context_counter)
        if ws_port == rdp_port:
            ws_port = await self._find_available_port(ws_port + 1)
        return rdp_port, ws_port

    async def new_context(self, **overrides) -> RDPContext:
        if "rdp_port" in overrides or "ws_port" in overrides:
            rdp_port = overrides.get("rdp_port", self._rdp_port + 100 + self._context_counter + 1)
            ws_port = overrides.get("ws_port", self._ws_port + 100 + self._context_counter + 1)
            rdp_port = await _PORT_ALLOCATOR.reserve(rdp_port)
            if ws_port == rdp_port:
                ws_port = await _PORT_ALLOCATOR.find_and_reserve(ws_port + 1)
            else:
                ws_port = await _PORT_ALLOCATOR.reserve(ws_port)
            self._context_counter += 1
        else:
            rdp_port, ws_port = await self._allocate_context_ports()

        child = RDPBrowser(
            executable_path=overrides.get("executable_path", self._executable),
            headless=overrides.get("headless", self._headless),
            proxy=overrides.get("proxy", self._proxy),
            viewport=overrides.get("viewport", self._viewport),
            locale=overrides.get("locale", self._locale),
            timezone=overrides.get("timezone", self._timezone),
            rdp_port=overrides.get("rdp_port", rdp_port),
            ws_port=overrides.get("ws_port", ws_port),
            firefox_user_prefs=overrides.get("firefox_user_prefs", dict(self._user_prefs)),
            profile_path=overrides.get("profile_path"),
            extension_dir=overrides.get("extension_dir", EXTENSION_DIR),
            fingerprint=overrides.get("fingerprint", self._fingerprint),
        )
        child._ports_reserved = True
        try:
            await child.start()
        except Exception:
            await _PORT_ALLOCATOR.release(child._rdp_port)
            await _PORT_ALLOCATOR.release(child._ws_port)
            child._ports_reserved = False
            raise
        context = RDPContext(self, child)
        self._contexts.append(context)
        return context

    async def close_all_contexts(self) -> None:
        for context in list(self.contexts()):
            await context.close()

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
            state["origins"].append({"origin": origin, "localStorage": local_storage})
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

    async def wait_for_new_page(self, timeout: int = 5000, existing_pages: Optional[List[RDPPage]] = None) -> RDPPage:
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

    async def start(self) -> None:
        if not self._ports_reserved:
            self._rdp_port = await _PORT_ALLOCATOR.reserve(self._rdp_port)
            if self._ws_port == self._rdp_port:
                self._ws_port = await _PORT_ALLOCATOR.find_and_reserve(self._ws_port + 1)
            else:
                self._ws_port = await _PORT_ALLOCATOR.reserve(self._ws_port)
            self._ports_reserved = True

        if not self._profile_path:
            self._profile_path = tempfile.mkdtemp(prefix="camou_rdp_")
            self._temp_profile = True
            self._temp_dirs.append(self._profile_path)

        os.makedirs(self._profile_path, exist_ok=True)

        bridge = _ExtensionBridge(self._ws_port)
        await bridge.start()
        self._bridge = bridge

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
            "librewolf.debugger.force_detach": True,
            "browser.sessionhistory.max_entries": 50,
            "test.events.async.enabled": True,
            "extensions.input.ws_port": self._ws_port,
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
                self._extension_dir = self._prepare_extension_with_proxy(proxy_host, proxy_port, self._proxy["username"], self._proxy.get("password", ""))
            else:
                prefs["network.proxy.type"] = 1
                prefs["network.proxy.http"] = proxy_host
                prefs["network.proxy.http_port"] = proxy_port
                prefs["network.proxy.ssl"] = proxy_host
                prefs["network.proxy.ssl_port"] = proxy_port
                prefs["network.proxy.no_proxies_on"] = "localhost, 127.0.0.1"
        else:
            self._extension_dir = self._prepare_extension_runtime()
        if self._locale:
            prefs["intl.accept_languages"] = self._locale

        if self._fingerprint:
            scheme = self._fingerprint.get("_prefers_color_scheme")
            if not scheme:
                canvas_seed = int(self._fingerprint.get("canvas:seed", 0) or 0)
                scheme = "dark" if (canvas_seed & 1) else "light"
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

        env = os.environ.copy()
        runtime_config = {"allowAddonNewtab": True}
        if self._fingerprint:
            fp_config = {k: v for k, v in self._fingerprint.items() if not k.startswith("_")}
            runtime_config.update(fp_config)
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
                    logger.warning(f"Extension install failed after {max_retries} attempts: {e}")

    async def _wait_for_bridge(self, timeout: float = 10.0, warn: bool = True) -> None:
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

    def _prepare_extension_runtime(self) -> str:
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
        return self._proc is not None and self._proc.poll() is None

    def is_connected(self) -> bool:
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
        if not self._pages and previous_tabs:
            first_actor = next(iter(previous_tabs))
            return self._build_page_from_tab(first_actor, await self._get_active_tab_id())

        bridge_tab_id = None
        if self._bridge and self._bridge.is_connected:
            try:
                result = await self._bridge.send_command("createTab", {"url": "about:blank", "active": True}, timeout=5)
                if result:
                    bridge_tab_id = result.get("tabId")
            except Exception:
                if self._pages:
                    await self._pages[-1].evaluate("window.open('about:blank', '_blank'); true")
                    try:
                        active_tab = await self._bridge.send_command("getActiveTab", {}, timeout=3)
                        if active_tab:
                            bridge_tab_id = active_tab.get("tabId")
                    except Exception:
                        pass
        elif previous_tabs:
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
        for context in list(self.contexts()):
            try:
                await context.close()
            except Exception:
                pass
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
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
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

        if self._ports_reserved:
            await _PORT_ALLOCATOR.release(self._rdp_port)
            await _PORT_ALLOCATOR.release(self._ws_port)
            self._ports_reserved = False

        logger.info("RDPBrowser closed")


__all__ = ["RDPBrowser"]
