import { RDPBrowser } from "./browser.js";
import type { RDPPage } from "./page.js";

export class RDPContext {
  private _parentBrowser: RDPBrowser;
  private _browser: RDPBrowser;
  private _closed = false;

  constructor(parentBrowser: RDPBrowser, browser: RDPBrowser) {
    this._parentBrowser = parentBrowser;
    this._browser = browser;
  }

  get browser(): RDPBrowser { return this._browser; }
  isClosed(): boolean { return this._closed; }

  async newPage(): Promise<RDPPage> {
    if (this._closed) throw new Error("Context is closed");
    return await this._browser.newPage();
  }

  pages(): RDPPage[] {
    if (this._closed) return [];
    return this._browser.listPages();
  }

  async close(): Promise<void> {
    if (this._closed) return;
    await this._browser.close();
    this._closed = true;
    this._parentBrowser._contexts = this._parentBrowser._contexts.filter(c => c !== this);
  }
}
