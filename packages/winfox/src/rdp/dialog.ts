import type { RDPPage } from "./page.js";

export class RDPDialog {
  private _page: RDPPage;
  private _id: number;
  public type: string;
  public message: string;
  public defaultValue: string | null;
  public handled: boolean = false;
  public accepted: boolean | null = null;
  public promptText: string | null = null;

  constructor(page: RDPPage, dialogId: number, dialogType: string, message: string, defaultValue: string | null = null) {
    this._page = page;
    this._id = dialogId;
    this.type = dialogType;
    this.message = message;
    this.defaultValue = defaultValue;
  }

  private _updateFromState(state: any) {
    this.handled = state.handled ?? this.handled;
    this.accepted = state.accepted ?? this.accepted;
    this.promptText = state.promptText ?? this.promptText;
  }

  async accept(promptText: string | null = null): Promise<void> {
    if (this.handled) return;
    const state = await this._page._resolveDialog(this._id, true, promptText);
    if (state && typeof state === 'object') {
      this._updateFromState(state);
    } else {
      this.handled = true;
      this.accepted = true;
      this.promptText = promptText;
    }
  }

  async dismiss(): Promise<void> {
    if (this.handled) return;
    const state = await this._page._resolveDialog(this._id, false, null);
    if (state && typeof state === 'object') {
      this._updateFromState(state);
    } else {
      this.handled = true;
      this.accepted = false;
      this.promptText = null;
    }
  }
}
