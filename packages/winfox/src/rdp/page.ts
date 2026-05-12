import { EventEmitter } from "events";
import * as humanize from "../humanize.js";
import { Locator } from "./locator.js";
import { RDPDialog } from "./dialog.js";
import { FrameLocator, RDPFrame } from "./frame.js";
import type { ExtensionBridge } from "./bridge.js";
import { RootActor, TabActor, WebConsoleActor, WatcherActor, StringActor, ScreenshotActor, MemoryActor, WindowGlobalActor } from "../geckordp/actors.js";
import { Events } from "../geckordp/events.js";
import type { RDPBrowser } from "./browser.js";
import type { RDPClient } from "../geckordp/client.js";

export class Mouse {
  private _page: RDPPage;
  public _x: number = 300 + Math.random() * 400;
  public _y: number = 200 + Math.random() * 300;

  constructor(page: RDPPage) {
    this._page = page;
  }

  async _rawMove(x: number, y: number): Promise<void> {
    this._page._ensureOpen();
    if (this._page._bridge?.isConnected && this._page._tabId !== null) {
      await this._page._bridge.sendCommand("moveTo", { tabId: this._page._tabId, x, y }, 5);
    }
  }

  async _followPath(path: humanize.PathPoint[]) {
    for (const [x, y, delay] of path) {
      await this._rawMove(x, y);
      if (delay > 0) await new Promise(r => setTimeout(r, delay * 1000));
    }
    if (path.length > 0) {
      this._x = path[path.length - 1]![0]!;
      this._y = path[path.length - 1]![1]!;
    }
  }

  async moveSmooth(x: number, y: number, targetWidth: number = 50.0): Promise<void> {
    this._page._ensureOpen();
    const path = humanize.generatePath(this._x, this._y, x, y, targetWidth);
    await this._followPath(path);
  }

  async click(x: number, y: number, button: number = 0): Promise<void> {
    this._page._ensureOpen();
    const dx = x - this._x, dy = y - this._y;
    if (dx * dx + dy * dy >= 4) await this.moveSmooth(x, y);
    if (this._page._bridge?.isConnected && this._page._tabId !== null) {
      await this._page._bridge.sendCommand("click", { tabId: this._page._tabId, x: this._x, y: this._y, button }, 5);
    } else {
      await this._page.evaluate(`document.elementFromPoint(${this._x},${this._y})?.click()`);
    }
  }

  async clickSmooth(x: number, y: number, targetWidth: number = 50.0, button: number = 0): Promise<void> {
    await this.moveSmooth(x, y, targetWidth);
    await new Promise(r => setTimeout(r, humanize.hoverDelay() * 1000));
    await this.click(this._x, this._y, button);
  }

  async wheel(deltaX: number, deltaY: number): Promise<void> {
    this._page._ensureOpen();
    if (this._page._bridge?.isConnected && this._page._tabId !== null) {
      await this._page._bridge.sendCommand("scroll", { tabId: this._page._tabId, x: this._x, y: this._y, deltaX, deltaY }, 5);
    }
  }

  async wheelSmooth(deltaY: number): Promise<void> {
    const events = humanize.scrollSequence(deltaY);
    for (const [dy, delay] of events) {
      if (Math.abs(dy) > 0.5) await this.wheel(0, dy);
      if (delay > 0) await new Promise(r => setTimeout(r, delay * 1000));
    }
  }
}

export class Keyboard {
  private _page: RDPPage;
  constructor(page: RDPPage) { this._page = page; }

  async type(text: string, instant: boolean = false): Promise<void> {
    this._page._ensureOpen();
    if (!this._page._bridge?.isConnected || this._page._tabId === null) return;
    if (instant || !text) {
      await this._page._bridge.sendCommand("type", { tabId: this._page._tabId, text }, 5);
      return;
    }
    const seq = humanize.typingSequence(text);
    for (const [ch, delay] of seq) {
      try { await this._page._bridge.sendCommand("type", { tabId: this._page._tabId, text: ch }, 5); } catch(e) { break; }
      if (delay > 0) await new Promise(r => setTimeout(r, delay * 1000));
    }
  }

