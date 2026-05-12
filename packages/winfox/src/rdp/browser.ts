import { spawn, ChildProcess } from "child_process";
import * as os from "os";
import * as fs from "fs";
import * as path from "path";
import { URL } from "url";
import { RDPClient } from "../geckordp/client.js";
import { ExtensionBridge } from "./bridge.js";
import { PORT_ALLOCATOR, waitForPort } from "./ports.js";
import { RDPPage } from "./page.js";
import { RDPContext } from "./context.js";
import { RootActor, TabActor, AddonsActor } from "../geckordp/actors.js";

const DEFAULT_RDP_PORT = 6000;
const DEFAULT_WS_PORT = 8775;

export class RDPBrowser {
  public _executable: string;
  public _headless: boolean;
  public _viewport: { width: number, height: number };
  public _rdpPort: number;
  public _wsPort: number;
  public _profilePath: string;
  public _extensionDir: string;
  public _proc: ChildProcess | null = null;
  public _client: RDPClient | null = null;
  public _bridge: ExtensionBridge | null = null;
  public _pages: RDPPage[] = [];
  public _contexts: RDPContext[] = [];
  public _portsReserved = false;

  constructor(options: any = {}) {
     this._executable = options.executablePath || "";
     this._headless = options.headless || false;
     this._viewport = options.viewport || { width: 1920, height: 1080 };
     this._rdpPort = options.rdpPort || DEFAULT_RDP_PORT;
     this._wsPort = options.wsPort || DEFAULT_WS_PORT;
     this._profilePath = options.profilePath || fs.mkdtempSync(path.join(os.tmpdir(), "camou_rdp_"));
     this._extensionDir = options.extensionDir || path.resolve(process.cwd(), "../../extension");
  }

  async start(): Promise<void> {
      if (!this._portsReserved) {
         this._rdpPort = await PORT_ALLOCATOR.reserve(this._rdpPort);
         this._wsPort = await PORT_ALLOCATOR.findAndReserve(this._wsPort === this._rdpPort ? this._wsPort + 1 : this._wsPort);
         this._portsReserved = true;
      }

      fs.mkdirSync(this._profilePath, { recursive: true });

      const prefs = {
         "extensions.experiments.enabled": true,
         "xpinstall.signatures.required": false,
         "extensions.autoDisableScopes": 0,
         "extensions.enabledScopes": 15,
         "browser.startup.page": 0,
         "browser.startup.homepage_override.mstone": "ignore",
         "browser.aboutwelcome.enabled": false,
         "test.events.async.enabled": true,
         "extensions.input.ws_port": this._wsPort
      };

      const userJs = path.join(this._profilePath, "user.js");
      let prefStr = "";
      for (const [k, v] of Object.entries(prefs)) {
          const val = typeof v === "boolean" ? (v ? "true" : "false") : (typeof v === "string" ? `"${v}"` : v);
          prefStr += `user_pref("${k}", ${val});\n`;
      }
      fs.writeFileSync(userJs, prefStr);

      this._bridge = new ExtensionBridge(this._wsPort);
      await this._bridge.start();

      const args = [
          "--new-instance", "--no-remote",
          `--start-debugger-server=${this._rdpPort}`,
          "--profile", this._profilePath,
          `--width=${this._viewport.width}`, `--height=${this._viewport.height}`
      ];
      if (this._headless) args.push("--headless");

      this._proc = spawn(this._executable, args, { stdio: "ignore" });

      await waitForPort("127.0.0.1", this._rdpPort, 30);

      this._client = new RDPClient(10);
      await this._client.connect("127.0.0.1", this._rdpPort);

      // Install extension
      try {
          const root = new RootActor(this._client);
          const rootData = await root.get_root();
          const addonsId = rootData?.addonsActor;
          if (addonsId) {
             const addons = new AddonsActor(this._client, addonsId);
             await addons.install_temporary_addon(path.resolve(this._extensionDir));
          }
      } catch(e) { console.error("Ext install fail", e); }
  }

  async newPage(): Promise<RDPPage> {
      if (!this._client) throw new Error("RDP not connected");

      const root = new RootActor(this._client);
      const tabs = await root.list_tabs();
      let tabActorId = tabs.length > 0 ? tabs[tabs.length - 1].actor : "";

      let bridgeTabId: number | null = null;
      if (this._bridge?.isConnected) {
         try {
           const res = await this._bridge.sendCommand("createTab", { url: "about:blank", active: true }, 5);
           bridgeTabId = res?.tabId || null;
         } catch(e) {}
      }

      if (!tabActorId) {
         const newTabs = await root.list_tabs();
         tabActorId = newTabs.length > 0 ? newTabs[newTabs.length - 1].actor : "";
      }

      const tab = new TabActor(this._client, tabActorId);
      const target = await tab.get_target();

      const page = new RDPPage(
          this, this._client, tabActorId, target?.actor || "", target?.consoleActor || "",
          target?.browsingContextID || null, this._bridge, bridgeTabId
      );
      this._pages.push(page);
      return page;
  }

  listPages(): RDPPage[] {
      this._pages = this._pages.filter(p => !p.isClosed());
      return this._pages;
  }

  async close(): Promise<void> {
      for (const p of this._pages) p.dispose();
      this._pages = [];

      if (this._bridge) {
         await this._bridge.stop();
         this._bridge = null;
      }
      if (this._client) {
         this._client.disconnect();
         this._client = null;
      }
      if (this._proc) {
         this._proc.kill();
         this._proc = null;
      }
      if (this._portsReserved) {
         await PORT_ALLOCATOR.release(this._rdpPort);
         await PORT_ALLOCATOR.release(this._wsPort);
         this._portsReserved = false;
      }
  }

  async _closePage(page: RDPPage) {
      if (page.isClosed()) return;
      if (this._bridge?.isConnected && page._tabId !== null) {
          try { await this._bridge.sendCommand("closeTab", { tabId: page._tabId }, 5); } catch(e) {}
      }
      page.dispose();
      this._pages = this._pages.filter(p => p !== page);
  }
}
