import type { RDPPage } from "./page.js";

export class FrameLocator {
  private _frame: RDPFrame;
  private _selector: string;
  private _index: number | null;
  private _mode: string | null;
  private _value: string | null;
  private _exact?: boolean | undefined;
  private _roleName?: string | null;
  private _roleNameExact?: boolean | undefined;
  private _hasText?: string | null;
  private _hasTextExact?: boolean | undefined;
  private _parent: FrameLocator | null;

  constructor(frame: RDPFrame, selector: string, options: {
    index?: number | null, mode?: string | null, value?: string | null, exact?: boolean | undefined,
    roleName?: string | null | undefined, roleNameExact?: boolean | undefined, hasText?: string | null | undefined, hasTextExact?: boolean | undefined, parent?: FrameLocator | null
  } = {}) {
    this._frame = frame;
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

  private _collectionExpr(): string {
    let root = "doc";
    if (this._parent !== null) {
      root = this._parent._elementExpr();
    }
    const rootBase = `(({root}).body||({root}).documentElement||({root}))`.replace(/\{root\}/g, root);

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
    const sel = this._selector.replace(/\\/g, "\\\\").replace(/'/g, "\\'");
    return `Array.from((${root}).querySelectorAll('${sel}'))`;
  }

  private _applyTextFilter(collectionExpr: string): string {
    if (this._hasText === null) return collectionExpr;
    const text = this._hasText!.replace(/\\/g, "\\\\").replace(/'/g, "\\'");
    const matcher = this._hasTextExact ? `txt.trim() === '${text}'` : `txt.includes('${text}')`;
    return `(function(){ return (${collectionExpr}).filter(el => { var txt=(el.innerText||el.textContent||''); return ${matcher}; }); })()`;
  }

  private _selectorExpr(): string {
    const collectionExpr = this._applyTextFilter(this._collectionExpr());
    if (this._index === null) return `((${collectionExpr})[0] || null)`;
    if (this._index === -1) return `(function(){ const els=(${collectionExpr}); return els.length ? els[els.length-1] : null; })()`;
    return `(function(){ const els=(${collectionExpr}); return els.length>${this._index} ? els[${this._index}] : null; })()`;
  }

  public _elementExpr(): string {
    return this._selectorExpr();
  }

  first(): FrameLocator {
    return new FrameLocator(this._frame, this._selector, { index: 0, mode: this._mode, value: this._value, exact: this._exact, roleName: this._roleName, roleNameExact: this._roleNameExact, hasText: this._hasText, hasTextExact: this._hasTextExact, parent: this._parent });
  }

  nth(index: number): FrameLocator {
    return new FrameLocator(this._frame, this._selector, { index, mode: this._mode, value: this._value, exact: this._exact, roleName: this._roleName, roleNameExact: this._roleNameExact, hasText: this._hasText, hasTextExact: this._hasTextExact, parent: this._parent });
  }

  last(): FrameLocator {
    return new FrameLocator(this._frame, this._selector, { index: -1, mode: this._mode, value: this._value, exact: this._exact, roleName: this._roleName, roleNameExact: this._roleNameExact, hasText: this._hasText, hasTextExact: this._hasTextExact, parent: this._parent });
  }

  filter(options: { hasText?: string, exact?: boolean }): FrameLocator {
    return new FrameLocator(this._frame, this._selector, { index: this._index, mode: this._mode, value: this._value, exact: this._exact, roleName: this._roleName, roleNameExact: this._roleNameExact, hasText: options.hasText, hasTextExact: options.exact, parent: this._parent });
  }

  locator(selector: string): FrameLocator {
    return new FrameLocator(this._frame, selector, { parent: this });
  }

  async waitFor(options: { state?: "visible" | "hidden", timeout?: number } = {}): Promise<void> {
    const state = options.state || "visible";
    const timeout = options.timeout || 5000;
    const result = await this._frame.waitForSelector(this._selector, { timeout, state });
    if (result === null) throw new Error(`Frame locator '${this._selector}' not ${state} within ${timeout}ms`);
  }

  async textContent(): Promise<string | null> {
    const expr = this._selectorExpr();
    return await this._frame._page._frameEvalBody(this._frame.path, `const el = ${expr}; return el ? el.textContent : null;`);
  }

  async innerText(): Promise<string | null> {
    const expr = this._selectorExpr();
    return await this._frame._page._frameEvalBody(this._frame.path, `const el = ${expr}; return el ? el.innerText : null;`);
  }

  async getAttribute(name: string): Promise<string | null> {
    const nameEscaped = name.replace(/\\/g, "\\\\").replace(/'/g, "\\'");
    const expr = this._selectorExpr();
    return await this._frame._page._frameEvalBody(this._frame.path, `const el = ${expr}; return el ? el.getAttribute('${nameEscaped}') : null;`);
  }

  async count(): Promise<number> {
    const collectionExpr = this._applyTextFilter(this._collectionExpr());
    const result = await this._frame._page._frameEvalBody(this._frame.path, `return (${collectionExpr}).length;`);
    try {
      return parseInt(result, 10);
    } catch {
      return 0;
    }
  }

  async exists(): Promise<boolean> {
    return (await this.count()) > 0;
  }

  async isVisible(): Promise<boolean> {
    const expr = this._selectorExpr();
    const result = await this._frame._page._frameEvalBody(this._frame.path, `
      const el = ${expr};
      if (!el) return false;
      const style = win.getComputedStyle(el);
      if (!style) return false;
      if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
      const r = el.getBoundingClientRect();
      return !!(r.width > 0 && r.height > 0);
    `);
    return !!result;
  }

  async isHidden(): Promise<boolean> {
    return !(await this.isVisible());
  }

  async click(): Promise<void> {
    await this._frame.click(this._selector);
  }

  async hover(): Promise<void> {
    await this._frame.hover(this._selector);
  }

  async focus(): Promise<void> {
    await this._frame.focus(this._selector);
  }

  async press(key: string): Promise<void> {
    await this._frame.press(this._selector, key);
  }
}

export class RDPFrame {
  public _page: RDPPage;
  public index: number;
  public path: number[];
  public parentPath: number[] | null;
  public depth: number;
  public name: string | null;
  public id: string | null;
  public src: string | null;
  public url: string | null;
  public sameOrigin: boolean;

  constructor(page: RDPPage, data: any) {
    this._page = page;
    this.index = data.index || 0;
    this.path = data.path || [];
    this.parentPath = data.parent_path || null;
    this.depth = data.depth || 0;
    this.name = data.name || null;
    this.id = data.id || null;
    this.src = data.src || null;
    this.url = data.url || null;
    this.sameOrigin = data.same_origin ?? true;
  }

  async childFrames(): Promise<RDPFrame[]> {
    return await this._page.childFrames(this.path);
  }

  locator(selector: string): FrameLocator {
    return new FrameLocator(this, selector);
  }

  getByText(text: string, options: { exact?: boolean } = {}): FrameLocator {
    return new FrameLocator(this, "", { mode: "text", value: text, exact: options.exact });
  }

  getByPlaceholder(text: string, options: { exact?: boolean } = {}): FrameLocator {
    return new FrameLocator(this, "", { mode: "placeholder", value: text, exact: options.exact });
  }

  getByLabel(text: string, options: { exact?: boolean } = {}): FrameLocator {
    return new FrameLocator(this, "", { mode: "label", value: text, exact: options.exact });
  }

  getByTestId(value: string): FrameLocator {
    return new FrameLocator(this, "", { mode: "testid", value, exact: true });
  }

  getByRole(role: string, options: { name?: string, exact?: boolean } = {}): FrameLocator {
    return new FrameLocator(this, "", { mode: "role", value: role, roleName: options.name, roleNameExact: options.exact });
  }

  async click(selector: string): Promise<void> {
    const expr = new FrameLocator(this, selector)._elementExpr();
    const result = await this._page._frameEvalBody(this.path, `
      const el = ${expr};
      if (!el) return null;
      const r = el.getBoundingClientRect();
      if (r.width === 0 && r.height === 0) return null;
      return JSON.stringify({x: r.x, y: r.y, w: r.width, h: r.height});
    `);
    if (typeof result === "string") {
      try {
        const rect = JSON.parse(result);
        const x = rect.x + rect.w / 2;
        const y = rect.y + rect.h / 2;
        await this._page.mouse.clickSmooth(x, y, rect.w || 50);
        return;
      } catch (e) {}
    }
    throw new Error(`Frame.click: Element not found or not clickable: ${selector}`);
  }

  async hover(selector: string): Promise<void> {
    const expr = new FrameLocator(this, selector)._elementExpr();
    const result = await this._page._frameEvalBody(this.path, `
      const el = ${expr};
      if (!el) return null;
      const r = el.getBoundingClientRect();
      if (r.width === 0 && r.height === 0) return null;
      return JSON.stringify({x: r.x, y: r.y, w: r.width, h: r.height});
    `);
    if (typeof result === "string") {
      try {
        const rect = JSON.parse(result);
        const x = rect.x + rect.w / 2;
        const y = rect.y + rect.h / 2;
        await this._page.mouse.moveSmooth(x, y, rect.w || 50);
        return;
      } catch (e) {}
    }
    throw new Error(`Frame.hover: Element not found or not interactable: ${selector}`);
  }

  async focus(selector: string): Promise<void> {
    const expr = new FrameLocator(this, selector)._elementExpr();
    const result = await this._page._frameEvalBody(this.path, `
      const el = ${expr};
      if (!el) return false;
      if (typeof el.scrollIntoView === 'function') el.scrollIntoView({ block: 'center', inline: 'center' });
      if (typeof el.focus === 'function') el.focus();
      return doc.activeElement === el;
    `);
    if (!result) throw new Error(`Frame.focus: Element not found or focus failed: ${selector}`);
  }

  async press(selector: string, key: string): Promise<void> {
    await this.focus(selector);
    await this._page.keyboard.press(key);
  }

  async fill(selector: string, text: string): Promise<void> {
    await this.click(selector);
    await new Promise(r => setTimeout(r, 100));
    const expr = new FrameLocator(this, selector)._elementExpr();
    const textEscaped = text.replace(/\\/g, "\\\\").replace(/'/g, "\\'");
    await this._page._frameEvalBody(this.path, `
      const el = ${expr};
      if (!el) return false;
      if ('value' in el) {
        el.value = '${textEscaped}';
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        return true;
      }
      return false;
    `);
  }

  async evaluate(expression: string): Promise<any> {
    return await this._page._frameEvaluate(this.path, expression);
  }

  async textContent(selector: string): Promise<string | null> {
    return await this.locator(selector).textContent();
  }

  async innerText(selector: string): Promise<string | null> {
    return await this.locator(selector).innerText();
  }

  async getAttribute(selector: string, name: string): Promise<string | null> {
    return await this.locator(selector).getAttribute(name);
  }

  async waitForSelector(selector: string, options: { state?: "visible" | "hidden", timeout?: number } = {}): Promise<any> {
    const state = options.state || "visible";
    const timeout = options.timeout || 5000;
    const deadline = Date.now() + timeout;
    while (Date.now() < deadline) {
      const isVis = await this.locator(selector).isVisible();
      if (state === "visible" && isVis) return {};
      if (state === "hidden" && !isVis) return {};
      await new Promise(r => setTimeout(r, 100));
    }
    return null;
  }
}
