import asyncio
import json
import time
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from camoufox._rdp_legacy_impl import RDPPage


class _Locator:
    """Playwright-compatible locator for RDPPage."""

    def __init__(
        self,
        page: "RDPPage",
        selector: str,
        index: Optional[int] = None,
        mode: str = "css",
        value: Optional[str] = None,
        exact: bool = False,
        role_name: Optional[str] = None,
        role_name_exact: bool = False,
        has_text: Optional[str] = None,
        has_text_exact: bool = False,
        parent: Optional["_Locator"] = None,
    ):
        self._page = page
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

    def _collection_expr(self, root: str = "document") -> str:
        if self._parent is not None:
            root = self._parent._to_css_and_js()
        root_base = f"(({root}).body||({root}).documentElement||({root}))"
        if self._mode == "text":
            text = (self._value or "").replace("\\", "\\\\").replace("'", "\\'")
            matcher = f"txt.trim() === '{text}'" if self._exact else f"txt.includes('{text}')"
            return (
                f"(function(){{ var scope={root}; var out=[]; var seen=new Set(); var tw=document.createTreeWalker({root_base}, NodeFilter.SHOW_TEXT);"
                f"while(tw.nextNode()){{ var txt=tw.currentNode.textContent||''; var el=tw.currentNode.parentElement; if(el && ({matcher}) && !seen.has(el)){{ seen.add(el); out.push(el); }} }} return out; }})()"
            )

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

        sel = self._selector
        if sel.startswith("text="):
            text = sel[5:]
            text = text.replace("\\", "\\\\").replace("'", "\\'")
            return (
                f"(function(){{ var out=[]; var seen=new Set(); var tw=document.createTreeWalker({root_base}, NodeFilter.SHOW_TEXT);"
                f"while(tw.nextNode()){{ var txt=tw.currentNode.textContent||''; var el=tw.currentNode.parentElement; if(el && txt.includes('{text}') && !seen.has(el)){{ seen.add(el); out.push(el); }} }} return out; }})()"
            )
        if sel.startswith("css:") or sel.startswith("css="):
            sel = sel[4:]
        sel_escaped = sel.replace(chr(39), chr(92) + chr(39))
        return f"Array.from(({root}).querySelectorAll('{sel_escaped}'))"

    def _apply_text_filter(self, collection_expr: str) -> str:
        if self._has_text is None:
            return collection_expr
        text = self._has_text.replace("\\", "\\\\").replace("'", "\\'")
        matcher = f"txt.trim() === '{text}'" if self._has_text_exact else f"txt.includes('{text}')"
        return f"(function(){{ return ({collection_expr}).filter(el => {{ var txt=(el.innerText||el.textContent||''); return {matcher}; }}); }})()"

    def _to_css_and_js(self) -> str:
        collection_expr = self._apply_text_filter(self._collection_expr("document"))
        if self._index is None:
            return f"(({collection_expr})[0] || null)"
        if self._index == -1:
            return f"(function(){{ var els=({collection_expr}); return els.length ? els[els.length-1] : null; }})()"
        return f"(function(){{ var els=({collection_expr}); return els.length>{self._index} ? els[{self._index}] : null; }})()"

    def first(self) -> "_Locator":
        return _Locator(self._page, self._selector, index=0, mode=self._mode, value=self._value, exact=self._exact, role_name=self._role_name, role_name_exact=self._role_name_exact, has_text=self._has_text, has_text_exact=self._has_text_exact, parent=self._parent)

    def nth(self, index: int) -> "_Locator":
        return _Locator(self._page, self._selector, index=index, mode=self._mode, value=self._value, exact=self._exact, role_name=self._role_name, role_name_exact=self._role_name_exact, has_text=self._has_text, has_text_exact=self._has_text_exact, parent=self._parent)

    def last(self) -> "_Locator":
        return _Locator(self._page, self._selector, index=-1, mode=self._mode, value=self._value, exact=self._exact, role_name=self._role_name, role_name_exact=self._role_name_exact, has_text=self._has_text, has_text_exact=self._has_text_exact, parent=self._parent)

    def filter(self, has_text: Optional[str] = None, exact: bool = False) -> "_Locator":
        return _Locator(self._page, self._selector, index=self._index, mode=self._mode, value=self._value, exact=self._exact, role_name=self._role_name, role_name_exact=self._role_name_exact, has_text=has_text, has_text_exact=exact, parent=self._parent)

    def locator(self, selector: str) -> "_Locator":
        return _Locator(self._page, selector, parent=self)

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
                await self._page.evaluate(f"try{{delete window._ws['{wfs_key}']}}catch(e){{}}")
                if val == "timeout":
                    raise TimeoutError(f"Locator '{self._selector}' not {state} within {timeout}ms")
                return
            await asyncio.sleep(0.1)
        try:
            await self._page.evaluate(f"try{{delete window._ws['{wfs_key}']}}catch(e){{}}")
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
                    await self._page.mouse.click_smooth(pos["x"], pos["y"], target_width=pos.get("w", 50))
                    return
            except Exception:
                pass
            await asyncio.sleep(0.3)
        raise TimeoutError(f"Locator '{self._selector}' not clickable within {timeout}ms")

    async def text_content(self) -> Optional[str]:
        find_js = self._to_css_and_js()
        result = await self._page.evaluate(f"(function(){{ var el = {find_js}; return el ? el.textContent : null; }})()")
        return result

    async def inner_text(self) -> Optional[str]:
        find_js = self._to_css_and_js()
        result = await self._page.evaluate(f"(function(){{ var el = {find_js}; return el ? el.innerText : null; }})()")
        return result

    async def get_attribute(self, name: str) -> Optional[str]:
        find_js = self._to_css_and_js()
        name_escaped = name.replace("'", "\\'")
        result = await self._page.evaluate(f"(function(){{ var el = {find_js}; return el ? el.getAttribute('{name_escaped}') : null; }})()")
        return result

    async def count(self) -> int:
        collection_expr = self._apply_text_filter(self._collection_expr("document"))
        result = await self._page.evaluate(f"({collection_expr}).length")
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