  async press(key: string): Promise<void> {
    this._page._ensureOpen();
    if (this._page._bridge?.isConnected && this._page._tabId !== null) {
      await this._page._bridge.sendCommand("keyPress", { tabId: this._page._tabId, key }, 5);
    }
  }
}

export class RDPPage extends EventEmitter {
  public _browser: RDPBrowser;
  public _client: RDPClient;
  public _tabActorId: string;
  public _targetActorId: string;
  public _consoleActorId: string;
  public _browsingContextId: number | null;
  public _bridge: ExtensionBridge | null;
  public _tabId: number | null;

  public _url: string = "";
  public _closed: boolean = false;
  private _consoleStarted: boolean = false;
  private _dialogShimReady: boolean = false;
  private _dialogLastId: number = 0;

  public mouse: Mouse;
  public keyboard: Keyboard;

  private _persistentConsoleId: string | null = null;
  private _persistentConsoleCb: any = null;
  private _persistentTargetCb: any = null;
  private _watcherId: string | null = null;

  constructor(
    browser: RDPBrowser, client: RDPClient, tabActorId: string, targetActorId: string, consoleActorId: string,
    browsingContextId: number | null = null, bridge: ExtensionBridge | null = null, tabId: number | null = null
  ) {
    super();
    this._browser = browser;
    this._client = client;
    this._tabActorId = tabActorId;
    this._targetActorId = targetActorId;
    this._consoleActorId = consoleActorId;
    this._browsingContextId = browsingContextId;
    this._bridge = bridge;
    this._tabId = tabId;
    this.mouse = new Mouse(this);
    this.keyboard = new Keyboard(this);
  }

  isClosed(): boolean { return this._closed; }
  public _ensureOpen() { if (this._closed) throw new Error("Page is closed"); }

  dispose() {
     this._closed = true;
     // Cleanup listeners etc
     if (this._persistentConsoleId && this._persistentConsoleCb) {
       this._client.remove_event_listener(this._persistentConsoleId, Events.WebConsole.DOCUMENT_EVENT, this._persistentConsoleCb);
     }
     if (this._watcherId && this._persistentTargetCb) {
       this._client.remove_event_listener(this._watcherId, Events.Watcher.TARGET_AVAILABLE_FORM, this._persistentTargetCb);
     }
  }

  async _startPersistentWatcher() {
     const tab = new TabActor(this._client, this._tabActorId);
     const watcherCtx = await tab.get_watcher();
     if (watcherCtx && watcherCtx.actor) {
       this._watcherId = watcherCtx.actor;
       const watcher = new WatcherActor(this._client, this._watcherId!);
       await watcher.watch_targets(WatcherActor.Targets.FRAME);

       this._persistentTargetCb = (data: any) => {
         // handle target available... (simplified for stub)
       };
       this._client.add_event_listener(this._watcherId!, Events.Watcher.TARGET_AVAILABLE_FORM, this._persistentTargetCb);
     }
  }

  async close() {
     if (this._closed) return;
     await this._browser._closePage(this);
  }

  async evaluate(expression: string): Promise<any> {
    this._ensureOpen();
    let expr = expression.trim();
    if (expr.startsWith("() =>") || expr.startsWith("async () =>") || expr.startsWith("function")) {
        if (!expr.endsWith("()")) expr = `(${expr})()`;
        expr = `(function(){var v=(${expr});return typeof v==='object'&&v!==null?JSON.stringify(v):v})()`;
    }

    if (!this._consoleStarted) {
       const console = new WebConsoleActor(this._client, this._consoleActorId);
       await console.start_listeners([]);
       this._consoleStarted = true;
    }

    return new Promise((resolve) => {
        let done = false;
        const cb = (data: any) => {
            if (done) return;
            done = true;
            this._client.remove_event_listener(this._consoleActorId, Events.WebConsole.EVALUATION_RESULT, cb);
            let result = data.result;
            if (result && typeof result === "object") {
                if (result.type === "longString") result = result.initial;
                else if (result.type === "undefined") result = null;
            }
            if (typeof result === "string" && expr.includes("JSON.stringify")) {
                try { result = JSON.parse(result); } catch(e) {}
            }
            resolve(result);
        };
        this._client.add_event_listener(this._consoleActorId, Events.WebConsole.EVALUATION_RESULT, cb);
        new WebConsoleActor(this._client, this._consoleActorId).evaluate_js_async(expr);
        setTimeout(() => {
           if (!done) { done = true; this._client.remove_event_listener(this._consoleActorId, Events.WebConsole.EVALUATION_RESULT, cb); resolve(null); }
        }, 10000);
    });
  }

