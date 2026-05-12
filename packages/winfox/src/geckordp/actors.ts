import { RDPClient } from "./client.js";

export class RootActor {
    constructor(private client: RDPClient) {}
    async get_root() {
        return await this.client.send_receive({ to: "root", type: "getRoot" });
    }
    async list_tabs() {
        const res = await this.client.send_receive({ to: "root", type: "listTabs" });
        return res?.tabs || [];
    }
}

export class AddonsActor {
    constructor(private client: RDPClient, private actorId: string) {}
    async install_temporary_addon(addonPath: string) {
        return await this.client.send_receive({ to: this.actorId, type: "installTemporaryAddon", addonPath });
    }
}

export class TabActor {
    constructor(private client: RDPClient, private actorId: string) {}
    async get_target() {
        const res = await this.client.send_receive({ to: this.actorId, type: "getTarget" });
        return res?.target || null;
    }
    async get_watcher() {
        const res = await this.client.send_receive({ to: this.actorId, type: "getWatcher" });
        return res || {};
    }
}

export class WatcherActor {
    public static Targets = { FRAME: "frame" };
    constructor(private client: RDPClient, private actorId: string) {}
    async watch_targets(targetType: string) {
        return await this.client.send_receive({ to: this.actorId, type: "watchTargets", targetType });
    }
    async watch_resources(resources: any[]) {
        return await this.client.send_receive({ to: this.actorId, type: "watchResources", resources });
    }
}

export class Resources {
    public static NETWORK_EVENT = "network-event";
}

export class WebConsoleActor {
    public static Listeners = { DOCUMENT_EVENTS: "documentEvents" };
    constructor(private client: RDPClient, private actorId: string) {}
    async start_listeners(listeners: string[]) {
        return await this.client.send_receive({ to: this.actorId, type: "startListeners", listeners });
    }
    async evaluate_js_async(text: string) {
        return await this.client.send_receive({ to: this.actorId, type: "evaluateJSAsync", text });
    }
}

export class MemoryActor {
    constructor(private client: RDPClient, private actorId: string) {}
    async attach() {
        return await this.client.send_receive({ to: this.actorId, type: "attach" });
    }
    async detach() {
        return await this.client.send_receive({ to: this.actorId, type: "detach" });
    }
    async measure() {
        return await this.client.send_receive({ to: this.actorId, type: "measure" });
    }
    async force_garbage_collection() {
        return await this.client.send_receive({ to: this.actorId, type: "forceGarbageCollection" });
    }
    async force_cycle_collection() {
        return await this.client.send_receive({ to: this.actorId, type: "forceCycleCollection" });
    }
}

export class ScreenshotActor {
    constructor(private client: RDPClient, private actorId: string) {}
    async capture(browsingContextID: number) {
         return await this.client.send_receive({ to: this.actorId, type: "capture", browsingContextID });
    }
}

export class StringActor {
    constructor(private client: RDPClient, private actorId: string) {}
    async substring(start: number, end: number) {
        return await this.client.send_receive({ to: this.actorId, type: "substring", start, end });
    }
}

export class WindowGlobalActor {
    constructor(private client: RDPClient, private actorId: string) {}
    async reload() {
         return await this.client.send_receive({ to: this.actorId, type: "reload" });
    }
}
