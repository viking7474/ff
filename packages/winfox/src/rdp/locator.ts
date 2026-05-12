import type { RDPPage } from "./page.js";

export class Locator {
  private _page: RDPPage;
  private _selector: string;
  private _index: number | null;
  private _mode: string | null;
  private _value: string | null;
  private _exact?: boolean;
  private _roleName?: string | null;
  private _roleNameExact?: boolean;
  private _hasText?: string | null;
  private _hasTextExact?: boolean;
  private _parent: Locator | null;

  constructor(page: RDPPage, selector: string, options: {
    index?: number | null, mode?: string | null, value?: string | null, exact?: boolean | undefined,
    roleName?: string | null | undefined, roleNameExact?: boolean | undefined, hasText?: string | null | undefined, hasTextExact?: boolean | undefined, parent?: Locator | null
  } = {}) {
    this._page = page;
    this._selector = selector;
    this._index = options.index ?? null;
    this._mode = options.mode ?? null;
    this._value = options.value ?? null;
    this._exact = options.exact ?? false;
    this._roleName = options.roleName ?? null;
    this._roleNameExact = options.roleNameExact ?? false;
    this._hasText = options.hasText ?? null;
    this._hasTextExact = options.hasTextExact ?? false;
    this._parent = options.parent ?? null;
  }

