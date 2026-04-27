import asyncio
import json
import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from camoufox._rdp_legacy_impl import RDPPage


class RDPFrame:
    def __init__(self, page: "RDPPage", metadata: Dict[str, Any]):
        self._page = page
        self.index = metadata.get("index", 0)
        self.path = metadata.get("path", [self.index])
        self.parent_path = metadata.get("parent_path")
        self.depth = metadata.get("depth", len(self.path) - 1)
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
        path_json = json.dumps(self.path)
        result = await self._page.evaluate(
            f"""
            (() => {{
              const path = {path_json};
              let doc = document;
              let x = 0;
              let y = 0;
              let w = 0;
              let h = 0;
              for (const idx of path) {{
                const frames = doc.querySelectorAll('iframe, frame');
                const frame = frames[idx];
                if (!frame) return JSON.stringify({{ ok: false, error: 'frame-not-found' }});
                const r = frame.getBoundingClientRect();
                x += r.x;
                y += r.y;
                w = r.width;
                h = r.height;
                doc = frame.contentWindow.document;
              }}
              return JSON.stringify({{ ok: true, x, y, w, h }});
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
                    raise RuntimeError(
                        f"Frame position lookup failed: {payload.get('error', 'unknown')}"
                    )
                return payload
        raise RuntimeError("Frame position lookup failed")

    async def _target_point(self, selector: str) -> Dict[str, float]:
        self._ensure_same_origin()
        selector_escaped = selector.replace("\\", "\\\\").replace("'", "\\'")
        element_rect = await self._page._frame_eval_body(
            self.path,
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
        return await self._page._frame_evaluate(self.path, expression)

    async def wait_for_text(self, text: str, timeout: int = 5000) -> str:
        self._ensure_same_origin()
        deadline = time.time() + (timeout / 1000)
        text_escaped = text.replace("\\", "\\\\").replace("'", "\\'")
        while time.time() < deadline:
            found = await self._page._frame_eval_body(
                self.path,
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
            self.path,
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
            self.path,
            f"const el = doc.querySelector('{selector_escaped}'); return el ? el.textContent : null;",
        )

    async def inner_text(self, selector: str) -> Optional[str]:
        self._ensure_same_origin()
        selector_escaped = selector.replace("\\", "\\\\").replace("'", "\\'")
        return await self._page._frame_eval_body(
            self.path,
            f"const el = doc.querySelector('{selector_escaped}'); return el ? el.innerText : null;",
        )

    async def inner_html(self, selector: str) -> Optional[str]:
        self._ensure_same_origin()
        selector_escaped = selector.replace("\\", "\\\\").replace("'", "\\'")
        return await self._page._frame_eval_body(
            self.path,
            f"const el = doc.querySelector('{selector_escaped}'); return el ? el.innerHTML : null;",
        )

    async def get_attribute(self, selector: str, name: str) -> Optional[str]:
        self._ensure_same_origin()
        selector_escaped = selector.replace("\\", "\\\\").replace("'", "\\'")
        name_escaped = name.replace("\\", "\\\\").replace("'", "\\'")
        return await self._page._frame_eval_body(
            self.path,
            f"const el = doc.querySelector('{selector_escaped}'); return el ? el.getAttribute('{name_escaped}') : null;",
        )

    async def count(self, selector: str) -> int:
        self._ensure_same_origin()
        selector_escaped = selector.replace("\\", "\\\\").replace("'", "\\'")
        result = await self._page._frame_eval_body(
            self.path,
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
            self.path,
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

    async def wait_for_selector(self, selector: str, timeout: int = 5000, state: str = "visible") -> Optional[Dict[str, Any]]:
        self._ensure_same_origin()
        selector_escaped = selector.replace("\\", "\\\\").replace("'", "\\'")
        deadline = time.time() + (timeout / 1000)
        while time.time() < deadline:
            result = await self._page._frame_eval_body(
                self.path,
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
            self.path,
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
                self.path,
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

    def get_by_test_id(self, value: str) -> "_FrameLocator":
        return _FrameLocator(self, "", mode="testid", value=value, exact=True)

    def get_by_text(self, text: str, exact: bool = False) -> "_FrameLocator":
        return _FrameLocator(self, "", mode="text", value=text, exact=exact)

    def get_by_placeholder(self, text: str, exact: bool = False) -> "_FrameLocator":
        return _FrameLocator(self, "", mode="placeholder", value=text, exact=exact)

    def get_by_label(self, text: str, exact: bool = False) -> "_FrameLocator":
        return _FrameLocator(self, "", mode="label", value=text, exact=exact)

    def get_by_role(self, role: str, name: Optional[str] = None, exact: bool = False) -> "_FrameLocator":
        return _FrameLocator(self, "", mode="role", value=role, exact=exact, role_name=name, role_name_exact=exact)

    async def parent_frame(self) -> Optional["RDPFrame"]:
        if not self.parent_path:
            return None
        return await self._page.frame(path=self.parent_path)

    async def child_frames(self) -> List["RDPFrame"]:
        return await self._page.child_frames(self.path)


class _FrameLocator:
    """Playwright-like locator for RDPFrame (same-origin only)."""

    def __init__(
        self,
        frame: RDPFrame,
        selector: str,
        index: Optional[int] = None,
        mode: str = "css",
        value: Optional[str] = None,
        exact: bool = False,
        role_name: Optional[str] = None,
        role_name_exact: bool = False,
        has_text: Optional[str] = None,
        has_text_exact: bool = False,
        parent: Optional["_FrameLocator"] = None,
    ):
        self._frame = frame
        self._selector = selector
        self._index = index
        self._mode = mode
        self._value = value
        self._exact = exact
        self._role_name = role_name
        self._role_name_exact = role_name_exact
        self._has_text = has_text
        self._has_text_exact = has_text_exact
        self._parent = parent

    def _collection_expr(self) -> str:
        if self._parent is not None:
            root = self._parent._element_expr()
        else:
            root = "doc"
        root_base = f"(({root}).body||({root}).documentElement||({root}))"
        if self._mode == "text":
            text = (self._value or "").replace("\\", "\\\\").replace("'", "\\'")
            matcher = f"txt.trim() === '{text}'" if self._exact else f"txt.includes('{text}')"
            return f"(function(){{ var out=[]; var seen=new Set(); var tw=document.createTreeWalker({root_base}, NodeFilter.SHOW_TEXT); while(tw.nextNode()){{ var txt=tw.currentNode.textContent||''; var el=tw.currentNode.parentElement; if(el && ({matcher}) && !seen.has(el)){{ seen.add(el); out.push(el); }} }} return out; }})()"
        if self._mode == "placeholder":
            value = (self._value or "").replace("\\", "\\\\").replace("'", "\\'")
            matcher = f"p.trim() === '{value}'" if self._exact else f"p.includes('{value}')"
            return f"Array.from(({root}).querySelectorAll('input[placeholder], textarea[placeholder]')).filter(el => {{ var p = el.getAttribute('placeholder') || ''; return {matcher}; }})"
        if self._mode == "label":
            value = (self._value or "").replace("\\", "\\\\").replace("'", "\\'")
            matcher = f"txt.trim() === '{value}'" if self._exact else f"txt.includes('{value}')"
            return f"(function(){{ var scope={root}; return Array.from(scope.querySelectorAll('label')).map(label => {{ var txt=(label.innerText||label.textContent||''); if (!({matcher})) return null; var target=null; var htmlFor=label.getAttribute('for'); if (htmlFor && scope.getElementById) target=scope.getElementById(htmlFor); if(!target) target=label.querySelector('input, textarea, select, button'); return target; }}).filter(Boolean); }})()"
        if self._mode == "role":
            role = (self._value or "").replace("\\", "\\\\").replace("'", "\\'")
            role_name = (self._role_name or "").replace("\\", "\\\\").replace("'", "\\'")
            name_match = "true" if self._role_name is None else (f"accName.trim() === '{role_name}'" if self._role_name_exact else f"accName.includes('{role_name}')")
            return f"""(function(){{
              const scope = {root};
              const all = Array.from(scope.querySelectorAll('*'));
              function implicitRole(el) {{
                const tag = (el.tagName || '').toLowerCase();
                const type = (el.getAttribute('type') || '').toLowerCase();
                if (tag === 'button') return 'button';
                if (tag === 'a' && el.hasAttribute('href')) return 'link';
                if (tag === 'textarea') return 'textbox';
                if (tag === 'input' && ['text','email','search','url','tel','password'].includes(type)) return 'textbox';
                if (tag === 'input' && type === 'checkbox') return 'checkbox';
                if (tag === 'input' && type === 'radio') return 'radio';
                if (tag === 'select') return 'combobox';
                if (tag === 'input' && ['button','submit','reset'].includes(type)) return 'button';
                return null;
              }}
              function accessibleName(el) {{
                const ariaLabel = el.getAttribute('aria-label');
                if (ariaLabel) return ariaLabel.trim();
                const labelledBy = el.getAttribute('aria-labelledby');
                if (labelledBy) return labelledBy.split(/\s+/).map(id => scope.getElementById ? scope.getElementById(id) : null).filter(Boolean).map(n => (n.innerText || n.textContent || '').trim()).join(' ').trim();
                if (el.labels && el.labels.length) return Array.from(el.labels).map(l => (l.innerText || l.textContent || '').trim()).join(' ').trim();
                const tag = (el.tagName || '').toLowerCase();
                const type = (el.getAttribute('type') || '').toLowerCase();
                if (tag === 'input' && ['button','submit','reset'].includes(type)) return (el.value || '').trim();
                return ((el.innerText || el.textContent || '') || '').trim();
              }}
              return all.filter(el => {{
                const explicitRole = (el.getAttribute('role') || '').trim();
                const actualRole = explicitRole || implicitRole(el);
                if (actualRole !== '{role}') return false;
                const accName = accessibleName(el);
                return {name_match};
              }});
            }})()"""
        if self._mode == "testid":
            value = (self._value or "").replace("\\", "\\\\").replace("'", "\\'")
            return f"Array.from(({root}).querySelectorAll('[data-testid]')).filter(el => (el.getAttribute('data-testid') || '') === '{value}')"
        sel = self._selector.replace("\\", "\\\\").replace("'", "\\'")
        return f"Array.from(({root}).querySelectorAll('{sel}'))"

    def _apply_text_filter(self, collection_expr: str) -> str:
        if self._has_text is None:
            return collection_expr
        text = self._has_text.replace("\\", "\\\\").replace("'", "\\'")
        matcher = f"txt.trim() === '{text}'" if self._has_text_exact else f"txt.includes('{text}')"
        return f"(function(){{ return ({collection_expr}).filter(el => {{ var txt=(el.innerText||el.textContent||''); return {matcher}; }}); }})()"

    def _selector_expr(self) -> str:
        collection_expr = self._apply_text_filter(self._collection_expr())
        if self._index is None:
            return f"(({collection_expr})[0] || null)"
        if self._index == -1:
            return f"(function(){{ const els=({collection_expr}); return els.length ? els[els.length-1] : null; }})()"
        return f"(function(){{ const els=({collection_expr}); return els.length>{self._index} ? els[{self._index}] : null; }})()"

    def _element_expr(self) -> str:
        return self._selector_expr()

    def first(self) -> "_FrameLocator":
        return _FrameLocator(self._frame, self._selector, index=0, mode=self._mode, value=self._value, exact=self._exact, role_name=self._role_name, role_name_exact=self._role_name_exact, has_text=self._has_text, has_text_exact=self._has_text_exact, parent=self._parent)

    def nth(self, index: int) -> "_FrameLocator":
        return _FrameLocator(self._frame, self._selector, index=index, mode=self._mode, value=self._value, exact=self._exact, role_name=self._role_name, role_name_exact=self._role_name_exact, has_text=self._has_text, has_text_exact=self._has_text_exact, parent=self._parent)

    def last(self) -> "_FrameLocator":
        return _FrameLocator(self._frame, self._selector, index=-1, mode=self._mode, value=self._value, exact=self._exact, role_name=self._role_name, role_name_exact=self._role_name_exact, has_text=self._has_text, has_text_exact=self._has_text_exact, parent=self._parent)

    def filter(self, has_text: Optional[str] = None, exact: bool = False) -> "_FrameLocator":
        return _FrameLocator(self._frame, self._selector, index=self._index, mode=self._mode, value=self._value, exact=self._exact, role_name=self._role_name, role_name_exact=self._role_name_exact, has_text=has_text, has_text_exact=exact, parent=self._parent)

    def locator(self, selector: str) -> "_FrameLocator":
        return _FrameLocator(self._frame, selector, parent=self)

    async def wait_for(self, state: str = "visible", timeout: int = 5000) -> None:
        result = await self._frame.wait_for_selector(self._selector, timeout=timeout, state=state)
        if result is None:
            raise TimeoutError(f"Frame locator '{self._selector}' not {state} within {timeout}ms")

    async def text_content(self) -> Optional[str]:
        expr = self._selector_expr()
        return await self._frame._page._frame_eval_body(self._frame.path, f"const el = {expr}; return el ? el.textContent : null;")

    async def inner_text(self) -> Optional[str]:
        expr = self._selector_expr()
        return await self._frame._page._frame_eval_body(self._frame.path, f"const el = {expr}; return el ? el.innerText : null;")

    async def get_attribute(self, name: str) -> Optional[str]:
        name_escaped = name.replace("\\", "\\\\").replace("'", "\\'")
        expr = self._selector_expr()
        return await self._frame._page._frame_eval_body(self._frame.path, f"const el = {expr}; return el ? el.getAttribute('{name_escaped}') : null;")

    async def count(self) -> int:
        collection_expr = self._apply_text_filter(self._collection_expr())
        result = await self._frame._page._frame_eval_body(self._frame.path, f"return ({collection_expr}).length;")
        try:
            return int(result)
        except Exception:
            return 0

    async def exists(self) -> bool:
        return (await self.count()) > 0

    async def is_visible(self) -> bool:
        expr = self._selector_expr()
        result = await self._frame._page._frame_eval_body(
            self._frame.path,
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