  async urlFresh(): Promise<string> {
    this._ensureOpen();
    try {
      const res = await this.evaluate("window.location.href");
      if (typeof res === "string") this._url = res;
    } catch(e) {}
    return this._url;
  }

  url(): string { return this._url; }

  async goto(url: string, options: { wait_until?: string, timeout?: number } = {}): Promise<void> {
      this._ensureOpen();
      const wait_until = options.wait_until || "load";
      const timeout = options.timeout || 30000;

      const goal = wait_until === "load" ? "dom-complete" : "dom-interactive";
      let loadDone = false;
      let listenersCb: any;

      if (!this._consoleStarted) {
         await new WebConsoleActor(this._client, this._consoleActorId).start_listeners([WebConsoleActor.Listeners.DOCUMENT_EVENTS]);
         this._consoleStarted = true;
      }

      await new Promise<void>((resolve) => {
          listenersCb = (data: any) => {
             const name = data.name || "";
             if (data.url) this._url = data.url;
             if (name === goal || name === "dom-complete") {
                 loadDone = true;
                 resolve();
             }
          };
          this._client.add_event_listener(this._consoleActorId, Events.WebConsole.DOCUMENT_EVENT, listenersCb);

          if (this._bridge?.isConnected && this._tabId !== null) {
              this._bridge.sendCommand("navigate", { tabId: this._tabId, url }).catch(()=>{});
          } else {
              this._client.send_receive({ to: this._tabActorId, type: "navigateTo", url, waitForLoad: false }).catch(()=>{});
          }

          setTimeout(() => { if (!loadDone) { loadDone = true; resolve(); } }, timeout);
      });

      this._client.remove_event_listener(this._consoleActorId, Events.WebConsole.DOCUMENT_EVENT, listenersCb);
  }

  async title(): Promise<string> { return await this.evaluate("document.title") || ""; }
  async content(): Promise<string> { return await this.evaluate("document.documentElement.outerHTML") || ""; }

  locator(selector: string): Locator { return new Locator(this, selector); }

  async _resolveDialog(dialogId: number, accepted: boolean, promptText: string | null): Promise<any> {
    this._ensureOpen();
    const promptValue = promptText === null ? "null" : JSON.stringify(promptText);
    const result = await this.evaluate(`(() => {
      const state = window.__rdpDialogState;
      if (!state) return null;
      const dialog = state.dialogs.find(d => d.id === ${dialogId});
      if (!dialog) return null;
      dialog.handled = true;
      dialog.accepted = ${accepted};
      dialog.promptText = ${promptValue};
      if (dialog.type === 'confirm') state.auto.confirm = ${accepted};
      if (dialog.type === 'prompt' && ${promptValue} !== null) state.auto.prompt = ${promptValue};
      return JSON.stringify(dialog);
    })()`);
    return typeof result === "string" ? JSON.parse(result) : null;
  }

  async _frameEvalBody(path: number[], body: string): Promise<any> {
     const pathJson = JSON.stringify(path);
     const result = await this.evaluate(`(() => {
       try {
         const path = ${pathJson};
         let frame = null;
         let win = window;
         let doc = document;
         for (const idx of path) {
           frame = doc.querySelectorAll('iframe, frame')[idx];
           if (!frame) return JSON.stringify({ ok: false, error: 'frame-not-found' });
           win = frame.contentWindow; doc = win.document;
         }
         const result = (() => { ${body} })();
         return JSON.stringify({ ok: true, value: result });
       } catch (e) {
         return JSON.stringify({ ok: false, error: 'cross-origin' });
       }
     })()`);
     if (typeof result === "string") {
        try {
           const parsed = JSON.parse(result);
           if (!parsed.ok) throw new Error(parsed.error);
           return parsed.value;
        } catch(e) { throw e; }
     }
     return result;
  }