  private _collectionExpr(root: string = "document"): string {
    if (this._parent !== null) {
      root = this._parent._elementExpr();
    }
    const rootBase = `((${root}).body||(${root}).documentElement||(${root}))`;

    if (this._mode === "text") {
      const text = (this._value || "").replace(/\\/g, "\\\\").replace(/'/g, "\\'");
      const matcher = this._exact ? `txt.trim() === '${text}'` : `txt.includes('${text}')`;
      return `(function(){ var out=[]; var seen=new Set(); var tw=document.createTreeWalker(${rootBase}, NodeFilter.SHOW_TEXT); while(tw.nextNode()){ var txt=tw.currentNode.textContent||''; var el=tw.currentNode.parentElement; if(el && (${matcher}) && !seen.has(el)){ seen.add(el); out.push(el); } } return out; })()`;
    }
    if (this._mode === "placeholder") {
      const value = (this._value || "").replace(/\\/g, "\\\\").replace(/'/g, "\\'");
      const matcher = this._exact ? `p.trim() === '${value}'` : `p.includes('${value}')`;
      return `Array.from((${root}).querySelectorAll('input[placeholder], textarea[placeholder]')).filter(el => { var p = el.getAttribute('placeholder') || ''; return ${matcher}; })`;
    }
    if (this._mode === "label") {
      const value = (this._value || "").replace(/\\/g, "\\\\").replace(/'/g, "\\'");
      const matcher = this._exact ? `txt.trim() === '${value}'` : `txt.includes('${value}')`;
      return `(function(){ var scope=${root}; return Array.from(scope.querySelectorAll('label')).map(label => { var txt=(label.innerText||label.textContent||''); if (!(${matcher})) return null; var target=null; var htmlFor=label.getAttribute('for'); if (htmlFor && scope.getElementById) target=scope.getElementById(htmlFor); if(!target) target=label.querySelector('input, textarea, select, button'); return target; }).filter(Boolean); })()`;
    }
    if (this._mode === "role") {
      const role = (this._value || "").replace(/\\/g, "\\\\").replace(/'/g, "\\'");
      const roleName = (this._roleName || "").replace(/\\/g, "\\\\").replace(/'/g, "\\'");
      const nameMatch = this._roleName === null ? "true" : (this._roleNameExact ? `accName.trim() === '${roleName}'` : `accName.includes('${roleName}')`);
      return `(function(){
        const scope = ${root};
        const all = Array.from(scope.querySelectorAll('*'));
        function implicitRole(el) {
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
        }
        function accessibleName(el) {
          const ariaLabel = el.getAttribute('aria-label');
          if (ariaLabel) return ariaLabel.trim();
          const labelledBy = el.getAttribute('aria-labelledby');
          if (labelledBy) return labelledBy.split(/\\s+/).map(id => scope.getElementById ? scope.getElementById(id) : null).filter(Boolean).map(n => (n.innerText || n.textContent || '').trim()).join(' ').trim();
          if (el.labels && el.labels.length) return Array.from(el.labels).map(l => (l.innerText || l.textContent || '').trim()).join(' ').trim();
          const tag = (el.tagName || '').toLowerCase();
          const type = (el.getAttribute('type') || '').toLowerCase();
          if (tag === 'input' && ['button','submit','reset'].includes(type)) return (el.value || '').trim();
          return ((el.innerText || el.textContent || '') || '').trim();
        }
        return all.filter(el => {
          const explicitRole = (el.getAttribute('role') || '').trim();
          const actualRole = explicitRole || implicitRole(el);
          if (actualRole !== '${role}') return false;
          const accName = accessibleName(el);
          return ${nameMatch};
        });
      })()`;
    }
    if (this._mode === "testid") {
      const value = (this._value || "").replace(/\\/g, "\\\\").replace(/'/g, "\\'");
      return `Array.from((${root}).querySelectorAll('[data-testid]')).filter(el => (el.getAttribute('data-testid') || '') === '${value}')`;
    }

    let sel = this._selector;
    if (sel.startsWith("text=")) {
      const text = sel.substring(5).replace(/\\/g, "\\\\").replace(/'/g, "\\'");
      return `(function(){ var out=[]; var seen=new Set(); var tw=document.createTreeWalker(${rootBase}, NodeFilter.SHOW_TEXT); while(tw.nextNode()){ var txt=tw.currentNode.textContent||''; var el=tw.currentNode.parentElement; if(el && txt.includes('${text}') && !seen.has(el)){ seen.add(el); out.push(el); } } return out; })()`;
    }
    if (sel.startsWith("css:") || sel.startsWith("css=")) {
      sel = sel.substring(4);
    }
    const selEscaped = sel.replace(/'/g, "\\'");
    return `Array.from((${root}).querySelectorAll('${selEscaped}'))`;
  }

  private _applyTextFilter(collectionExpr: string): string {
    if (this._hasText === null) return collectionExpr;
    const text = this._hasText!.replace(/\\/g, "\\\\").replace(/'/g, "\\'");
    const matcher = this._hasTextExact ? `txt.trim() === '${text}'` : `txt.includes('${text}')`;
    return `(function(){ return (${collectionExpr}).filter(el => { var txt=(el.innerText||el.textContent||''); return ${matcher}; }); })()`;
  }

  private _toCssAndJs(): string {
    const collectionExpr = this._applyTextFilter(this._collectionExpr("document"));
    if (this._index === null) return `((${collectionExpr})[0] || null)`;
    if (this._index === -1) return `(function(){ var els=(${collectionExpr}); return els.length ? els[els.length-1] : null; })()`;
    return `(function(){ var els=(${collectionExpr}); return els.length>${this._index} ? els[${this._index}] : null; })()`;
  }

  public _elementExpr(): string {
    return this._toCssAndJs();
  }

  first(): Locator {
    return new Locator(this._page, this._selector, { index: 0, mode: this._mode, value: this._value, exact: this._exact, roleName: this._roleName, roleNameExact: this._roleNameExact, hasText: this._hasText, hasTextExact: this._hasTextExact, parent: this._parent });
  }

  nth(index: number): Locator {
    return new Locator(this._page, this._selector, { index, mode: this._mode, value: this._value, exact: this._exact, roleName: this._roleName, roleNameExact: this._roleNameExact, hasText: this._hasText, hasTextExact: this._hasTextExact, parent: this._parent });
  }

  last(): Locator {
    return new Locator(this._page, this._selector, { index: -1, mode: this._mode, value: this._value, exact: this._exact, roleName: this._roleName, roleNameExact: this._roleNameExact, hasText: this._hasText, hasTextExact: this._hasTextExact, parent: this._parent });
  }

  filter(options: { hasText?: string, exact?: boolean }): Locator {
    return new Locator(this._page, this._selector, { index: this._index, mode: this._mode, value: this._value, exact: this._exact, roleName: this._roleName, roleNameExact: this._roleNameExact, hasText: options.hasText, hasTextExact: options.exact, parent: this._parent });
  }

  locator(selector: string): Locator {
    return new Locator(this._page, selector, { parent: this });
  }

  async waitFor(options: { state?: "visible" | "hidden", timeout?: number } = {}): Promise<void> {
    const state = options.state || "visible";
    const timeout = options.timeout || 5000;
    const findJs = this._toCssAndJs();
    const wfsKey = `_l${(Date.now() % 100000)}`;

    let setupJs = "";
    if (state === "hidden") {
      setupJs = `(function(){
        if(!window._ws)window._ws={};
        if ((${findJs}) === null) { window._ws['${wfsKey}']='ok'; return; }
        var obs = new MutationObserver(function(){
          if ((${findJs}) === null) { obs.disconnect(); window._ws['${wfsKey}']='ok'; }
        });
        obs.observe(document.body||document.documentElement, {childList:true,subtree:true,attributes:true});
        setTimeout(function(){ obs.disconnect(); if(!window._ws['${wfsKey}']) window._ws['${wfsKey}']='timeout'; },${timeout});
      })()`;
    } else {
      const vis = state === "visible" ? "if(r.width===0&&r.height===0) return null;" : "";
      setupJs = `(function(){
        if(!window._ws)window._ws={};
        function chk(){
          var el=${findJs}; if(!el) return null;
          var r=el.getBoundingClientRect(); ${vis}
          return JSON.stringify({x:r.x,y:r.y,w:r.width,h:r.height});
        }
        var hit=chk(); if(hit){ window._ws['${wfsKey}']=hit; return; }
        var obs=new MutationObserver(function(){
          var hit=chk(); if(hit){ obs.disconnect(); window._ws['${wfsKey}']=hit; }
        });
        obs.observe(document.body||document.documentElement, {childList:true,subtree:true,attributes:true});
        setTimeout(function(){ obs.disconnect(); if(!window._ws['${wfsKey}']) window._ws['${wfsKey}']='timeout'; },${timeout});
      })()`;
    }

    await this._page.evaluate(setupJs);
    const deadline = Date.now() + timeout;
    while (Date.now() < deadline) {
      const val = await this._page.evaluate(`(window._ws||{})['${wfsKey}']`);
      if (val && val !== "null") {
        await this._page.evaluate(`try{delete window._ws['${wfsKey}']}catch(e){}`);
        if (val === "timeout") throw new Error(`Locator '${this._selector}' not ${state} within ${timeout}ms`);
        return;
      }
      await new Promise(r => setTimeout(r, 100));
    }
    try { await this._page.evaluate(`try{delete window._ws['${wfsKey}']}catch(e){}`); } catch(e) {}
    throw new Error(`Locator '${this._selector}' not ${state} within ${timeout}ms`);
  }

  async click(options: { timeout?: number } = {}): Promise<void> {
    const timeout = options.timeout || 5000;
    const findJs = this._toCssAndJs();
    const deadline = Date.now() + timeout;
    while (Date.now() < deadline) {
      try {
        const js = `(function(){ var el = ${findJs}; if(!el) return null; var r = el.getBoundingClientRect(); if(r.width===0&&r.height===0) return null; return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2,w:r.width}); })()`;
        const result = await this._page.evaluate(js);
        if (result && typeof result === "string") {
          const pos = JSON.parse(result);
          await this._page.mouse.clickSmooth(pos.x, pos.y, pos.w || 50);
          return;
        }
      } catch (e) {}
      await new Promise(r => setTimeout(r, 300));
    }
    throw new Error(`Locator '${this._selector}' not clickable within ${timeout}ms`);
  }

  async textContent(): Promise<string | null> {
    const findJs = this._toCssAndJs();
    return await this._page.evaluate(`(function(){ var el = ${findJs}; return el ? el.textContent : null; })()`);
  }

  async innerText(): Promise<string | null> {
    const findJs = this._toCssAndJs();
    return await this._page.evaluate(`(function(){ var el = ${findJs}; return el ? el.innerText : null; })()`);
  }

  async getAttribute(name: string): Promise<string | null> {
    const findJs = this._toCssAndJs();
    const nameEscaped = name.replace(/'/g, "\\'");
    return await this._page.evaluate(`(function(){ var el = ${findJs}; return el ? el.getAttribute('${nameEscaped}') : null; })()`);
  }

  async count(): Promise<number> {
    const collectionExpr = this._applyTextFilter(this._collectionExpr("document"));
    const result = await this._page.evaluate(`(${collectionExpr}).length`);
    return result || 0;
  }

  async exists(): Promise<boolean> {
    return (await this.count()) > 0;
  }

  async isVisible(): Promise<boolean> {
    const findJs = this._toCssAndJs();
    const result = await this._page.evaluate(`(function(){
      var el = ${findJs};
      if (!el) return false;
      var style = window.getComputedStyle(el);
      if (!style) return false;
      if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
      var r = el.getBoundingClientRect();
      return !!(r.width > 0 && r.height > 0);
    })()`);
    return !!result;
  }

  async isHidden(): Promise<boolean> {
    return !(await this.isVisible());
  }
}