  async _frameEvaluate(path: number[], expr: string): Promise<any> {
     return this._frameEvalBody(path, `return eval(${JSON.stringify(expr)});`);
  }

  async childFrames(path?: number[]): Promise<RDPFrame[]> {
     const result = await this.evaluate(`(() => {
        const out = [];
        const walk = (doc, parentPath) => {
          const frames = Array.from(doc.querySelectorAll('iframe, frame'));
          frames.forEach((frame, index) => {
            const p = parentPath.concat(index);
            try {
              out.push({ index, path: p, parent_path: parentPath.length ? parentPath : null });
              walk(frame.contentWindow.document, p);
            } catch(e) {
              out.push({ index, path: p, parent_path: parentPath.length ? parentPath : null });
            }
          });
        };
        walk(document, []);
        return JSON.stringify(out);
     })()`);
     const framesData = typeof result === "string" ? JSON.parse(result) : [];
     const allFrames = framesData.map((d: any) => new RDPFrame(this, d));
     if (!path) return allFrames.filter((f: RDPFrame) => !f.parentPath);
     return allFrames.filter((f: RDPFrame) => f.parentPath && f.parentPath.join() === path.join());
  }

  async screenshot(): Promise<Buffer> {
      if (this._bridge?.isConnected) {
          const res = await this._bridge.sendCommand("screenshot", {}, 10);
          if (res?.dataUrl) {
              const b64 = res.dataUrl.split(",")[1] || res.dataUrl;
              return Buffer.from(b64, 'base64');
          }
      }
      return Buffer.from("");
  }
  async waitForLoadState(state: string = "load", timeout: number = 30000): Promise<void> {
    this._ensureOpen();
    const target = state === "load" || state === "networkidle" ? "complete" : "interactive";
    try {
       const current = await this.evaluate("document.readyState");
       if (current === target || current === "complete") return;
    } catch(e) {}

    const goal = state === "load" || state === "networkidle" ? "dom-complete" : "dom-interactive";

    let loadDone = false;
    let listenersCb: any;

    if (!this._consoleStarted) {
       await new WebConsoleActor(this._client, this._consoleActorId).start_listeners([WebConsoleActor.Listeners.DOCUMENT_EVENTS]);
       this._consoleStarted = true;
    }

    await new Promise<void>((resolve) => {
        listenersCb = (data: any) => {
           const name = data.name || "";
           if (data.url) this._url = data.url;
           if (name === goal || name === "dom-complete") {
               loadDone = true;
               resolve();
           }
        };
        this._client.add_event_listener(this._consoleActorId, Events.WebConsole.DOCUMENT_EVENT, listenersCb);
        setTimeout(() => { if (!loadDone) { loadDone = true; resolve(); } }, timeout);
    });

    this._client.remove_event_listener(this._consoleActorId, Events.WebConsole.DOCUMENT_EVENT, listenersCb);
  }

  async setLocalStorage(data: Record<string, any>): Promise<void> {
    this._ensureOpen();
    const payload = JSON.stringify(Object.fromEntries(Object.entries(data).map(([k, v]) => [String(k), v === null ? "" : String(v)])));
    await this.evaluate(`(() => {
      const data = ${payload};
      for (const [k, v] of Object.entries(data)) localStorage.setItem(k, v);
      return true;
    })()`);
  }

  async getLocalStorage(): Promise<Record<string, string>> {
    this._ensureOpen();
    const result = await this.evaluate(`JSON.stringify(Object.fromEntries(Object.keys(localStorage).map(k => [k, localStorage.getItem(k)])))`);
    if (typeof result === "string") {
        try { return JSON.parse(result); } catch(e) {}
    }
    return {};
  }

  async clearLocalStorage(): Promise<void> {
    this._ensureOpen();
    await this.evaluate("localStorage.clear(); true");
  }
}
